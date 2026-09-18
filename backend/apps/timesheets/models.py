from django.conf import settings
from django.db import models


class TimeEntryTag(models.Model):
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="time_entry_tags"
    )
    name = models.CharField(max_length=50)
    color = models.CharField(max_length=7, default="#DCDFE4")

    class Meta:
        unique_together = ("organization", "name")

    def __str__(self):
        return self.name


class TimeEntry(models.Model):
    class CreatedVia(models.TextChoices):
        TIMER = "timer", "Timer"
        MANUAL = "manual", "Manual"
        CHAT_COMMAND = "chat_command", "Chat command"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="time_entries")
    issue = models.ForeignKey(
        "issues.Issue", null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries"
    )
    # Denormalized from issue.project for fast aggregation; kept in sync in save().
    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries"
    )
    description = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    is_billable = models.BooleanField(default=True)
    is_running = models.BooleanField(default=False)
    tags = models.ManyToManyField(TimeEntryTag, blank=True, related_name="time_entries")
    created_via = models.CharField(max_length=20, choices=CreatedVia.choices, default=CreatedVia.MANUAL)
    locked = models.BooleanField(default=False)
    work_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-work_date", "-started_at"]
        indexes = [models.Index(fields=["user", "work_date"])]

    def __str__(self):
        return f"{self.user} - {self.duration} on {self.work_date}"

    def save(self, *args, **kwargs):
        if self.issue_id and not self.project_id:
            self.project_id = self.issue.project_id
        super().save(*args, **kwargs)


class Timesheet(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="timesheets")
    period_start = models.DateField()
    period_end = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_timesheets"
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.TextField(blank=True)

    class Meta:
        unique_together = ("user", "period_start")
        ordering = ["-period_start"]

    def __str__(self):
        return f"{self.user} {self.period_start} – {self.period_end} ({self.status})"


class BillableRate(models.Model):
    class Scope(models.TextChoices):
        ORGANIZATION = "organization", "Organization default"
        PROJECT = "project", "Project override"
        USER = "user", "User override"

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="billable_rates")
    scope = models.CharField(max_length=20, choices=Scope.choices)
    project = models.ForeignKey(
        "projects.Project", null=True, blank=True, on_delete=models.CASCADE, related_name="billable_rates"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE, related_name="billable_rates"
    )
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    def __str__(self):
        return f"{self.get_scope_display()}: {self.hourly_rate} {self.currency}/hr"
