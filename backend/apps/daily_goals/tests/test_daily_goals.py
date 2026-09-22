from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.daily_goals.models import DailyGoal
from apps.orgs.models import Organization
from apps.teams.models import Team, TeamMembership

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead():
    return User.objects.create_user(username="dg_lead", email="dg_lead@example.com", password="x")


@pytest.fixture
def member():
    return User.objects.create_user(username="dg_member", email="dg_member@example.com", password="x")


@pytest.fixture
def outsider():
    return User.objects.create_user(username="dg_outsider", email="dg_outsider@example.com", password="x")


@pytest.fixture
def team(lead, member):
    team = Team.objects.create(organization=Organization.get_solo(), name="Goals Team")
    TeamMembership.objects.create(team=team, user=lead, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=team, user=member, role=TeamMembership.Role.MEMBER)
    return team


@pytest.fixture
def lead_client(lead):
    client = APIClient()
    client.force_authenticate(user=lead)
    return client


@pytest.fixture
def member_client(member):
    client = APIClient()
    client.force_authenticate(user=member)
    return client


@pytest.fixture
def outsider_client(outsider):
    client = APIClient()
    client.force_authenticate(user=outsider)
    return client


def _today():
    return str(date.today())


def test_create_and_list_own_goals(member_client):
    resp = member_client.post("/api/daily-goals/", {"date": _today(), "text": "Ship the thing"}, format="json")
    assert resp.status_code == 201
    assert resp.data["status"] == "planned"

    listing = member_client.get(f"/api/daily-goals/?date={_today()}")
    assert len(listing.data) == 1


def test_goals_default_to_the_requesters_own(member_client, member):
    DailyGoal.objects.create(user=member, date=date.today(), text="Mine")
    resp = member_client.get("/api/daily-goals/")
    assert all(g["user"]["id"] == member.id for g in resp.data)


def test_outsider_cannot_view_another_users_goals(outsider_client, member, team):
    DailyGoal.objects.create(user=member, date=date.today(), text="Private-ish")
    resp = outsider_client.get(f"/api/daily-goals/?user={member.id}")
    assert resp.status_code == 403


def test_team_lead_can_view_a_members_goals_via_user_param(lead_client, member, team):
    DailyGoal.objects.create(user=member, date=date.today(), text="Visible to lead")
    resp = lead_client.get(f"/api/daily-goals/?user={member.id}")
    assert resp.status_code == 200
    assert len(resp.data) == 1


def test_only_the_owner_can_edit_their_goal(member_client, outsider_client, member, team):
    goal = DailyGoal.objects.create(user=member, date=date.today(), text="Edit me")
    resp = outsider_client.patch(f"/api/daily-goals/{goal.id}/", {"status": "achieved"}, format="json")
    assert resp.status_code == 403

    resp2 = member_client.patch(f"/api/daily-goals/{goal.id}/", {"status": "achieved"}, format="json")
    assert resp2.status_code == 200


def test_marking_not_achieved_requires_a_note(member_client, member):
    goal = DailyGoal.objects.create(user=member, date=date.today(), text="Missed it")
    resp = member_client.patch(f"/api/daily-goals/{goal.id}/", {"status": "not_achieved"}, format="json")
    assert resp.status_code == 400

    resp2 = member_client.patch(
        f"/api/daily-goals/{goal.id}/", {"status": "not_achieved", "note": "Got pulled into an incident"}, format="json"
    )
    assert resp2.status_code == 200


def test_carry_over_creates_tomorrows_linked_goal(member_client, member):
    goal = DailyGoal.objects.create(
        user=member, date=date.today(), text="Recurring blocker", status="not_achieved", note="Blocked on design",
    )
    resp = member_client.post(f"/api/daily-goals/{goal.id}/carry-over/")
    assert resp.status_code == 201
    assert resp.data["date"] == str(date.today() + timedelta(days=1))
    assert resp.data["carried_over_from"] == goal.id
    assert resp.data["text"] == "Recurring blocker"
    assert resp.data["status"] == "planned"


def test_carry_over_chain_lets_the_team_leader_see_a_repeated_miss(lead_client, member_client, member, team):
    day1 = DailyGoal.objects.create(
        user=member, date=date.today(), text="Recurring blocker", status="not_achieved", note="Blocked on design",
    )
    r1 = member_client.post(f"/api/daily-goals/{day1.id}/carry-over/")
    day2_id = r1.data["id"]
    member_client.patch(f"/api/daily-goals/{day2_id}/", {"status": "not_achieved", "note": "Still blocked"}, format="json")
    r2 = member_client.post(f"/api/daily-goals/{day2_id}/carry-over/")
    day3_id = r2.data["id"]

    day3 = DailyGoal.objects.get(id=day3_id)
    assert day3.carried_over_from_id == day2_id
    assert day3.carried_over_from.carried_over_from_id == day1.id
    assert day3.date == date.today() + timedelta(days=2)

    # The team leader rollup can walk the chain back from the latest day's goal to see the
    # full history of a repeatedly-missed commitment, not just the most recent day.
    rollup = lead_client.get(f"/api/teams/{team.id}/daily-goals/?date_from={date.today()}&date_to={day3.date}")
    texts = {g["text"] for g in rollup.data}
    assert texts == {"Recurring blocker"}
    assert len(rollup.data) == 3


def test_carrying_over_an_already_achieved_goal_is_rejected(member_client, member):
    goal = DailyGoal.objects.create(user=member, date=date.today(), text="Done", status="achieved")
    resp = member_client.post(f"/api/daily-goals/{goal.id}/carry-over/")
    assert resp.status_code == 400


def test_team_rollup_requires_lead_or_admin(lead_client, member_client, outsider_client, team, member):
    DailyGoal.objects.create(user=member, date=date.today(), text="Rollup test")

    ok = lead_client.get(f"/api/teams/{team.id}/daily-goals/?date={_today()}")
    assert ok.status_code == 200
    assert len(ok.data) == 1

    denied = outsider_client.get(f"/api/teams/{team.id}/daily-goals/")
    assert denied.status_code == 403


def test_own_goals_date_range_filter(member_client, member):
    DailyGoal.objects.create(user=member, date=date.today() - timedelta(days=5), text="Five days ago")
    DailyGoal.objects.create(user=member, date=date.today(), text="Today")

    resp = member_client.get(
        f"/api/daily-goals/?date_from={date.today() - timedelta(days=1)}&date_to={date.today()}"
    )
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["text"] == "Today"


def test_team_rollup_date_range_filter(lead_client, member, team):
    DailyGoal.objects.create(user=member, date=date.today() - timedelta(days=10), text="Old")
    DailyGoal.objects.create(user=member, date=date.today(), text="Recent")

    resp = lead_client.get(
        f"/api/teams/{team.id}/daily-goals/?date_from={date.today() - timedelta(days=1)}&date_to={date.today()}"
    )
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["text"] == "Recent"


def test_workspace_admin_can_view_team_rollup_without_being_a_lead(member, team):
    admin = User.objects.create_user(username="dg_admin", email="dg_admin@example.com", password="x", is_staff=True)
    admin_client = APIClient()
    admin_client.force_authenticate(user=admin)
    DailyGoal.objects.create(user=member, date=date.today(), text="Admin visibility")

    resp = admin_client.get(f"/api/teams/{team.id}/daily-goals/")
    assert resp.status_code == 200
