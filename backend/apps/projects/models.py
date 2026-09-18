from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models

KEY_PATTERN = r"^[A-Z][A-Z0-9]{1,9}$"
key_validator = RegexValidator(
    regex=KEY_PATTERN,
    message="Project key must be 2-10 uppercase letters/digits, starting with a letter.",
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
    key = models.CharField(max_length=10, unique=True, validators=[key_validator])
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
    avatar_color = models.CharField(max_length=7, default="#0C66E4")
    default_assignee_rule = models.CharField(
        max_length=20,
        choices=[("unassigned", "Unassigned"), ("project_lead", "Project Lead")],
        default="unassigned",
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="ProjectMembership", related_name="projects"
    )
    is_archived = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return f"{self.key} - {self.name}"

    def save(self, *args, **kwargs):
        self.key = self.key.upper()
        super().save(*args, **kwargs)


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
