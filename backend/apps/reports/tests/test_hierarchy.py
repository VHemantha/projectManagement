"""Workspace (Team) > Sub-workspace (Client) > Project > Task: the app's one hierarchy."""
import importlib

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.clients.services import get_or_create_client_workspace
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="h_user", email="h_user@example.com", password="x")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def project(key, lead, **kwargs):
    return Project.objects.create(organization=Organization.get_solo(), key=key, name=kwargs.pop("name", f"{key} Project"), lead=lead, **kwargs)


def by_label(nodes):
    return {n["label"]: n for n in nodes}


def test_tree_is_workspace_then_sub_workspace_then_project(api, user):
    org = Organization.get_solo()
    team1 = Team.objects.create(organization=org, name="Team 1")
    Team.objects.create(organization=org, name="Team 2")
    rwca = Client.objects.create(organization=org, name="RWCA", team=team1, requires_projects=True)
    acme = Client.objects.create(organization=org, name="Acme", team=team1)
    floating = Client.objects.create(organization=org, name="Floating Ltd")
    project("Michael", user, name="Michael Group", client=rwca, primary_team=team1)
    project("Internal", user, name="Internal tools", primary_team=team1)
    project("Lost", user, name="Lost project")
    get_or_create_client_workspace(acme, user)  # Acme's list for tasks added without a project
    project("Old", user, name="Archived one", client=rwca, is_archived=True)

    nodes = api.get("/api/reports/nav-tree/?group_by=hierarchy").data["nodes"]
    tree = by_label(nodes)
    assert list(tree) == ["Team 1", "Team 2", "No workspace"]
    ws = tree["Team 1"]
    assert ws["type"] == "workspace" and ws["team_id"] == team1.id
    subs = by_label(ws["children"])
    assert list(subs) == ["Acme", "RWCA", "No sub-workspace"]
    assert subs["RWCA"]["type"] == "sub_workspace" and subs["RWCA"]["client_id"] == rwca.id
    assert subs["RWCA"]["board_query"] == {"client": rwca.id}
    michael = subs["RWCA"]["children"]
    assert [(p["type"], p["label"], p["project_key"]) for p in michael] == [("project", "Michael Group", "Michael")]  # archived left out
    assert [p["label"] for p in subs["Acme"]["children"]] == ["Tasks without a project"]
    assert subs["Acme"]["children"][0]["is_client_tasks"] is True
    assert [p["label"] for p in subs["No sub-workspace"]["children"]] == ["Internal tools"]
    assert subs["No sub-workspace"]["board_query"] == {"team": team1.id, "exclude_sub_teams": True, "no_client": True}
    assert tree["Team 2"]["children"] == []
    # Nothing is unreachable: an unplaced sub-workspace and a project with neither.
    unplaced = by_label(tree["No workspace"]["children"])
    assert list(unplaced) == ["Floating Ltd", "No sub-workspace"]
    assert [p["label"] for p in unplaced["No sub-workspace"]["children"]] == ["Lost project"]
    # The automatic task list joined its sub-workspace's workspace.
    assert Project.objects.get(client=acme, is_client_workspace=True).primary_team == team1


def test_sub_workspaces_belong_to_a_workspace_and_projects_follow(api, user):
    org = Organization.get_solo()
    team1 = Team.objects.create(organization=org, name="Team 1")
    resp = api.post("/api/clients/", {"name": "RWCA", "team_id": team1.id}, format="json")
    assert resp.status_code == 201 and resp.data["team_id"] == team1.id and resp.data["team_name"] == "Team 1"
    rwca = Client.objects.get(name="RWCA")
    Client.objects.create(organization=org, name="Other")
    assert [c["name"] for c in api.get("/api/clients/", {"team": team1.id}).data] == ["RWCA"]
    assert [c["name"] for c in api.get("/api/clients/", {"team": "none"}).data] == ["Other"]

    # A project created in a sub-workspace lands in that sub-workspace's workspace.
    resp = api.post("/api/projects/", {"name": "Michael Group", "key": "Michael", "project_type": "kanban", "client_id": rwca.id}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["primary_team"]["id"] == team1.id and resp.data["client"]["id"] == rwca.id
    # An explicit choice is kept.
    team2 = Team.objects.create(organization=org, name="Team 2")
    resp = api.post("/api/projects/", {"name": "Shared", "key": "Shared", "project_type": "kanban", "client_id": rwca.id, "primary_team_id": team2.id}, format="json")
    assert resp.data["primary_team"]["id"] == team2.id
    # Errors use the new names.
    resp = api.post("/api/projects/", {"name": "Bad", "key": "1x", "project_type": "kanban"}, format="json")
    assert "Project key must be" in str(resp.data)


def test_existing_clients_are_placed_in_the_workspace_their_projects_use(user):
    org = Organization.get_solo()
    team1 = Team.objects.create(organization=org, name="Team 1")
    team2 = Team.objects.create(organization=org, name="Team 2")
    rwca = Client.objects.create(organization=org, name="RWCA")
    lonely = Client.objects.create(organization=org, name="Lonely")
    project("A", user, client=rwca, primary_team=team1)
    project("B", user, client=rwca, primary_team=team1)
    project("C", user, client=rwca, primary_team=team2)
    loose = project("D", user, client=rwca)
    migration = importlib.import_module("apps.clients.migrations.0003_alter_client_options_client_team")
    migration.place_clients_in_workspaces(django_apps, None)
    rwca.refresh_from_db()
    lonely.refresh_from_db()
    loose.refresh_from_db()
    assert rwca.team == team1  # most of its projects are there
    assert lonely.team is None  # nothing to go by: left for a person to place
    assert loose.primary_team == team1  # a project with no workspace joins its sub-workspace's
