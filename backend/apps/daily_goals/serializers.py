from rest_framework import serializers

from apps.accounts.serializers import UserSerializer
from apps.issues.models import Issue
from apps.issues.serializers import IssueMiniSerializer

from .models import DailyGoal


def job_name(issue: Issue) -> str:
    """How a task reads in a plan: its sub-workspace, then its name ("ABC Ltd Preparation")."""
    client = getattr(issue.project, "client", None) if issue.project_id else None
    return f"{client.name} {issue.summary}" if client else issue.summary


class DailyGoalSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    linked_issue = IssueMiniSerializer(read_only=True)
    linked_issue_id = serializers.PrimaryKeyRelatedField(
        source="linked_issue", queryset=Issue.objects.all(), write_only=True, required=False, allow_null=True
    )
    # Blank with a task picked: the plan reads as the task's sub-workspace and name.
    text = serializers.CharField(max_length=300, required=False, allow_blank=True)
    planned_hours = serializers.FloatField(required=False, allow_null=True, min_value=0.25, max_value=24)
    sub_workspace = serializers.SerializerMethodField()
    task_done = serializers.SerializerMethodField()
    checked_by = UserSerializer(read_only=True)

    class Meta:
        model = DailyGoal
        fields = [
            "id",
            "user",
            "date",
            "text",
            "linked_issue",
            "linked_issue_id",
            "sub_workspace",
            "planned_hours",
            "complete_by",
            "task_done",
            "status",
            "note",
            "order",
            "carried_over_from",
            "lead_check",
            "checked_by",
            "checked_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["carried_over_from", "lead_check", "checked_at"]

    def get_sub_workspace(self, obj):
        issue = obj.linked_issue
        client = getattr(issue.project, "client", None) if issue and issue.project_id else None
        return client.name if client else None

    def get_task_done(self, obj):
        """The linked task's own record: finished (in a done stage), and when."""
        issue = obj.linked_issue
        if not issue or issue.status.category != "done":
            return None
        return (issue.resolved_at or issue.updated_at).date().isoformat()

    def validate(self, attrs):
        if attrs.get("status") == DailyGoal.Status.NOT_ACHIEVED and not (attrs.get("note") or getattr(self.instance, "note", "")):
            raise serializers.ValidationError(
                {"note": "A short note is required when marking a goal not achieved."}
            )
        issue = attrs.get("linked_issue", getattr(self.instance, "linked_issue", None))
        text = attrs.get("text", getattr(self.instance, "text", "")).strip()
        if not text:
            if not issue:
                raise serializers.ValidationError({"text": "Say what you plan to do, or pick a task."})
            attrs["text"] = job_name(issue)[:300]
        day = attrs.get("date", getattr(self.instance, "date", None))
        complete_by = attrs.get("complete_by", getattr(self.instance, "complete_by", None))
        if day and complete_by and complete_by < day:
            raise serializers.ValidationError({"complete_by": "The completion date can't be before the plan's day."})
        return attrs
