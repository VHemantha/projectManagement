import pytest

from apps.accounts.models import User
from apps.chat.models import Channel
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team

pytestmark = pytest.mark.django_db


def test_creating_a_project_auto_creates_a_channel():
    org = Organization.get_solo()
    lead = User.objects.create_user(username="lead", email="lead@example.com", password="x")
    project = Project.objects.create(organization=org, key="CHT", name="Chat Test", lead=lead)

    channel = Channel.objects.get(linked_project=project)
    assert channel.channel_type == Channel.ChannelType.PROJECT
    assert channel.name == "cht"
    assert channel.memberships.filter(user=lead).exists()


def test_creating_a_team_auto_creates_a_channel():
    org = Organization.get_solo()
    team = Team.objects.create(organization=org, name="Design Guild")

    channel = Channel.objects.get(linked_team=team)
    assert channel.channel_type == Channel.ChannelType.TEAM
    assert channel.name == "design-guild"


def test_deleting_project_cascades_to_its_channel():
    org = Organization.get_solo()
    project = Project.objects.create(organization=org, key="DEL", name="Delete Test")
    channel_id = Channel.objects.get(linked_project=project).id

    project.delete()
    assert not Channel.objects.filter(id=channel_id).exists()
