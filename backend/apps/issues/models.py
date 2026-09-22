from django.conf import settings
from django.db import models, transaction

from .rank import rank_first


class ProjectIssueCounter(models.Model):
    """Per-project sequential counter for issue keys (PROJECTKEY-N)."""

    project = models.OneToOneField(
        "projects.Project", on_delete=models.CASCADE, related_name="issue_counter"
    )
    last_number = models.PositiveIntegerField(default=0)

    @classmethod
    def next_number(cls, project) -> int:
        with transaction.atomic():
            counter, _ = cls.objects.select_for_update().get_or_create(project=project)
            counter.last_number += 1
            counter.save(update_fields=["last_number"])
            return counter.last_number


class Issue(models.Model):
    class Priority(models.TextChoices):
        HIGHEST = "highest", "Highest"
        HIGH = "high", "High"
        MEDIUM = "medium", "Medium"
        LOW = "low", "Low"
        LOWEST = "lowest", "Lowest"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="issues")
    # PROJECTKEY-N — project keys can now be up to 100 chars, so this needs enough headroom
    # for the longest key plus "-" plus a large issue number.
    key = models.CharField(max_length=120, unique=True, editable=False)
    issue_type = models.ForeignKey("workflow.IssueType", on_delete=models.PROTECT, related_name="issues")
    summary = models.CharField(max_length=500)
    description = models.JSONField(null=True, blank=True)

    status = models.ForeignKey("workflow.WorkflowStatus", on_delete=models.PROTECT, related_name="issues")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)

    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_issues"
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reported_issues"
    )

    # RACI-style roles layered on top of assignee/reporter (not replacing them): preparer is
    # who drafted the work, reviewer is who's expected to review it, current_responsible is
    # "whoever currently has the ball" and is meant to move as the issue goes through review
    # (see WorkflowTransition.set_current_responsible_to), unlike assignee which stays fixed.
    preparer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="prepared_issues"
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="review_issues"
    )
    current_responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="responsible_for_issues"
    )

    # An Epic is just an Issue with issue_type=Epic; these two fields carry epic-only data.
    epic_name = models.CharField(max_length=150, blank=True)
    epic_color = models.CharField(max_length=7, blank=True, default="#8777D9")

    epic = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="epic_children"
    )
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="subtasks"
    )
    sprint = models.ForeignKey(
        "sprints.Sprint", null=True, blank=True, on_delete=models.SET_NULL, related_name="issues"
    )

    story_points = models.FloatField(null=True, blank=True)
    # Optional issue-level budget override, for teams that want granularity below the
    # project-level Project.budgeted_hours/job_value. Both nullable — most teams only set the
    # project-level figures and never touch these.
    budgeted_hours = models.FloatField(null=True, blank=True)
    allocated_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    original_estimate = models.DurationField(null=True, blank=True)
    time_spent = models.DurationField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    labels = models.ManyToManyField("projects.Label", blank=True, related_name="issues")
    components = models.ManyToManyField("projects.Component", blank=True, related_name="issues")
    fix_versions = models.ManyToManyField("projects.Version", blank=True, related_name="issues")
    watchers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="Watcher", blank=True, related_name="watched_issues"
    )

    rank = models.CharField(max_length=100, default=rank_first, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["rank"]
        indexes = [models.Index(fields=["project", "status"])]

    def __str__(self):
        return f"{self.key} {self.summary}"

    def save(self, *args, **kwargs):
        if not self.key:
            number = ProjectIssueCounter.next_number(self.project)
            self.key = f"{self.project.key}-{number}"
        super().save(*args, **kwargs)


class Comment(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="comments")
    body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.author} on {self.issue.key}"


def attachment_upload_path(instance, filename):
    if instance.issue_id:
        return f"attachments/{instance.issue.project.key}/{instance.issue.key}/{filename}"
    if instance.message_id:
        return f"attachments/chat/{instance.message.channel_id}/{filename}"
    # Neither parent set: let the DB CheckConstraint reject the save with a clear
    # IntegrityError instead of crashing here on an AttributeError first.
    return f"attachments/unassigned/{filename}"


class Attachment(models.Model):
    """Belongs to exactly one of `issue` or `message` (chat attachments reuse this same
    model/upload pipeline rather than duplicating it — see apps.chat.models.Message)."""

    issue = models.ForeignKey(Issue, null=True, blank=True, on_delete=models.CASCADE, related_name="attachments")
    message = models.ForeignKey(
        "chat.Message", null=True, blank=True, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(upload_to=attachment_upload_path)
    filename = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attachments")
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(issue__isnull=False, message__isnull=True)
                    | models.Q(issue__isnull=True, message__isnull=False)
                ),
                name="attachment_belongs_to_exactly_one_parent",
            )
        ]

    def save(self, *args, **kwargs):
        if not self.filename and self.file:
            self.filename = self.file.name.split("/")[-1]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.filename


class IssueLink(models.Model):
    class LinkType(models.TextChoices):
        BLOCKS = "blocks", "blocks"
        IS_BLOCKED_BY = "is_blocked_by", "is blocked by"
        RELATES_TO = "relates_to", "relates to"
        DUPLICATES = "duplicates", "duplicates"
        CLONES = "clones", "clones"

    source_issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="outgoing_links")
    target_issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="incoming_links")
    link_type = models.CharField(max_length=20, choices=LinkType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("source_issue", "target_issue", "link_type")

    def __str__(self):
        return f"{self.source_issue.key} {self.link_type} {self.target_issue.key}"


class IssueHistory(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="history")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    field_changed = models.CharField(max_length=50)
    old_value = models.TextField(blank=True, null=True)
    new_value = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name_plural = "issue history"

    def __str__(self):
        return f"{self.issue.key}: {self.field_changed} changed"


class Watcher(models.Model):
    issue = models.ForeignKey(Issue, on_delete=models.CASCADE, related_name="watcher_rows")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="watcher_rows")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("issue", "user")
