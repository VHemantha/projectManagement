from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import User
from apps.accounts.serializers import UserSerializer
from apps.clients.models import Client
from apps.clients.services import get_or_create_client_workspace
from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_many
from apps.projects.keys import resolve_project
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
    "is_archived",
]


class ProjectKeyField(serializers.SlugRelatedField):
    """A project by key, ignoring case and accepting old keys after a rename."""

    def __init__(self, **kwargs):
        super().__init__(slug_field="key", queryset=Project.objects.all(), **kwargs)

    def to_internal_value(self, data):
        project = resolve_project(str(data))
        if project is None:
            self.fail("does_not_exist", slug_name=self.slug_field, value=str(data))
        return project


def actual_hours_of(issue) -> float:
    """Hours logged against a job in timesheets. Uses the list/detail queryset's
    `actual_duration` annotation when present (one query for a whole list)."""
    if hasattr(issue, "actual_duration"):
        duration = issue.actual_duration
        return round(duration.total_seconds() / 3600, 2) if duration else 0.0
    from apps.timesheets.budget import issue_actual_hours

    return issue_actual_hours(issue.id)


def set_archived(queryset, archived: bool) -> int:
    """Archive or restore jobs in bulk (bulk update: tells open views itself)."""
    from apps.live.broadcast import notify as live_notify

    projects = set(queryset.values_list("project__key", flat=True))
    count = queryset.update(is_archived=archived, archived_at=timezone.now() if archived else None)
    for key in projects:
        live_notify("issues", project=key)
    return count


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
    project_name = serializers.CharField(source="project.name", read_only=True)
    actual_hours = serializers.SerializerMethodField()
    # The job's value is shown (and edited) on cards in its project's currency.
    value_currency = serializers.CharField(source="project.job_value_currency", read_only=True)

    def get_actual_hours(self, obj):
        return actual_hours_of(obj)

    class Meta:
        model = Issue
        fields = [
            "id",
            "key",
            "project_key",
            "project_name",
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
            "budgeted_hours",
            "actual_hours",
            "allocated_value",
            "value_currency",
            "is_archived",
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
    project = ProjectKeyField(required=False)
    project_name = serializers.CharField(source="project.name", read_only=True)
    # Create-only: a job for a client that doesn't require projects, without a project (it goes
    # into the client's automatic job list). Ignored when `project` is given.
    client_id = serializers.PrimaryKeyRelatedField(
        queryset=Client.objects.all(), write_only=True, required=False, allow_null=True
    )
    actual_hours = serializers.SerializerMethodField()
    time_by_user = serializers.SerializerMethodField()
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
            "project_name",
            "client_id",
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
            "actual_hours",
            "time_by_user",
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
            "is_archived",
            "archived_at",
            "rank",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = ["key", "rank", "archived_at"]

    def get_actual_hours(self, obj):
        return actual_hours_of(obj)

    def get_time_by_user(self, obj):
        """Logged hours per person, most first — who the actual time came from."""
        from django.db.models import Sum

        rows = (
            obj.time_entries.exclude(duration__isnull=True)
            .values("user_id", "user__display_name")
            .annotate(total=Sum("duration"))
            .order_by("-total")
        )
        return [
            {"user_id": r["user_id"], "display_name": r["user__display_name"], "hours": round(r["total"].total_seconds() / 3600, 2)}
            for r in rows
        ]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        client = attrs.pop("client_id", None)
        if self.instance is None and not attrs.get("project"):
            if client is None:
                raise serializers.ValidationError({"project": "Choose a project, or a client to add the job to."})
            if client.requires_projects:
                raise serializers.ValidationError(
                    {"project": f"Jobs for {client.name} must belong to one of its projects — choose a project."}
                )
            attrs["project"] = get_or_create_client_workspace(client, self.context["request"].user)
        return attrs

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
                # New issues start in the board's first column, so they're always visible on it
                # even after columns are reordered or the original first status is unmapped.
                default_status = None
                board = project.boards.order_by("id").first()
                first_column = board.column_config[0] if board and board.column_config else None
                if first_column and first_column.get("status_ids"):
                    default_status = workflow.statuses.filter(id=first_column["status_ids"][0]).first()
                default_status = default_status or workflow.statuses.order_by("order").first()
                if default_status:
                    validated_data["status"] = default_status
        last = Issue.objects.filter(project=project).order_by("-rank").first()
        if last:
            validated_data["rank"] = rank_after(last.rank)
        return super().create(validated_data)

    @transaction.atomic
    def update(self, instance, validated_data):
        request = self.context["request"]
        if "is_archived" in validated_data and validated_data["is_archived"] != instance.is_archived:
            validated_data["archived_at"] = timezone.now() if validated_data["is_archived"] else None
            set_archived(instance.subtasks.all(), validated_data["is_archived"])
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
