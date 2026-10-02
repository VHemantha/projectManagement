from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user: email is the login identifier, plus Jira-profile-ish fields."""

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    is_active_member = models.BooleanField(default=True)
    # Desktop (OS) notifications for new direct messages, @mentions and bell notifications.
    # The browser must also allow them; this is the person's own on/off switch.
    desktop_notifications = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.get_full_name() or self.username
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.email


class TablePreference(models.Model):
    """One user's layout for one table (job list, projects, a report): visible columns, their
    order, widths and sort. Stored server-side so it follows the user to any device."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="table_preferences")
    table_id = models.CharField(max_length=100)
    state = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "table_id"], name="one_layout_per_user_table")]

    def __str__(self):
        return f"{self.user} / {self.table_id}"
