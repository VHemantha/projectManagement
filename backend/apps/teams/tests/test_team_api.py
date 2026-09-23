import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.teams.models import Team, TeamMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="lead3", email="lead3@example.com", password="x")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_create_team(api_client):
    resp = api_client.post("/api/teams/", {"name": "Design Guild"}, format="json")
    assert resp.status_code == 201
    assert Team.objects.filter(name="Design Guild").exists()


def test_team_list_reports_member_count(api_client, user):
    from apps.orgs.models import Organization

    team = Team.objects.create(organization=Organization.get_solo(), name="Infra")
    other = User.objects.create_user(username="member1", email="member1@example.com", password="x")
    TeamMembership.objects.create(team=team, user=user, role="lead")
    TeamMembership.objects.create(team=team, user=other, role="member")

    resp = api_client.get("/api/teams/")
    row = next(r for r in resp.data["results"] if r["name"] == "Infra")
    assert row["member_count"] == 2


def test_creating_a_team_with_a_parent_nests_it(api_client, user):
    from apps.orgs.models import Organization

    group = Team.objects.create(organization=Organization.get_solo(), name="Group 1")
    resp = api_client.post("/api/teams/", {"name": "Team 1", "parent_id": group.id}, format="json")
    assert resp.status_code == 201
    assert resp.data["parent"]["id"] == group.id

    group_detail = api_client.get(f"/api/teams/{group.id}/")
    assert [t["id"] for t in group_detail.data["sub_teams"]] == [resp.data["id"]]


def test_a_team_cannot_be_parented_to_itself(api_client, user):
    from apps.orgs.models import Organization

    team = Team.objects.create(organization=Organization.get_solo(), name="Self Team")
    resp = api_client.patch(f"/api/teams/{team.id}/", {"parent_id": team.id}, format="json")
    assert resp.status_code == 400


def test_a_team_cannot_be_parented_to_its_own_sub_team(api_client, user):
    from apps.orgs.models import Organization

    org = Organization.get_solo()
    parent = Team.objects.create(organization=org, name="Parent Team")
    child = Team.objects.create(organization=org, name="Child Team", parent=parent)

    resp = api_client.patch(f"/api/teams/{parent.id}/", {"parent_id": child.id}, format="json")
    assert resp.status_code == 400


def test_add_and_remove_team_member(api_client, user):
    from apps.orgs.models import Organization

    team = Team.objects.create(organization=Organization.get_solo(), name="QA Guild")
    other = User.objects.create_user(username="member2", email="member2@example.com", password="x")

    resp = api_client.post(f"/api/teams/{team.id}/members/", {"user_id": other.id, "role": "member"}, format="json")
    assert resp.status_code == 201
    membership_id = resp.data["id"]

    detail = api_client.get(f"/api/teams/{team.id}/")
    assert len(detail.data["memberships"]) == 1

    del_resp = api_client.delete(f"/api/teams/{team.id}/members/{membership_id}/")
    assert del_resp.status_code == 204
    assert not TeamMembership.objects.filter(id=membership_id).exists()
