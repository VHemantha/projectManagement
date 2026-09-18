from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user: email is the login identifier, plus Jira-profile-ish fields."""

    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=150, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    job_title = models.CharField(max_length=150, blank=True)
    is_active_member = models.BooleanField(default=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    def save(self, *args, **kwargs):
        if not self.display_name:
            self.display_name = self.get_full_name() or self.username
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or self.email
