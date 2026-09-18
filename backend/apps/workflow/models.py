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
        TODO = "todo", "To Do"
        IN_PROGRESS = "in_progress", "In Progress"
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
    workflow = models.ForeignKey(Workflow, on_delete=models.CASCADE, related_name="transitions")
    name = models.CharField(max_length=50)
    from_status = models.ForeignKey(
        WorkflowStatus, null=True, blank=True, on_delete=models.CASCADE, related_name="transitions_from"
    )
    to_status = models.ForeignKey(
        WorkflowStatus, on_delete=models.CASCADE, related_name="transitions_to"
    )

    def __str__(self):
        src = self.from_status.name if self.from_status else "Any"
        return f"{src} -> {self.to_status.name}"


class Board(models.Model):
    class BoardType(models.TextChoices):
        KANBAN = "kanban", "Kanban"
        SCRUM = "scrum", "Scrum"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="boards")
    name = models.CharField(max_length=100)
    board_type = models.CharField(max_length=10, choices=BoardType.choices)
    # ordered list of {"name": str, "status_ids": [int, ...], "wip_limit": int|null}
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

    def __str__(self):
        return f"{self.name} ({self.project.key})"
