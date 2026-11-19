"""Password reset by email (AFIT, 18 Nov 2026).

Someone who can't sign in asks for a link on /forgot-password; an admin can also send one
(`manage.py send_password_reset <email>`). The link is /reset-password?uid=<id>&token=<token>, made
with Django's password-reset token generator: it works once (setting the password, or signing in,
invalidates it) and expires after PASSWORD_RESET_TIMEOUT (3 days by default). The request always
answers the same way, so it never tells anyone whether an email has an account.
"""
import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import User

logger = logging.getLogger(__name__)

SENT = "If that email has an account, a link to set a new password is on its way. It works once and expires in 3 days."


def _frontend_base(request=None) -> str:
    configured = getattr(settings, "FRONTEND_URL", "")
    if configured:
        return configured.rstrip("/")
    if request is not None:
        origin = request.headers.get("Origin")
        return (origin or request.build_absolute_uri("/")).rstrip("/")
    return ""


def reset_url(user: User, request=None) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return f"{_frontend_base(request)}/reset-password?uid={uid}&token={default_token_generator.make_token(user)}"


def can_reset(user: User | None) -> bool:
    return bool(user and user.is_active and not getattr(user, "is_agent", False))


def send_reset_email(user: User, request=None) -> bool:
    """Email the user a link to set a new password. False when the email couldn't be sent."""
    days = max(1, round(getattr(settings, "PASSWORD_RESET_TIMEOUT", 259200) / 86400))
    try:
        send_mail(
            subject="Set your TASKO password",
            message=(
                f"Hi {user.display_name or user.email},\n\n"
                f"Use this link to set a new password for your TASKO account ({user.email}). "
                f"It works once and expires in {days} days:\n{reset_url(user, request)}\n\n"
                "If you didn't ask for this, you can ignore this email: your password stays as it is.\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
        )
        return True
    except Exception:  # SMTP down, SES not verified, ...
        logger.warning("Could not send the password reset email to %s", user.email, exc_info=True)
        return False


class ResetRequestThrottle(AnonRateThrottle):
    scope = "password_reset"
    rate = "5/hour"


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/ {email} - public; always the same answer."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ResetRequestThrottle]

    def post(self, request):
        email = str(request.data.get("email") or "").strip()
        if not email:
            return Response({"email": ["Enter your email."]}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(email__iexact=email).first()
        if can_reset(user):
            send_reset_email(user, request)
        return Response({"detail": SENT})


def user_for(uid: str, token: str) -> User | None:
    try:
        user = User.objects.filter(pk=int(force_str(urlsafe_base64_decode(uid or "")))).first()
    except (TypeError, ValueError, OverflowError):
        return None
    if can_reset(user) and default_token_generator.check_token(user, token or ""):
        return user
    return None


class _ConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True)


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset/confirm/ {uid, token, password} - sets the new password."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [ResetRequestThrottle]

    def post(self, request):
        s = _ConfirmSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        user = user_for(s.validated_data["uid"], s.validated_data["token"])
        if user is None:
            return Response({"detail": "This link isn't valid any more: it has been used or has expired. Ask for a new one."},
                            status=status.HTTP_410_GONE)
        try:
            validate_password(s.validated_data["password"], user)
        except Exception as exc:  # django.core.exceptions.ValidationError
            return Response({"password": list(getattr(exc, "messages", [str(exc)]))}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(s.validated_data["password"])
        user.save(update_fields=["password"])
        return Response({"detail": "Your password is set. Log in with it now.", "email": user.email})
