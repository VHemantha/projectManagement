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


def _leaves(node) -> dict:
    """Client label -> client leaf under a team/group node."""
    return {c["label"]: c for c in node["children"]}


def _walk(nodes):
    for node in nodes:
        yield node
        yield from _walk(node.get("children", []))


def test_by_team_ends_at_client_leaves_with_board_filters(api_client, user, teams, acme_client):
    _make_project("NVA", user, primary_team=teams["platform"], client=acme_client)
    _make_project("NVB", user, primary_team=teams["platform"])
    _make_project("NVC", user, primary_team=teams["growth"])

    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    assert resp.status_code == 200
    platform = _leaves(next(n for n in resp.data["nodes"] if n["label"] == "Platform"))
    team_id = teams["platform"].id
    assert platform["Acme Corp"]["children"] == []
    assert platform["Acme Corp"]["board_query"] == {"team": team_id, "exclude_sub_teams": True, "client": acme_client.id}
    assert platform["Acme Corp"]["project_count"] == 1
    assert platform["Internal / No Client"]["board_query"] == {
        "team": team_id, "exclude_sub_teams": True, "no_client": True,
    }


def test_the_tree_never_contains_project_or_board_nodes(api_client, user, teams, acme_client):
    from apps.workflow.services import provision_project_defaults

    provision_project_defaults(_make_project("NVG", user, primary_team=teams["platform"], client=acme_client))
    for mode in ("group", "team", "client"):
        nodes = api_client.get(f"/api/reports/nav-tree/?group_by={mode}").data["nodes"]
        assert {n["type"] for n in _walk(nodes)} <= {"group", "team", "client"}, mode


def test_a_project_with_multiple_contributing_teams_counts_under_each(api_client, user, teams):
    project = _make_project("NVC", user, primary_team=teams["platform"])
    project.contributing_teams.set([teams["growth"]])

    nodes = {n["label"]: n for n in api_client.get("/api/reports/nav-tree/?group_by=team").data["nodes"]}
    assert _leaves(nodes["Platform"])["Internal / No Client"]["project_count"] == 1
    assert _leaves(nodes["Growth"])["Internal / No Client"]["project_count"] == 1


def test_no_team_catch_all_filters_on_no_team(api_client, user):
    _make_project("NVD", user)

    nodes = api_client.get("/api/reports/nav-tree/?group_by=team").data["nodes"]
    no_team = next(n for n in nodes if n["label"] == "No Team")
    assert _leaves(no_team)["Internal / No Client"]["board_query"] == {"no_team": True, "no_client": True}


def test_by_client_is_a_flat_list_of_client_leaves(api_client, user, acme_client):
    _make_project("NVE", user, client=acme_client)
    _make_project("NVF", user)

    nodes = {n["label"]: n for n in api_client.get("/api/reports/nav-tree/?group_by=client").data["nodes"]}
    assert nodes["Acme Corp"]["board_query"] == {"client": acme_client.id}
    assert nodes["Acme Corp"]["project_count"] == 1
    assert nodes["Acme Corp"]["children"] == []
    assert nodes["Internal / No Client"]["board_query"] == {"no_client": True}


def test_by_group_merges_a_top_level_teams_own_and_sub_teams_projects(api_client, user, teams):
    org = teams["platform"].organization
    group = Team.objects.create(organization=org, name="Group 1")
    for team in (teams["platform"], teams["growth"]):
        team.parent = group
        team.save(update_fields=["parent"])

    _make_project("NVK", user, primary_team=teams["platform"])
    _make_project("NVL", user, primary_team=teams["growth"])

    resp = api_client.get("/api/reports/nav-tree/?group_by=group")
    assert resp.status_code == 200
    group_node = next(n for n in resp.data["nodes"] if n["label"] == "Group 1")
    leaf = _leaves(group_node)["Internal / No Client"]
    assert leaf["project_count"] == 2
    assert leaf["board_query"] == {"team": group.id, "no_client": True}
    # The sub-teams themselves shouldn't appear as their own top-level group nodes.
    assert not any(n["label"] in ("Platform", "Growth") for n in resp.data["nodes"])


def test_by_group_a_plain_top_level_team_is_its_own_group(api_client, user, teams):
    _make_project("NVM", user, primary_team=teams["platform"])

    resp = api_client.get("/api/reports/nav-tree/?group_by=group")
    labels = {n["label"] for n in resp.data["nodes"]}
    assert "Platform" in labels
    assert "Growth" in labels


def test_a_team_with_no_projects_still_carries_its_team_id(api_client, teams):
    # A childless team/group node is a leaf in the tree UI (nothing to expand into), so the
    # frontend needs team_id on it to route a click to the team's own detail page instead of
    # silently doing nothing.
    resp = api_client.get("/api/reports/nav-tree/?group_by=team")
    growth_node = next(n for n in resp.data["nodes"] if n["label"] == "Growth")
    assert growth_node["children"] == []
    assert growth_node["team_id"] == teams["growth"].id

    resp = api_client.get("/api/reports/nav-tree/?group_by=group")
    growth_group_node = next(n for n in resp.data["nodes"] if n["label"] == "Growth")
    assert growth_group_node["team_id"] == teams["growth"].id


def test_every_client_leaf_board_query_selects_exactly_its_projects_issues(api_client, user, teams, acme_client):
    """Clicking a client leaf opens the All issues board with its board_query: the issues it
    returns must come from exactly the projects the tree counted under that leaf."""
    from apps.workflow.models import IssueType, Workflow, WorkflowStatus

    org = teams["platform"].organization
    group = Team.objects.create(organization=org, name="Group 1")
    teams["platform"].parent = group
    teams["platform"].save(update_fields=["parent"])
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)

    specs = [
        ("NVP", {"primary_team": group, "client": acme_client}),
        ("NVQ", {"primary_team": teams["platform"], "client": acme_client}),
        ("NVR", {"primary_team": teams["platform"]}),
        ("NVS", {"primary_team": teams["growth"]}),
        ("NVT", {"client": acme_client}),
        ("NVU", {}),
    ]
    for key, extra in specs:
        project = _make_project(key, user, **extra)
        WorkflowStatus.objects.create(workflow=Workflow.objects.create(project=project), name="To Do", category="todo", order=0)
        api_client.post("/api/issues/", {"project": key, "summary": f"{key} work", "issue_type_id": task.id}, format="json")

    for mode in ("group", "team", "client"):
        for leaf in _walk(api_client.get(f"/api/reports/nav-tree/?group_by={mode}").data["nodes"]):
            if leaf["type"] != "client":
                continue
            rows = api_client.get("/api/issues/", {**leaf["board_query"], "page_size": 100}).data["results"]
            project_keys = {r["project_key"] for r in rows}
            assert len(project_keys) == leaf["project_count"], (mode, leaf["id"], project_keys)


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
