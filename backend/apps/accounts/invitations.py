"""Sign-up by invitation only.

Admins invite people by email from the People page; the email carries a link to
/signup?invite=<token>. The token is random (secrets.token_urlsafe), stored only as a SHA-256
hash, works once, and expires after INVITATION_DAYS. Resending issues a fresh token (the old
link stops working); revoking kills it. Accepting it creates the account with the email,
role (admin = organisation staff) and team the admin chose.

Email goes through Django's configured EMAIL_BACKEND (console by default — see settings). The
invite link is also returned to the admin so it can be shared by hand if email isn't set up.
"""
import hashlib
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.teams.models import Team, TeamMembership

from .models import Invitation, User

logger = logging.getLogger(__name__)

INVITATION_DAYS = 7


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _issue_token(invitation: Invitation) -> str:
    token = secrets.token_urlsafe(32)
    now = timezone.now()
    invitation.token_hash = hash_token(token)
    invitation.sent_at = now
    invitation.expires_at = now + timedelta(days=INVITATION_DAYS)
    return token


def _frontend_base(request) -> str:
    """Where the app is served: FRONTEND_URL if set, else the browser's Origin, else this host."""
    configured = getattr(settings, "FRONTEND_URL", "")
    if configured:
        return configured.rstrip("/")
    origin = request.headers.get("Origin")
    if origin:
        return origin.rstrip("/")
    return request.build_absolute_uri("/").rstrip("/")


def invite_url(request, token: str) -> str:
    return f"{_frontend_base(request)}/signup?invite={token}"


def _send_invitation_email(invitation: Invitation, url: str) -> bool:
    inviter = invitation.invited_by.display_name if invitation.invited_by else "An admin"
    team = f" in the {invitation.team.name} workspace" if invitation.team else ""
    try:
        send_mail(
            subject="You're invited to TrackFlow",
            message=(
                f"{inviter} has invited you to join TrackFlow as {invitation.get_role_display().lower()}{team}.\n\n"
                f"Create your account here (the link works once and expires in {INVITATION_DAYS} days):\n{url}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
        )
        return True
    except Exception:  # SMTP down, SES not verified, …: the admin can still copy the link
        logger.warning("Could not send the invitation email to %s", invitation.email, exc_info=True)
        return False


class IsStaff(permissions.BasePermission):
    message = "Only an organisation admin can manage invitations."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class InvitationSerializer(serializers.ModelSerializer):
    team_id = serializers.PrimaryKeyRelatedField(
        source="team", queryset=Team.objects.all(), required=False, allow_null=True
    )
    team_name = serializers.CharField(source="team.name", read_only=True, default=None)
    invited_by_name = serializers.CharField(source="invited_by.display_name", read_only=True, default=None)
    status = serializers.SerializerMethodField()

    class Meta:
        model = Invitation
        fields = [
            "id", "email", "role", "team_id", "team_name", "invited_by_name", "status",
            "created_at", "sent_at", "expires_at", "accepted_at", "revoked_at",
        ]
        read_only_fields = ["created_at", "sent_at", "expires_at", "accepted_at", "revoked_at"]

    def get_status(self, obj) -> str:
        return obj.status_at(timezone.now())

    def validate_email(self, value):
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Someone with this email already has an account.")
        now = timezone.now()
        pending = Invitation.objects.filter(
            email__iexact=email, accepted_at__isnull=True, revoked_at__isnull=True, expires_at__gt=now
        )
        if pending.exists():
            raise serializers.ValidationError("This email already has a pending invitation. Resend it instead.")
        return email


def _with_link(request, invitation, token, email_sent) -> dict:
    return {**InvitationSerializer(invitation).data, "invite_url": invite_url(request, token), "email_sent": email_sent}


class InvitationListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/invitations/ — admins list and send invitations."""

    serializer_class = InvitationSerializer
    permission_classes = [IsStaff]
    pagination_class = None

    def get_queryset(self):
        return Invitation.objects.select_related("team", "invited_by")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        invitation = Invitation(**serializer.validated_data, invited_by=request.user)
        token = _issue_token(invitation)
        invitation.save()
        url = invite_url(request, token)
        return Response(_with_link(request, invitation, token, _send_invitation_email(invitation, url)), status=201)


class InvitationResendView(APIView):
    """POST /api/invitations/<id>/resend/ — a fresh link (the old one stops working) and 7 more days."""

    permission_classes = [IsStaff]

    def post(self, request, pk):
        invitation = generics.get_object_or_404(Invitation, pk=pk)
        if invitation.accepted_at or invitation.revoked_at:
            return Response({"detail": f"This invitation was {invitation.status_at(timezone.now())}."}, status=400)
        token = _issue_token(invitation)
        invitation.save(update_fields=["token_hash", "sent_at", "expires_at"])
        url = invite_url(request, token)
        return Response(_with_link(request, invitation, token, _send_invitation_email(invitation, url)))


class InvitationRevokeView(APIView):
    """POST /api/invitations/<id>/revoke/ — the link stops working."""

    permission_classes = [IsStaff]

    def post(self, request, pk):
        invitation = generics.get_object_or_404(Invitation, pk=pk)
        if invitation.accepted_at:
            return Response({"detail": "This invitation was already accepted."}, status=400)
        if not invitation.revoked_at:
            invitation.revoked_at = timezone.now()
            invitation.save(update_fields=["revoked_at"])
        return Response(InvitationSerializer(invitation).data)


def find_usable_invitation(token: str | None, *, lock: bool = False) -> tuple[Invitation | None, str | None]:
    """(invitation, None) when the token can be used now, else (None, reason)."""
    if not token:
        return None, "Sign-up is by invitation only. Ask an admin to invite you."
    qs = Invitation.objects.select_related("team", "invited_by")
    if lock:
        qs = qs.select_for_update()
    invitation = qs.filter(token_hash=hash_token(token)).first()
    if invitation is None:
        return None, "This invitation link isn't valid. It may have been replaced by a newer one."
    state = invitation.status_at(timezone.now())
    if state == "accepted":
        return None, "This invitation has already been used. Sign in instead."
    if state == "revoked":
        return None, "This invitation was withdrawn. Ask an admin for a new one."
    if state == "expired":
        return None, "This invitation has expired. Ask an admin to resend it."
    return invitation, None


class InvitationLookupView(APIView):
    """GET /api/auth/invitations/<token>/ — public: what the sign-up page shows for a link."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def get(self, request, token):
        invitation, problem = find_usable_invitation(token)
        if problem:
            return Response({"detail": problem}, status=status.HTTP_410_GONE)
        return Response(
            {
                "email": invitation.email,
                "role": invitation.role,
                "team_name": invitation.team.name if invitation.team else None,
                "invited_by_name": invitation.invited_by.display_name if invitation.invited_by else None,
                "expires_at": invitation.expires_at,
            }
        )


@transaction.atomic
def accept_invitation(invitation: Invitation, user: User) -> None:
    """Give the new account the invitation's role and team, and use the invitation up."""
    if invitation.role == Invitation.Role.ADMIN:
        user.is_staff = True
        user.save(update_fields=["is_staff"])
    if invitation.team_id:
        TeamMembership.objects.get_or_create(team_id=invitation.team_id, user=user)
    invitation.accepted_at = timezone.now()
    invitation.accepted_user = user
    invitation.save(update_fields=["accepted_at", "accepted_user"])
