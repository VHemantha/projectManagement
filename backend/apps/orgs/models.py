from django.db import models


class Organization(models.Model):
    """Tenant container. Single-row for v1; schema supports multiple later."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def get_solo(cls):
        org, _ = cls.objects.get_or_create(
            slug="default", defaults={"name": "TrackFlow"}
        )
        return org
