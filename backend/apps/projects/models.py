from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models.functions import Lower

# Keys keep the case they're typed in ("Pochin" -> jobs "Pochin-12") and are unique ignoring
# case, so "pochin" can't be created alongside it and lookups can be case-insensitive.
KEY_PATTERN = r"^[A-Za-z][A-Za-z0-9]{1,99}$"
key_validator = RegexValidator(
    regex=KEY_PATTERN,
    message="Workspace key must be 2-100 letters/digits, starting with a letter.",
)


class ProjectCategory(models.Model):
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="project_categories"
    )
    name = models.CharField(max_length=100)

    class Meta:
        verbose_name_plural = "project categories"

    def __str__(self):
        return self.name


class Project(models.Model):
    class ProjectType(models.TextChoices):
        SCRUM = "scrum", "Scrum"
        KANBAN = "kanban", "Kanban"

    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="projects"
    )
    key = models.CharField(max_length=100, unique=True, validators=[key_validator])
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    project_type = models.CharField(
        max_length=10, choices=ProjectType.choices, default=ProjectType.SCRUM
    )
    category = models.ForeignKey(
        ProjectCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="led_projects"
    )
    client = models.ForeignKey(
        "clients.Client", null=True, blank=True, on_delete=models.SET_NULL, related_name="projects"
    )
    # The tree-nav "By Team" view groups projects under teams. A project's main team (if any)
    # plus any other contributing teams via the ProjectTeam M2M below — Project and Team had no
    # relationship at all before this addendum.
    primary_team = models.ForeignKey(
        "teams.Team", null=True, blank=True, on_delete=models.SET_NULL, related_name="primary_projects"
    )
    contributing_teams = models.ManyToManyField(
        "teams.Team", through="ProjectTeam", blank=True, related_name="contributing_projects"
    )
    # Reporting/visibility only — no invoicing or automatic billing, matching the scope
    # boundary already set for Timesheets. job_value is a separate, often fixed-fee number
    # that doesn't derive from rate × hours (BillableRate), which matters for services
    # businesses tracking margin (job_value - effective cost) alongside hours budget vs actual.
    budgeted_hours = models.FloatField(null=True, blank=True)
    job_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    job_value_currency = models.CharField(max_length=3, default="USD")
    avatar_color = models.CharField(max_length=7, default="#0C66E4")
    default_assignee_rule = models.CharField(
        max_length=20,
        choices=[("unassigned", "Unassigned"), ("project_lead", "Project Lead")],
        default="unassigned",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ProjectMembership", related_name="projects"
    )
    # The project's standard task names (e.g. "Bank reconciliation", "VAT return"), defined when
    # the project is created and editable later. The Create issue dialog offers them as the
    # issue summary, so recurring work is named consistently across a project.
    task_names = models.JSONField(default=list, blank=True)
    # An automatic job container for a client that doesn't use projects (see
    # Client.requires_projects): created on demand the first time a job is added for that
    # client without a project. Behaves like any project (board, workflow, settings).
    is_client_workspace = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]
        # Shown to users as "workspaces"; the model/table keep their original name so existing
        # data, foreign keys and the /api/projects/ endpoints stay unchanged.
        verbose_name = "workspace"
        verbose_name_plural = "workspaces"
        constraints = [models.UniqueConstraint(Lower("key"), name="project_key_unique_ignoring_case")]

    def __str__(self):
        return f"{self.key} - {self.name}"


class ProjectKeyAlias(models.Model):
    """A key a project used to have. After a rename, old links and job keys (PG-12) still
    resolve: the project is found through its alias and the job by its number."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="key_aliases")
    key = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(Lower("key"), name="project_key_alias_unique_ignoring_case")]

    def __str__(self):
        return f"{self.key} -> {self.project.key}"


class ProjectMembership(models.Model):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        MEMBER = "member", "Member"
        VIEWER = "viewer", "Viewer"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="project_memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("project", "user")

    def __str__(self):
        return f"{self.user} in {self.project} ({self.role})"


class ProjectTeam(models.Model):
    """Additional teams contributing to a project, beyond its primary_team — a project with
    multiple contributing teams should appear under each relevant team branch in the tree-nav
    view rather than being forced into a single-parent tree."""

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="project_team_rows")
    team = models.ForeignKey("teams.Team", on_delete=models.CASCADE, related_name="project_team_rows")

    class Meta:
        unique_together = ("project", "team")

    def __str__(self):
        return f"{self.team} on {self.project}"


class Label(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="labels")
    name = models.CharField(max_length=60)
    color = models.CharField(max_length=7, default="#DCDFE4")

    class Meta:
        unique_together = ("project", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Component(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="components")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    lead = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="led_components"
    )

    class Meta:
        unique_together = ("project", "name")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Version(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="versions")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    released = models.BooleanField(default=False)
    archived = models.BooleanField(default=False)

    class Meta:
        unique_together = ("project", "name")
        ordering = ["-release_date", "name"]

    def __str__(self):
        return self.name
