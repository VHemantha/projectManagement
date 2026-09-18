from django.db import models


class Sprint(models.Model):
    class State(models.TextChoices):
        FUTURE = "future", "Future"
        ACTIVE = "active", "Active"
        CLOSED = "closed", "Closed"

    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="sprints")
    name = models.CharField(max_length=100)
    goal = models.TextField(blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=10, choices=State.choices, default=State.FUTURE)
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.name} ({self.project.key})"
