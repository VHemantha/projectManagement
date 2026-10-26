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


def test_tree_is_workspace_then_sub_workspace_and_stops_there(api, user):
    """AFIT, 26 Oct 2026: the tree ends at the sub-workspace (client). Each row opens its tasks:
    a workspace filtered by itself, a sub-workspace by its workspace and itself."""
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
    assert ws["type"] == "workspace" and ws["team_id"] == team1.id and ws["board_query"] == {"team": team1.id}
    subs = by_label(ws["children"])
    assert list(subs) == ["Acme", "RWCA", "No sub-workspace"]
    assert subs["RWCA"]["type"] == "sub_workspace" and subs["RWCA"]["client_id"] == rwca.id
    assert subs["RWCA"]["board_query"] == {"team": team1.id, "client": rwca.id}
    assert all(s["children"] == [] for s in subs.values())  # no projects below a sub-workspace
    assert subs["RWCA"]["project_count"] == 1  # the archived one is left out
    assert subs["No sub-workspace"]["board_query"] == {"team": team1.id, "exclude_sub_teams": True, "no_client": True}
    assert tree["Team 2"]["children"] == []
    # Nothing is unreachable: an unplaced sub-workspace and a project with neither.
    assert tree["No workspace"]["board_query"] == {"no_team": True}
    unplaced = by_label(tree["No workspace"]["children"])
    assert list(unplaced) == ["Floating Ltd", "No sub-workspace"]
    assert unplaced["Floating Ltd"]["board_query"] == {"client": floating.id}
    # The automatic task list joined its sub-workspace's workspace.
    assert Project.objects.get(client=acme, is_client_workspace=True).primary_team == team1


def test_a_workspace_shows_every_task_of_its_sub_workspaces(api, user):
    """A sub-workspace's projects belong to its workspace even when a project's own team is
    another or none, so the workspace's and the sub-workspace's views show them."""
    from apps.issues.models import Issue
    from apps.workflow.models import IssueType

    org = Organization.get_solo()
    team1, team2 = Team.objects.create(organization=org, name="Team 1"), Team.objects.create(organization=org, name="Team 2")
    rwca = Client.objects.create(organization=org, name="RWCA", team=team1)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    elsewhere = project("Hedwig", user, name="Hedwig Group", client=rwca, primary_team=team2)
    loose = get_or_create_client_workspace(rwca, user)
    loose.primary_team = None
    loose.save()
    other = project("Other", user, name="Other work", primary_team=team2)
    from apps.workflow.services import provision_project_defaults

    for p in (elsewhere, loose, other):
        if not hasattr(p, "workflow"):
            provision_project_defaults(p)

    def add(p, summary):
        return api.post("/api/issues/", {"project": p.key, "summary": summary, "issue_type_id": task.id}, format="json").data["key"]

    hedwig, unfiled, mine = add(elsewhere, "Hedwig year end"), add(loose, "Loose task"), add(other, "Team 2 job")
    keys = lambda q: {i["key"] for i in api.get("/api/issues/", q).data["results"]}  # noqa: E731
    assert keys({"team": team1.id}) == {hedwig, unfiled}
    assert keys({"team": team1.id, "client": rwca.id}) == {hedwig, unfiled}
    assert keys({"team": team2.id}) == {hedwig, mine}  # still a team-2 project too
    assert mine not in keys({"no_team": True}) and unfiled not in keys({"no_team": True})
    assert Issue.objects.count() == 3


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
