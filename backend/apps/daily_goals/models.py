from django.conf import settings
from django.db import models


class DailyGoal(models.Model):
    """A lightweight daily-planning commitment, not a performance-scoring system — no numeric
    score, no ranking of members. Framed around visibility and accountability-through-
    transparency ('did we do what we said we'd do today')."""

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        ACHIEVED = "achieved", "Achieved"
        NOT_ACHIEVED = "not_achieved", "Not achieved"
        CARRIED_OVER = "carried_over", "Carried over"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="daily_goals")
    date = models.DateField()
    text = models.CharField(max_length=300)
    linked_issue = models.ForeignKey(
        "issues.Issue", null=True, blank=True, on_delete=models.SET_NULL, related_name="daily_goals"
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLANNED)
    # The "why not" note is what makes the team-leader rollup useful instead of just a checkbox.
    note = models.CharField(max_length=500, blank=True)
    order = models.PositiveIntegerField(default=0)
    # When a not-achieved goal is carried to tomorrow, the new row links back here so the team
    # leader view can show a streak of a goal being repeatedly missed rather than it vanishing.
    carried_over_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="carried_over_to"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.user} - {self.date}: {self.text[:40]}"
