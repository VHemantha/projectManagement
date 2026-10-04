from django.db import models


class Client(models.Model):
    """Shown to users as a "sub-workspace": the second level of the app's hierarchy,

        Workspace (teams.Team) > Sub-workspace (Client) > Project (projects.Project) > Task (Issue)

    e.g. Team 1 > RWCA > Michael Group > ABC Ltd. Nullable on Project — internal projects have
    no client, which the tree shows under "No sub-workspace" in their workspace."""

    organization = models.ForeignKey("orgs.Organization", on_delete=models.CASCADE, related_name="clients")
    # The workspace this sub-workspace sits in. Nullable so existing clients keep working until
    # someone places them (migration 0003 places each one in the team most of its projects use).
    team = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="clients"
    )
    name = models.CharField(max_length=150)
    logo = models.ImageField(upload_to="client_logos/", null=True, blank=True)
    primary_contact_name = models.CharField(max_length=150, blank=True)
    primary_contact_email = models.EmailField(blank=True)
    notes = models.TextField(blank=True)
    # Off: jobs can be created for the client directly, without making a project first (they
    # go into the client's automatic job list — see services.get_or_create_client_workspace).
    # On (e.g. RWCA): every job must belong to one of the client's projects.
    requires_projects = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "sub-workspace"
        verbose_name_plural = "sub-workspaces"

    def __str__(self):
        return self.name
