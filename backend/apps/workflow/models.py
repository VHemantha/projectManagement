from django.db import models


class IssueType(models.Model):
    """System types (Epic/Story/Task/Bug/Sub-task) are seeded with project=null.
    Per-project custom types are a stretch goal, hence the nullable FK."""

    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="custom_issue_types"
    )
    name = models.CharField(max_length=50)
    icon = models.CharField(max_length=50, default="square")
    color = models.CharField(max_length=7, default="#0C66E4")
    is_subtask = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Workflow(models.Model):
    project = models.OneToOneField(
        "projects.Project", on_delete=models.CASCADE, related_name="workflow"
    )
    name = models.CharField(max_length=100, default="Default Workflow")

    def __str__(self):
        return f"{self.name} ({self.project.key})"


class WorkflowStatus(models.Model):
    class Category(models.TextChoices):
        TODO = "todo", "To do"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="statuses")
    name = models.CharField(max_length=50)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.TODO)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name_plural = "workflow statuses"

    def __str__(self):
        return self.name


class WorkflowTransition(models.Model):
    class ReassignRule(models.TextChoices):
        NO_CHANGE = "no_change", "No change"
        PREPARER = "preparer", "Set to preparer"
        REVIEWER = "reviewer", "Set to reviewer"
        ASSIGNEE = "assignee", "Set to assignee"

    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="transitions")
    name = models.CharField(max_length=50)
    from_status = models.ForeignKey(
        WorkflowStatus, null=True, blank=True, on_delete=models.CASCADE, related_name="transitions_from"
    )
    to_status = models.ForeignKey(
        WorkflowStatus, on_delete=models.CASCADE, related_name="transitions_to"
    )
    # Optional: on this transition, auto-set Issue.current_responsible. Purely additive —
    # transitions themselves are still unenforced (any status can move to any other), this
    # only fires a side effect when a transition row happens to match the status change made.
    set_current_responsible_to = models.CharField(
        max_length=20, choices=ReassignRule.choices, default=ReassignRule.NO_CHANGE
    )

    def __str__(self):
        src = self.from_status.name if self.from_status else "Any"
        return f"{src} -> {self.to_status.name}"


def _default_card_fields():
    # Cards show the job's value by default so it can be entered right on the board.
    return ["epic_tag", "story_points", "priority", "assignee", "job_value"]


class Board(models.Model):
    class BoardType(models.TextChoices):
        KANBAN = "kanban", "Kanban"
        SCRUM = "scrum", "Scrum"

    class CardColorRule(models.TextChoices):
        NONE = "none", "None"
        PRIORITY = "priority", "By priority"
        ISSUE_TYPE = "issue_type", "By issue type"
        LABEL = "label", "By label"
        DUE_DATE = "due_date", "By due date"

    class CardColorStyle(models.TextChoices):
        STRIPE = "stripe", "Left stripe"
        TINT = "tint", "Tinted card"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="boards")
    name = models.CharField(max_length=100)
    board_type = models.CharField(max_length=10, choices=BoardType.choices)
    # ordered list of {"name": str, "status_ids": [int, ...], "wip_limit": int|null,
    # "color": "#rrggbb"|null}
    column_config = models.JSONField(default=list)
    swimlane_mode = models.CharField(
        max_length=20,
        choices=[
            ("none", "None"),
            ("epic", "By Epic"),
            ("assignee", "By Assignee"),
            ("parent", "By Parent"),
        ],
        default="none",
    )
    # ordered list of field keys (e.g. "assignee", "story_points", "priority", "labels",
    # "due_date", "epic_tag", "current_responsible", "time_logged") rendered on card faces.
    card_fields = models.JSONField(default=_default_card_fields)
    card_color_rule = models.CharField(max_length=20, choices=CardColorRule.choices, default=CardColorRule.NONE)
    # Per-rule colour overrides, e.g. {"priority": {"high": "#e5493a"}, "issue_type": {"3": "#36b37e"},
    # "due_date": {"overdue": "#e5493a", "due_soon": "#ffab00", "on_track": "#36b37e"}}. Anything
    # not overridden falls back to the built-in colour for that value.
    card_colors = models.JSONField(default=dict, blank=True)
    card_color_style = models.CharField(
        max_length=10, choices=CardColorStyle.choices, default=CardColorStyle.STRIPE
    )
    filters = models.ForeignKey(
        "search.Filter", null=True, blank=True, on_delete=models.SET_NULL, related_name="boards"
    )

    def __str__(self):
        return f"{self.name} ({self.project.key})"
