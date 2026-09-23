from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_many
from apps.projects.models import Component, Label, Project, Version
from apps.sprints.models import Sprint
from apps.teams.models import TeamMembership
from apps.workflow.models import IssueType, WorkflowStatus, WorkflowTransition
from apps.workflow.serializers import IssueTypeSerializer, WorkflowStatusSerializer

from .models import Attachment, Comment, Issue, IssueHistory, IssueLink, Watcher
from .rank import rank_after

FIELD_DISPLAY_ATTR = {
    "status": "name",
    "assignee": "display_name",
    "preparer": "display_name",
    "reviewer": "display_name",
    "current_responsible": "display_name",
    "epic": "key",
    "parent": "key",
    "sprint": "name",
}


def _display_value(field, value):
    if value is None:
        return ""
    attr = FIELD_DISPLAY_ATTR.get(field)
    return str(getattr(value, attr)) if attr else str(value)


HISTORY_TRACKED_FIELDS = [
    "summary",
    "status",
    "priority",
    "assignee",
    "preparer",
    "reviewer",
    "current_responsible",
    "epic",
    "parent",
    "sprint",
    "story_points",
    "due_date",
]


def _apply_transition_reassignment(instance, old_status):
    """If a WorkflowTransition matching (old_status -> instance.status) has an auto-reassign
    rule configured, apply it to current_responsible. Transitions themselves are still
    unenforced (any status can move to any other) — this only fires a side effect when a
    transition row happens to match; it's a no-op when none does, so it can never block a
    status change that already worked before this addendum."""
    old_status_id = getattr(old_status, "id", None)
    if old_status_id == instance.status_id:
        return
    workflow = getattr(instance.project, "workflow", None)
    if not workflow:
        return
    transition = (
        WorkflowTransition.objects.filter(workflow=workflow, to_status_id=instance.status_id)
        .filter(Q(from_status=old_status) | Q(from_status__isnull=True))
        .exclude(set_current_responsible_to=WorkflowTransition.ReassignRule.NO_CHANGE)
        .order_by("-from_status_id")  # an exact from-status match beats an "any status" wildcard
        .first()
    )
    if not transition:
        return
    new_responsible = {
        WorkflowTransition.ReassignRule.PREPARER: instance.preparer,
        WorkflowTransition.ReassignRule.REVIEWER: instance.reviewer,
        WorkflowTransition.ReassignRule.ASSIGNEE: instance.assignee,
    }.get(transition.set_current_responsible_to)
    if new_responsible and new_responsible != instance.current_responsible:
        instance.current_responsible = new_responsible
        instance.save(update_fields=["current_responsible"])


class LabelMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Label
        fields = ["id", "name", "color"]


class EpicMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Issue
        fields = ["id", "key", "epic_name", "epic_color"]


class SprintMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sprint
        fields = ["id", "name", "state"]


class IssueMiniSerializer(serializers.ModelSerializer):
    """Compact shape used for sub-task lists, linked issues, etc."""

    issue_type = IssueTypeSerializer(read_only=True)
    status = WorkflowStatusSerializer(read_only=True)
    assignee = UserSerializer(read_only=True)

    class Meta:
        model = Issue
        fields = ["id", "key", "summary", "issue_type", "status", "assignee", "priority"]


class IssueListSerializer(serializers.ModelSerializer):
    issue_type = IssueTypeSerializer(read_only=True)
    status = WorkflowStatusSerializer(read_only=True)
    assignee = UserSerializer(read_only=True)
    reporter = UserSerializer(read_only=True)
    preparer = UserSerializer(read_only=True)
    reviewer = UserSerializer(read_only=True)
    current_responsible = UserSerializer(read_only=True)
    epic = EpicMiniSerializer(read_only=True)
    sprint = SprintMiniSerializer(read_only=True)
    labels = LabelMiniSerializer(many=True, read_only=True)
    project_key = serializers.CharField(source="project.key", read_only=True)

    class Meta:
        model = Issue
        fields = [
            "id",
            "key",
            "project_key",
            "summary",
            "issue_type",
            "status",
            "priority",
            "assignee",
            "reporter",
            "preparer",
            "reviewer",
            "current_responsible",
            "epic",
            "parent_id",
            "sprint",
            "story_points",
            "start_date",
            "due_date",
            "labels",
            "rank",
            "created_at",
            "updated_at",
            "resolved_at",
        ]


