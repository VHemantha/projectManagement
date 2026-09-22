from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.issues.models import Issue
from apps.issues.serializers import IssueMiniSerializer

from .models import DailyGoal


class DailyGoalSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    linked_issue = IssueMiniSerializer(read_only=True)
    linked_issue_id = serializers.PrimaryKeyRelatedField(
        source="linked_issue", queryset=Issue.objects.all(), write_only=True, required=False, allow_null=True
    )

    class Meta:
        model = DailyGoal
        fields = [
            "id",
            "user",
            "date",
            "text",
            "linked_issue",
            "linked_issue_id",
            "status",
            "note",
            "order",
            "carried_over_from",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["carried_over_from"]

    def validate(self, attrs):
        if attrs.get("status") == DailyGoal.Status.NOT_ACHIEVED and not (attrs.get("note") or getattr(self.instance, "note", "")):
            raise serializers.ValidationError(
                {"note": "A short note is required when marking a goal not achieved."}
            )
        return attrs
