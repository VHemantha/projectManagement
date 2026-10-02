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


class Invitation(models.Model):
    """An admin's invitation to join. Sign-up is by invitation only: the emailed link carries a
    random token, of which only a SHA-256 hash is stored. A token works once, until it expires,
    is replaced by a resend, or the invitation is revoked."""

    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        WORKER = "worker", "Worker"

    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.WORKER)
    team = models.ForeignKey("teams.Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="invitations")
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="invitations_sent")
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_user = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Invitation for {self.email}"

    def status_at(self, now) -> str:
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        if self.expires_at <= now:
            return "expired"
        return "pending"
