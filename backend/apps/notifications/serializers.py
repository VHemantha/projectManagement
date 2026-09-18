from rest_framework import serializers

from apps.accounts.serializers import UserSerializer

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    actor = UserSerializer(read_only=True)
    target_issue_key = serializers.CharField(source="target_issue.key", read_only=True, default=None)
    target_issue_summary = serializers.CharField(source="target_issue.summary", read_only=True, default=None)
    target_project_key = serializers.CharField(source="target_issue.project.key", read_only=True, default=None)
    target_channel_id = serializers.IntegerField(source="target_message.channel_id", read_only=True, default=None)
    target_channel_name = serializers.CharField(source="target_message.channel.name", read_only=True, default=None)

    class Meta:
        model = Notification
        fields = [
            "id",
            "actor",
            "verb",
            "target_issue_key",
            "target_issue_summary",
            "target_project_key",
            "target_channel_id",
            "target_channel_name",
            "is_read",
            "created_at",
        ]
