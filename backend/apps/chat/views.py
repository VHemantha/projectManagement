from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.issues.models import Attachment, Issue
from apps.issues.serializers import AttachmentSerializer
from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_many
from apps.projects.models import ProjectMembership
from apps.teams.models import TeamMembership

from .consumers import group_name
from .models import Channel, ChannelMembership, Message, MessageIssueLink, MessageReaction
from .permissions import ensure_channel_membership, user_can_access_channel
from .serializers import ChannelMembershipSerializer, ChannelSerializer, MessageIssueLinkSerializer, MessageSerializer


def broadcast_message(channel_id, message_data):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(group_name(channel_id), {"type": "chat.message", "message": message_data})


def _accessible_channel_ids(user):
    project_ids = ProjectMembership.objects.filter(user=user).values_list("project_id", flat=True)
    team_ids = TeamMembership.objects.filter(user=user).values_list("team_id", flat=True)
    manual_ids = ChannelMembership.objects.filter(user=user).values_list("channel_id", flat=True)
    return Channel.objects.filter(
        Q(channel_type=Channel.ChannelType.GENERAL)
        | Q(channel_type=Channel.ChannelType.PROJECT, linked_project_id__in=project_ids)
        | Q(channel_type=Channel.ChannelType.PROJECT, linked_project__lead=user)
        | Q(channel_type=Channel.ChannelType.TEAM, linked_team_id__in=team_ids)
        | Q(id__in=manual_ids)
    ).distinct()


class ChannelListCreateView(generics.ListCreateAPIView):
    serializer_class = ChannelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = _accessible_channel_ids(self.request.user).filter(archived_at__isnull=True)
        return qs.order_by("channel_type", "name")

    def perform_create(self, serializer):
        from apps.orgs.models import Organization

        channel = serializer.save(
            organization=Organization.get_solo(),
            channel_type=self.request.data.get("channel_type", Channel.ChannelType.TOPIC),
            created_by=self.request.user,
        )
        ChannelMembership.objects.get_or_create(
            channel=channel, user=self.request.user, defaults={"role": ChannelMembership.Role.OWNER}
        )
        member_ids = self.request.data.get("member_ids", [])
        for uid in member_ids:
            ChannelMembership.objects.get_or_create(channel=channel, user_id=uid)


class ChannelDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ChannelSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Channel.objects.all()

    def get_object(self):
        channel = get_object_or_404(Channel, pk=self.kwargs["pk"])
        if not user_can_access_channel(self.request.user, channel):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You don't have access to this channel.")
        return channel


class ChannelMembersView(generics.ListAPIView):
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        channel = get_object_or_404(Channel, pk=self.kwargs["pk"])
        if channel.channel_type == Channel.ChannelType.PROJECT:
            ids = ProjectMembership.objects.filter(project=channel.linked_project).values_list("user_id", flat=True)
            return User.objects.filter(Q(id__in=ids) | Q(id=channel.linked_project.lead_id))
        if channel.channel_type == Channel.ChannelType.TEAM:
            ids = TeamMembership.objects.filter(team=channel.linked_team).values_list("user_id", flat=True)
            return User.objects.filter(id__in=ids)
        if channel.channel_type == Channel.ChannelType.GENERAL:
            return User.objects.filter(is_active=True)
        ids = ChannelMembership.objects.filter(channel=channel).values_list("user_id", flat=True)
        return User.objects.filter(id__in=ids)


class ChannelArchiveView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        channel = get_object_or_404(Channel, pk=pk)
        channel.archived_at = timezone.now()
        channel.save(update_fields=["archived_at"])
        return Response(ChannelSerializer(channel, context={"request": request}).data)


class ChannelMarkReadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        channel = get_object_or_404(Channel, pk=pk)
        membership = ensure_channel_membership(request.user, channel)
        membership.last_read_at = timezone.now()
        membership.save(update_fields=["last_read_at"])
        return Response({"detail": "ok"})


