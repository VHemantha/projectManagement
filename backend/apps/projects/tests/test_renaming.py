"""Renaming things people named: teams, workspaces, board columns, labels, channels, filters."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Channel, ChannelMembership
from apps.orgs.models import Organization
from apps.projects.models import Label, Project, ProjectMembership
from apps.search.models import Filter
from apps.teams.models import Team, TeamMembership

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def lead():
    return User.objects.create_user(username="lead", email="lead@example.com", password="x")


@pytest.fixture
def worker():
    return User.objects.create_user(username="worker", email="worker@example.com", password="x")


@pytest.fixture
def project(lead, worker):
    assert client_for(lead).post("/api/projects/", {"key": "Ren", "name": "Rename me", "project_type": "kanban"}, format="json").status_code == 201
    project = Project.objects.get(key="Ren")
    ProjectMembership.objects.create(project=project, user=worker)
    return project


# ---- Teams -----------------------------------------------------------------------------------


@pytest.fixture
def team(lead, worker):
    team = Team.objects.create(organization=Organization.get_solo(), name="Accounts")
    TeamMembership.objects.create(team=team, user=lead, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=team, user=worker, role=TeamMembership.Role.MEMBER)
    return team


def test_team_lead_renames_team_and_its_channel_follows(lead, team):
    resp = client_for(lead).patch(f"/api/teams/{team.id}/", {"name": "  Accounts   payable "}, format="json")
    assert resp.status_code == 200, resp.data
    team.refresh_from_db()
    assert team.name == "Accounts payable"
    assert team.channels.get().name == "accounts-payable"


def test_team_rename_rules(lead, worker, team):
    Team.objects.create(organization=Organization.get_solo(), name="Payroll")
    assert client_for(worker).patch(f"/api/teams/{team.id}/", {"name": "Mine now"}, format="json").status_code == 403
    assert client_for(lead).patch(f"/api/teams/{team.id}/", {"name": "   "}, format="json").status_code == 400
    resp = client_for(lead).patch(f"/api/teams/{team.id}/", {"name": "payroll"}, format="json")
    assert resp.status_code == 400
    assert "already a workspace" in str(resp.data["name"][0])
    # Changing only the case of its own name is fine.
    assert client_for(lead).patch(f"/api/teams/{team.id}/", {"name": "ACCOUNTS"}, format="json").status_code == 200


# ---- Workspaces ------------------------------------------------------------------------------


def test_workspace_rename_by_manager_only(lead, worker, project):
    assert client_for(lead).patch("/api/projects/Ren/", {"name": "Renamed"}, format="json").status_code == 200
    assert client_for(worker).patch("/api/projects/Ren/", {"name": "Hijacked"}, format="json").status_code == 403
    assert client_for(lead).patch("/api/projects/Ren/", {"name": " "}, format="json").status_code == 400
    project.refresh_from_db()
    assert project.name == "Renamed"


# ---- Board columns ---------------------------------------------------------------------------


def test_column_rename_also_renames_its_status(lead, project):
    board = project.boards.first()
    resp = client_for(lead).patch(f"/api/boards/{board.id}/columns/2/", {"name": "Doing"}, format="json")
    assert resp.status_code == 200, resp.data
    board.refresh_from_db()
    assert board.column_config[2]["name"] == "Doing"
    status_id = board.column_config[2]["status_ids"][0]
    assert project.workflow.statuses.get(pk=status_id).name == "Doing"


def test_column_rename_rules(lead, worker, project):
    board = project.boards.first()
    url = f"/api/boards/{board.id}/columns/1/"
    assert client_for(worker).patch(url, {"name": "Next"}, format="json").status_code == 403
    assert client_for(lead).patch(url, {"name": ""}, format="json").status_code == 400
    resp = client_for(lead).patch(url, {"name": "done"}, format="json")
    assert resp.status_code == 400
    assert "already has a column" in str(resp.data["name"][0])
    assert client_for(lead).patch(f"/api/boards/{board.id}/columns/99/", {"name": "X"}, format="json").status_code == 404


def test_column_whose_name_differs_from_its_status_keeps_the_status_name(lead, project):
    board = project.boards.first()
    board.column_config[1]["name"] = "Ready"
    board.save()
    resp = client_for(lead).patch(f"/api/boards/{board.id}/columns/1/", {"name": "Up next"}, format="json")
    assert resp.status_code == 200
    assert project.workflow.statuses.filter(name="To do").exists()


# ---- Labels ----------------------------------------------------------------------------------


def test_label_rename(lead, worker, project):
    label = Label.objects.create(project=project, name="VAT")
    Label.objects.create(project=project, name="Payroll")
    url = f"/api/projects/Ren/labels/{label.id}/"
    assert client_for(lead).patch(url, {"name": "VAT return"}, format="json").status_code == 200
    assert client_for(worker).patch(url, {"name": "Nope"}, format="json").status_code == 403
    resp = client_for(lead).patch(url, {"name": "PAYROLL"}, format="json")
    assert resp.status_code == 400
    assert client_for(lead).patch(url, {"name": ""}, format="json").status_code == 400
    label.refresh_from_db()
    assert label.name == "VAT return"
    # Adding labels follows the same rule.
    assert client_for(worker).post("/api/projects/Ren/labels/", {"name": "New"}, format="json").status_code == 403
    assert client_for(lead).post("/api/projects/Ren/labels/", {"name": "vat RETURN"}, format="json").status_code == 400
    assert client_for(lead).post("/api/projects/Ren/labels/", {"name": "Bookkeeping", "color": "#ccddee"}, format="json").status_code == 201


# ---- Channels --------------------------------------------------------------------------------


def test_topic_channel_rename_rules(lead, team):
    org = Organization.get_solo()
    topic = Channel.objects.create(organization=org, name="random", channel_type="topic")
    Channel.objects.create(organization=org, name="announcements", channel_type="topic")
    ChannelMembership.objects.create(channel=topic, user=lead)
    client = client_for(lead)
    assert client.patch(f"/api/chat/channels/{topic.id}/", {"name": "watercooler"}, format="json").status_code == 200
    assert client.patch(f"/api/chat/channels/{topic.id}/", {"name": "Announcements"}, format="json").status_code == 400
    team_channel = team.channels.get()
    resp = client.patch(f"/api/chat/channels/{team_channel.id}/", {"name": "other"}, format="json")
    assert resp.status_code == 400
    assert "named after" in str(resp.data["name"][0])


# ---- Saved filters ---------------------------------------------------------------------------


def test_only_the_owner_can_rename_a_public_filter(lead, worker):
    mine = Filter.objects.create(owner=lead, name="My open jobs", is_public=True)
    Filter.objects.create(owner=lead, name="Overdue")
    assert client_for(lead).patch(f"/api/search/filters/{mine.id}/", {"name": "Open jobs"}, format="json").status_code == 200
    assert client_for(lead).patch(f"/api/search/filters/{mine.id}/", {"name": "overdue"}, format="json").status_code == 400
    assert client_for(worker).patch(f"/api/search/filters/{mine.id}/", {"name": "Taken"}, format="json").status_code == 403
    assert client_for(worker).delete(f"/api/search/filters/{mine.id}/").status_code == 403
