import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="nav_user", email="nav_user@example.com", password="x")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def teams():
    org = Organization.get_solo()
    return {
        "platform": Team.objects.create(organization=org, name="Platform"),
        "growth": Team.objects.create(organization=org, name="Growth"),
    }


@pytest.fixture
def acme_client():
    return Client.objects.create(organization=Organization.get_solo(), name="Acme Corp")


def _make_project(key, lead, **kwargs):
    return Project.objects.create(organization=Organization.get_solo(), key=key, name=f"{key} Project", lead=lead, **kwargs)


def _project_keys_under_team(team_node) -> list[str]:
    """Team -> Client -> Project, so a team's project keys are one level deeper than before
    the client grouping was added — flatten across every client branch under this team."""
    keys = []
    for client_node in team_node["children"]:
        keys.extend(c["key"] for c in client_node["children"])
    return keys


def test_by_team_groups_projects_under_their_primary_team(api_client, user, teams):
    _make_project("NVA", user, primary_team=teams["platform"])
    _make_project("NVB", user, primary_team=teams["growth"])

    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    assert resp.status_code == 200
    nodes_by_label = {node["label"]: node for node in resp.data["nodes"]}
    assert _project_keys_under_team(nodes_by_label["Platform"]) == ["NVA"]
    assert _project_keys_under_team(nodes_by_label["Growth"]) == ["NVB"]


def test_by_team_also_groups_each_teams_projects_by_client(api_client, user, teams, acme_client):
    _make_project("NVI", user, primary_team=teams["platform"], client=acme_client)
    _make_project("NVJ", user, primary_team=teams["platform"])

    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    platform_node = next(n for n in resp.data["nodes"] if n["label"] == "Platform")
    client_labels = {c["label"]: [p["key"] for p in c["children"]] for c in platform_node["children"]}
    assert client_labels["Acme Corp"] == ["NVI"]
    assert client_labels["Internal / No Client"] == ["NVJ"]


def test_a_project_with_multiple_contributing_teams_appears_under_each(api_client, user, teams):
    project = _make_project("NVC", user, primary_team=teams["platform"])
    project.contributing_teams.set([teams["growth"]])

    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    nodes_by_label = {node["label"]: node for node in resp.data["nodes"]}
    assert "NVC" in _project_keys_under_team(nodes_by_label["Platform"])
    assert "NVC" in _project_keys_under_team(nodes_by_label["Growth"])


def test_a_project_with_no_team_falls_under_the_no_team_catch_all(api_client, user):
    _make_project("NVD", user)

    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    no_team_node = next(n for n in resp.data["nodes"] if n["label"] == "No Team")
    assert "NVD" in _project_keys_under_team(no_team_node)


def test_by_client_groups_projects_and_uses_internal_catch_all(api_client, user, acme_client):
    _make_project("NVE", user, client=acme_client)
    _make_project("NVF", user)

    resp = api_client.get("/api/reports/nav-tree/?group_by=client")
    labels = {node["label"]: [c["key"] for c in node["children"]] for node in resp.data["nodes"]}
    assert labels["Acme Corp"] == ["NVE"]
    assert "NVF" in labels["Internal / No Client"]


def test_project_leaf_includes_a_board_child_when_one_exists(api_client, user, teams):
    from apps.workflow.services import provision_project_defaults

    project = _make_project("NVG", user, primary_team=teams["platform"])
    provision_project_defaults(project)

    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    team_node = next(n for n in resp.data["nodes"] if n["label"] == "Platform")
    no_client_node = next(c for c in team_node["children"] if c["label"] == "Internal / No Client")
    project_node = next(c for c in no_client_node["children"] if c["key"] == "NVG")
    assert len(project_node["children"]) == 1
    assert project_node["children"][0]["type"] == "board"


def test_client_crud(api_client):
    create = api_client.post("/api/clients/", {"name": "Globex"}, format="json")
    assert create.status_code == 201
    client_id = create.data["id"]

    listing = api_client.get("/api/clients/")
    assert any(c["id"] == client_id for c in listing.data)

    update = api_client.patch(f"/api/clients/{client_id}/", {"primary_contact_name": "Hank Scorpio"}, format="json")
    assert update.status_code == 200
    assert update.data["primary_contact_name"] == "Hank Scorpio"


def test_project_serializer_accepts_client_and_team_assignment(api_client, user, teams, acme_client):
    resp = api_client.post(
        "/api/projects/",
        {
            "key": "NVH", "name": "Nav Test H", "project_type": "kanban",
            "client_id": acme_client.id, "primary_team_id": teams["platform"].id,
            "contributing_team_ids": [teams["growth"].id],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["client"]["name"] == "Acme Corp"
    assert resp.data["primary_team"]["name"] == "Platform"
    assert [t["name"] for t in resp.data["contributing_teams"]] == ["Growth"]
