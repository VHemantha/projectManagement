from django.conf import settings
from django.db import models


class Team(models.Model):
    organization = models.ForeignKey(
        "orgs.Organization", on_delete=models.CASCADE, related_name="teams"
    )
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    avatar_color = models.CharField(max_length=7, default="#0C66E4")
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through="TeamMembership", related_name="teams"
    )
    # Self-referential rather than a separate "Group" model — a Group is just a top-level Team
    # (parent is null) whose children are ordinary Teams (e.g. "Group 1" has parent=None;
    # "Team 1"/"Team 2" have parent=<Group 1>). Reuses every existing Team/TeamMembership CRUD
    # and lead convention for both levels instead of a parallel model.
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.SET_NULL, related_name="sub_teams"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TeamMembership(models.Model):
    class Role(models.TextChoices):
        LEAD = "lead", "Lead"
        MEMBER = "member", "Member"

    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_memberships"
    )
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("team", "user")

    def __str__(self):
        return f"{self.user} in {self.team} ({self.role})"