class MessageListCreateView(generics.ListCreateAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_channel(self):
        channel = get_object_or_404(Channel, pk=self.kwargs["pk"])
        if not user_can_access_channel(self.request.user, channel):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You don't have access to this channel.")
        return channel

    def get_queryset(self):
        qs = Message.objects.filter(channel=self.get_channel(), parent_message__isnull=True).select_related(
            "author"
        ).prefetch_related("reactions", "issue_links", "mentions")
        before = self.request.query_params.get("before")
        if before:
            qs = qs.filter(id__lt=before)
        limit = int(self.request.query_params.get("limit", 50))
        ids = list(qs.order_by("-created_at").values_list("id", flat=True)[:limit])
        return Message.objects.filter(id__in=ids).order_by("created_at")

    def perform_create(self, serializer):
        channel = self.get_channel()
        message = serializer.save(channel=channel, author=self.request.user)
        mentioned_ids = self.request.data.get("mentioned_user_ids", [])
        if mentioned_ids:
            from .models import MessageMention

            users = list(User.objects.filter(id__in=mentioned_ids))
            MessageMention.objects.bulk_create([MessageMention(message=message, mentioned_user=u) for u in users])
            notify_many(users, Notification.Verb.MENTIONED, actor=self.request.user, target_message=message)

        # Messages created over REST (e.g. the attachment-upload flow, which needs a
        # message id to exist before it can attach a file) don't go through the
        # WebSocket consumer, so broadcast them the same way it does — otherwise
        # other connected clients would only see them on next refetch.
        broadcast_message(channel.id, MessageSerializer(message).data)


class MessageAttachmentListCreateView(generics.ListCreateAPIView):
    serializer_class = AttachmentSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]
    pagination_class = None

    def get_message(self):
        message = get_object_or_404(Message, pk=self.kwargs["pk"])
        if not user_can_access_channel(self.request.user, message.channel):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("You don't have access to this channel.")
        return message

    def get_queryset(self):
        return Attachment.objects.filter(message=self.get_message())

    def perform_create(self, serializer):
        message = self.get_message()
        attachment = serializer.save(message=message, uploaded_by=self.request.user)
        broadcast_message(message.channel_id, MessageSerializer(message).data)
        return attachment


class MessageThreadRepliesView(generics.ListAPIView):
    serializer_class = MessageSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        parent = get_object_or_404(Message, pk=self.kwargs["pk"])
        return Message.objects.filter(parent_message=parent).select_related("author")


@api_view(["POST", "DELETE"])
@permission_classes([permissions.IsAuthenticated])
def toggle_reaction(request, pk=None):
    message = get_object_or_404(Message, pk=pk)
    emoji = request.data.get("emoji", "👍")
    if request.method == "POST":
        MessageReaction.objects.get_or_create(message=message, user=request.user, emoji=emoji)
    else:
        MessageReaction.objects.filter(message=message, user=request.user, emoji=emoji).delete()
    return Response(MessageSerializer(message).data)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def create_task_from_message(request, pk=None):
    from apps.issues.serializers import IssueDetailSerializer

    message = get_object_or_404(Message, pk=pk)
    payload = {**request.data}
    serializer = IssueDetailSerializer(data=payload, context={"request": request})
    serializer.is_valid(raise_exception=True)
    issue = serializer.save()

    MessageIssueLink.objects.create(message=message, issue=issue, created_task=True)
    system_message = Message.objects.create(
        channel=message.channel,
        author=request.user,
        body=_system_doc(f"✅ Created {issue.key}: {issue.summary}"),
        is_system=True,
    )
    MessageIssueLink.objects.create(message=system_message, issue=issue, created_task=True)

    return Response(
        {
            "issue": IssueDetailSerializer(issue, context={"request": request}).data,
            "system_message": MessageSerializer(system_message).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def link_task_to_message(request, pk=None):
    message = get_object_or_404(Message, pk=pk)
    issue = get_object_or_404(Issue, id=request.data.get("issue_id"))
    link, created = MessageIssueLink.objects.get_or_create(message=message, issue=issue, defaults={"created_task": False})
    return Response(MessageIssueLinkSerializer(link).data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


def _system_doc(text: str) -> dict:
    return {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}
