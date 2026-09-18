from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Verb(models.TextChoices):
        ASSIGNED = "assigned", "assigned you"
        MENTIONED = "mentioned", "mentioned you"
        COMMENTED = "commented", "commented"
        STATUS_CHANGED = "status_changed", "changed status"
        WATCHING_UPDATED = "watching_updated", "updated a watched issue"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    verb = models.CharField(max_length=30, choices=Verb.choices)
    target_issue = models.ForeignKey(
        "issues.Issue", null=True, on_delete=models.CASCADE, related_name="notifications"
    )
    target_message = models.ForeignKey(
        "chat.Message", null=True, on_delete=models.CASCADE, related_name="notifications"
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user}: {self.get_verb_display()}"
