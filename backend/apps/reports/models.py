from django.conf import settings
from django.db import models


class Dashboard(models.Model):
    name = models.CharField(max_length=150)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dashboards")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class DashboardWidget(models.Model):
    class WidgetType(models.TextChoices):
        ASSIGNED_TO_ME = "assigned_to_me", "Assigned to me"
        RECENT_ACTIVITY = "recent_activity", "Recent activity"
        STATUS_PIE = "status_pie", "Status breakdown"
        SPRINT_BURNDOWN = "sprint_burndown", "Sprint burndown"
        VELOCITY = "velocity", "Velocity"

    dashboard = models.ForeignKey(Dashboard, on_delete=models.CASCADE, related_name="widgets")
    widget_type = models.CharField(max_length=30, choices=WidgetType.choices)
    config = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_widget_type_display()} on {self.dashboard}"
