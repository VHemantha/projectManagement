from django.db import models


class Client(models.Model):
    """An external client/customer a project may be done for. Nullable on Project — plenty of
    projects (internal tooling, etc.) have no client, which the tree-nav view surfaces under an
    "Internal / No Client" catch-all branch rather than requiring every project to have one."""

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="clients")
    name = models.CharField(max_length=150)
    logo = models.ImageField(upload_to="client_logos/", null=True, blank=True)
    primary_contact_name = models.CharField(max_length=150, blank=True)
    primary_contact_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
