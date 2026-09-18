from django.conf import settings
from django.db import models


class Filter(models.Model):
    """A saved, structured filter (JQL-lite). `query` holds the filter-panel criteria as JSON,
    e.g. {"project": [1,2], "status": ["todo"], "assignee": ["me"], "text": "login bug"}."""

    name = models.CharField(max_length=150)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="filters")
    query = models.JSONField(default=dict)
    is_public = models.BooleanField(default=False)
    shared_with_projects = models.ManyToManyField(
        "projects.Project", blank=True, related_name="shared_filters"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