class IssueDetailSerializer(serializers.ModelSerializer):
    issue_type = IssueTypeSerializer(read_only=True)
    issue_type_id = serializers.PrimaryKeyRelatedField(
        source="issue_type", queryset=IssueType.objects.all(), write_only=True
    )
    status = WorkflowStatusSerializer(read_only=True)
    status_id = serializers.PrimaryKeyRelatedField(
        source="status", queryset=WorkflowStatus.objects.all(), write_only=True, required=False
    )
    assignee = UserSerializer(read_only=True)
    assignee_id = serializers.PrimaryKeyRelatedField(
        source="assignee", queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    reporter = UserSerializer(read_only=True)
    reporter_id = serializers.PrimaryKeyRelatedField(
        source="reporter", queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    preparer = UserSerializer(read_only=True)
    preparer_id = serializers.PrimaryKeyRelatedField(
        source="preparer", queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    reviewer = UserSerializer(read_only=True)
    reviewer_id = serializers.PrimaryKeyRelatedField(
        source="reviewer", queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    current_responsible = UserSerializer(read_only=True)
    current_responsible_id = serializers.PrimaryKeyRelatedField(
        source="current_responsible", queryset=User.objects.all(), write_only=True, required=False, allow_null=True
    )
    epic = EpicMiniSerializer(read_only=True)
    epic_id = serializers.PrimaryKeyRelatedField(
        source="epic", queryset=Issue.objects.filter(issue_type__name="Epic"),
        write_only=True, required=False, allow_null=True,
    )
    parent = IssueMiniSerializer(read_only=True)
    parent_id = serializers.PrimaryKeyRelatedField(
        source="parent", queryset=Issue.objects.all(), write_only=True, required=False, allow_null=True
    )
    sprint = SprintMiniSerializer(read_only=True)
    sprint_id = serializers.PrimaryKeyRelatedField(
        source="sprint", queryset=Sprint.objects.all(), write_only=True, required=False, allow_null=True
    )
    project = serializers.SlugRelatedField(slug_field="key", queryset=Project.objects.all())
    labels = LabelMiniSerializer(many=True, read_only=True)
    label_ids = serializers.PrimaryKeyRelatedField(
        source="labels", queryset=Label.objects.all(), many=True, write_only=True, required=False
    )
    components = serializers.SerializerMethodField()
    component_ids = serializers.PrimaryKeyRelatedField(
        source="components", queryset=Component.objects.all(), many=True, write_only=True, required=False
    )
    fix_versions = serializers.SerializerMethodField()
    fix_version_ids = serializers.PrimaryKeyRelatedField(
        source="fix_versions", queryset=Version.objects.all(), many=True, write_only=True, required=False
    )
    subtasks = IssueMiniSerializer(many=True, read_only=True)
    watcher_count = serializers.IntegerField(source="watchers.count", read_only=True)
    is_watching = serializers.SerializerMethodField()

    class Meta:
        model = Issue
        fields = [
            "id",
            "key",
            "project",
            "summary",
            "description",
            "issue_type",
            "issue_type_id",
            "status",
            "status_id",
            "priority",
            "assignee",
            "assignee_id",
            "reporter",
            "reporter_id",
            "preparer",
            "preparer_id",
            "reviewer",
            "reviewer_id",
            "current_responsible",
            "current_responsible_id",
            "epic",
            "epic_id",
            "epic_name",
            "epic_color",
            "parent",
            "parent_id",
            "sprint",
            "sprint_id",
            "story_points",
            "budgeted_hours",
            "allocated_value",
            "original_estimate",
            "time_spent",
            "start_date",
            "due_date",
            "labels",
            "label_ids",
            "components",
            "component_ids",
            "fix_versions",
            "fix_version_ids",
            "subtasks",
            "watcher_count",
            "is_watching",
            "rank",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = ["key", "rank"]

    def get_components(self, obj):
        return [{"id": c.id, "name": c.name} for c in obj.components.all()]

    def get_fix_versions(self, obj):
        return [{"id": v.id, "name": v.name} for v in obj.fix_versions.all()]

    def get_is_watching(self, obj):
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        return obj.watcher_rows.filter(user=request.user).exists()

    def create(self, validated_data):
        request = self.context["request"]
        project = validated_data["project"]
        if "reporter" not in validated_data:
            team_lead = None
            if project.primary_team_id:
                membership = TeamMembership.objects.filter(
                    team_id=project.primary_team_id, role=TeamMembership.Role.LEAD
                ).first()
                if membership:
                    team_lead = membership.user
            validated_data["reporter"] = team_lead or request.user
        validated_data.setdefault("preparer", request.user)
        validated_data.setdefault("current_responsible", validated_data.get("preparer"))
        if "status" not in validated_data:
            workflow = getattr(project, "workflow", None)
            if workflow:
                default_status = workflow.statuses.order_by("order").first()
                if default_status:
                    validated_data["status"] = default_status
        last = Issue.objects.filter(project=project).order_by("-rank").first()
        if last:
            validated_data["rank"] = rank_after(last.rank)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context["request"]
        old_values = {f: getattr(instance, f) for f in HISTORY_TRACKED_FIELDS}
        old_status = instance.status if instance.status_id else None
        was_done = instance.status.category == "done" if instance.status_id else False

        instance = super().update(instance, validated_data)
        _apply_transition_reassignment(instance, old_status)

        history_rows = []
        for field in HISTORY_TRACKED_FIELDS:
            old = old_values[field]
            new = getattr(instance, field)
            if old != new:
                history_rows.append(
                    IssueHistory(
                        issue=instance,
                        user=request.user,
                        field_changed=field,
                        old_value=_display_value(field, old),
                        new_value=_display_value(field, new),
                    )
                )
        if history_rows:
            IssueHistory.objects.bulk_create(history_rows)

        if instance.assignee and old_values["assignee"] != instance.assignee:
            notify(instance.assignee, Notification.Verb.ASSIGNED, actor=request.user, target_issue=instance)

        if old_values["status"] != instance.status:
            watcher_ids = instance.watcher_rows.exclude(user=request.user).values_list("user", flat=True)
            notify_many(
                User.objects.filter(id__in=watcher_ids),
                Notification.Verb.STATUS_CHANGED,
                actor=request.user,
                target_issue=instance,
            )

        now_done = instance.status.category == "done"
        if now_done and not was_done and not instance.resolved_at:
            instance.resolved_at = timezone.now()
            instance.save(update_fields=["resolved_at"])
        elif not now_done and was_done:
            instance.resolved_at = None
            instance.save(update_fields=["resolved_at"])

        return instance


class CommentSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "author", "body", "created_at", "updated_at"]


class AttachmentSerializer(serializers.ModelSerializer):
    uploaded_by = UserSerializer(read_only=True)

    class Meta:
        model = Attachment
        fields = ["id", "file", "filename", "uploaded_by", "uploaded_at"]


class IssueLinkSerializer(serializers.ModelSerializer):
    target_issue = IssueMiniSerializer(read_only=True)
    target_issue_id = serializers.PrimaryKeyRelatedField(
        source="target_issue", queryset=Issue.objects.all(), write_only=True
    )

    class Meta:
        model = IssueLink
        fields = ["id", "link_type", "target_issue", "target_issue_id", "created_at"]


class IssueHistorySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = IssueHistory
        fields = ["id", "user", "field_changed", "old_value", "new_value", "timestamp"]


class RecentActivitySerializer(IssueHistorySerializer):
    issue_key = serializers.CharField(source="issue.key", read_only=True)
    issue_summary = serializers.CharField(source="issue.summary", read_only=True)
    project_key = serializers.CharField(source="issue.project.key", read_only=True)

    class Meta(IssueHistorySerializer.Meta):
        fields = IssueHistorySerializer.Meta.fields + ["issue_key", "issue_summary", "project_key"]
