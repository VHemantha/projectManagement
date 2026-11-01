"""Who leads whom, from workspace membership: a lead of a workspace leads its members, and a lead of
a group (a top-level workspace) also leads the members of the workspaces inside it. An organisation
admin (and the CEO) leads everyone."""
from django.contrib.auth import get_user_model

from .models import Team, TeamMembership


def led_team_ids(user) -> set[int]:
    led = set(TeamMembership.objects.filter(user=user, role=TeamMembership.Role.LEAD).values_list("team_id", flat=True))
    return led | set(Team.objects.filter(parent_id__in=led).values_list("id", flat=True))


def led_people(user):
    """Active people (not the agent) this user leads, the user left out."""
    User = get_user_model()
    people = User.objects.filter(is_active=True, is_agent=False)
    if not user.is_staff:
        people = people.filter(team_memberships__team_id__in=led_team_ids(user))
    return people.exclude(id=user.id).distinct().order_by("display_name")


def leads(user, person) -> bool:
    if user.id == person.id:
        return False
    return user.is_staff or led_people(user).filter(id=person.id).exists()
