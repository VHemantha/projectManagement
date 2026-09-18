from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.issues.serializers import IssueMiniSerializer

from .models import Channel, ChannelMembership, Message, MessageIssueLink, MessageMention, MessageReaction


class ChannelMembershipSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = ChannelMembership
        fields = ["id", "user", "role", "muted", "last_read_at", "notification_preference", "joined_at"]


class ChannelSerializer(serializers.ModelSerializer):
    unread_count = serializers.SerializerMethodField()
    project_key = serializers.CharField(source="linked_project.key", read_only=True, default=None)
    team_id = serializers.IntegerField(source="linked_team_id", read_only=True, default=None)

    class Meta:
        model = Channel
        fields = [
            "id",
            "name",
            "description",
            "channel_type",
            "linked_project",
            "project_key",
            "linked_team",
            "team_id",
            "is_private",
            "created_by",
            "created_at",
            "archived_at",
            "unread_count",
        ]
        read_only_fields = ["created_by", "archived_at"]

    def get_unread_count(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return 0
        membership = obj.memberships.filter(user=request.user).first()
        qs = obj.messages.all()
        if membership and membership.last_read_at:
            qs = qs.filter(created_at__gt=membership.last_read_at)
        return qs.count()


class MessageReactionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = MessageReaction
        fields = ["id", "user", "emoji"]


class MessageIssueLinkSerializer(serializers.ModelSerializer):
    issue = IssueMiniSerializer(read_only=True)

    class Meta:
        model = MessageIssueLink
        fields = ["id", "issue", "created_task", "created_at"]


class IssueChatLinkSerializer(serializers.ModelSerializer):
    """Used by the issue activity feed to surface chat messages linked to that issue —
    the reverse direction of MessageIssueLinkSerializer (issue -> its linked messages)."""

    message_id = serializers.IntegerField(source="message.id", read_only=True)
    channel_id = serializers.IntegerField(source="message.channel_id", read_only=True)
    channel_name = serializers.CharField(source="message.channel.name", read_only=True)
    author = UserSerializer(source="message.author", read_only=True)
    body = serializers.JSONField(source="message.body", read_only=True)
    created_at = serializers.DateTimeField(source="message.created_at", read_only=True)

    class Meta:
        model = MessageIssueLink
        fields = ["id", "message_id", "channel_id", "channel_name", "author", "body", "created_at", "created_task"]


class MessageMentionSerializer(serializers.ModelSerializer):
    mentioned_user = UserSerializer(read_only=True)

    class Meta:
        model = MessageMention
        fields = ["id", "mentioned_user"]


class MessageSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    reactions = MessageReactionSerializer(many=True, read_only=True)
    issue_links = MessageIssueLinkSerializer(many=True, read_only=True)
    mentions = MessageMentionSerializer(many=True, read_only=True)
    reply_count = serializers.IntegerField(source="replies.count", read_only=True)
    attachments = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "channel",
            "author",
            "body",
            "created_at",
            "edited_at",
            "parent_message",
            "pinned",
            "is_system",
            "reactions",
            "issue_links",
            "mentions",
            "reply_count",
            "attachments",
        ]
        read_only_fields = ["channel", "author", "created_at", "edited_at", "is_system"]

    def get_attachments(self, obj):
        from apps.issues.serializers import AttachmentSerializer

        return AttachmentSerializer(obj.attachments.all(), many=True).data
