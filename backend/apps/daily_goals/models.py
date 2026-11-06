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
    # The morning plan (AFIT, 1 Nov 2026): the hours set aside for it today, and the day the job is
    # to be finished ("ABC Ltd Preparation, 7h today, completion tomorrow").
    planned_hours = models.FloatField(null=True, blank=True)
    complete_by = models.DateField(null=True, blank=True)
    # The "why not" note is what makes the team-leader rollup useful instead of just a checkbox.
    note = models.CharField(max_length=500, blank=True)
    order = models.PositiveIntegerField(default=0)
    # When a not-achieved goal is carried to tomorrow, the new row links back here so the team
    # leader view can show a streak of a goal being repeatedly missed rather than it vanishing.
    carried_over_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="carried_over_to"
    )
    # The team lead's check of the day's result: confirmed, or not done after all. The rating's
    # "morning plans kept" KPI follows the lead's word over the person's own tick.
    class LeadCheck(models.TextChoices):
        NONE = "", "Not checked"
        CONFIRMED = "confirmed", "Confirmed"
        NOT_DONE = "not_done", "Not done"

    lead_check = models.CharField(max_length=10, choices=LeadCheck.choices, default=LeadCheck.NONE, blank=True)
    checked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    checked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "id"]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"{self.user} - {self.date}: {self.text[:40]}"


class TodoItem(models.Model):
    """A person's own to-do list (AFIT, 5 Nov 2026), apart from the morning plan: work and personal
    things alike, private to the person (nobody else, not a team lead or the CEO, sees it), and not
    counted in any rating."""

    class Kind(models.TextChoices):
        WORK = "work", "Work"
        PERSONAL = "personal", "Personal"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="todo_items")
    text = models.CharField(max_length=300)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.WORK)
    due_date = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)
    done_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["done", models.F("due_date").asc(nulls_last=True), "-created_at", "-id"]
        indexes = [models.Index(fields=["user", "done"])]

    def __str__(self):
        return f"{self.user} - {self.text[:40]}"
