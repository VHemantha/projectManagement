"""GET /api/users/hierarchy/ — admins on top, workers grouped by team."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orgs.models import Organization
from apps.teams.models import Team, TeamMembership

pytestmark = pytest.mark.django_db


def make(name, **extra):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title(), **extra)


def test_hierarchy_puts_admins_on_top_and_groups_workers_by_team():
    org = Organization.get_solo()
    boss = make("boss", is_staff=True)
    lead, ann, bob, loner = make("lead"), make("ann"), make("bob"), make("loner")
    make("gone", is_active=False)
    accounts = Team.objects.create(organization=org, name="Accounts")
    payroll = Team.objects.create(organization=org, name="Payroll", parent=accounts)
    TeamMembership.objects.create(team=accounts, user=lead, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=accounts, user=bob)
    TeamMembership.objects.create(team=accounts, user=ann)
    TeamMembership.objects.create(team=accounts, user=boss)  # admin in a team: shown at the top only
    TeamMembership.objects.create(team=payroll, user=ann)

    client = APIClient()
    client.force_authenticate(user=ann)
    data = client.get("/api/users/hierarchy/").data

    assert data["derived"] is True
    assert [a["display_name"] for a in data["admins"]] == ["Boss"]
    assert data["admins"][0]["role"] == "admin"
    assert data["admins"][0]["teams"] == ["Accounts"]

    teams = {t["name"]: t for t in data["teams"]}
    assert [u["display_name"] for u in teams["Accounts"]["leads"]] == ["Lead"]
    assert [u["display_name"] for u in teams["Accounts"]["members"]] == ["Ann", "Bob"]
    assert teams["Payroll"]["parent_id"] == teams["Accounts"]["id"]
    assert [u["display_name"] for u in teams["Payroll"]["members"]] == ["Ann"]
    assert sorted(teams["Accounts"]["members"][0]["teams"]) == ["Accounts", "Payroll"]

    assert [u["display_name"] for u in data["no_team"]] == ["Loner"]
    everyone = str(data)
    assert "Gone" not in everyone


def test_hierarchy_needs_login():
    assert APIClient().get("/api/users/hierarchy/").status_code == 401


def test_the_ceo_and_team_leads_are_on_top_the_ceo_first():
    """Employee types (AFIT, 16 Nov 2026): Standard, Team Lead (an organisation admin) and the CEO."""
    make("anna", is_staff=True)
    make("zed", role=User.Role.CEO)
    client = APIClient()
    client.force_authenticate(user=make("pat"))
    data = client.get("/api/users/hierarchy/").data
    assert [(a["display_name"], a["role"]) for a in data["admins"]] == [("Zed", "ceo"), ("Anna", "admin")]
    assert data["basis"].startswith("The CEO and Team Leads are at the top; Standard employees")
