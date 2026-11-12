"""The CEO edits names across the organisation (AFIT, 12 Nov 2026): the organisation's own name and
anyone's name and job title; workspaces, sub-workspaces and projects through their own endpoints.
Only the CEO may; every change and every refusal is in the audit log."""
import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.coordinator.models import AuditEntry
from apps.orgs.models import Organization
from apps.precheck.tests.test_direction_drafting import make_job
from apps.teams.models import Team

pytestmark = pytest.mark.django_db


def person(name, **extra):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title(), **extra)


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def ceo():
    return person("dushan", role=User.Role.CEO)


def test_everyone_sees_the_organisations_name_and_only_the_ceo_may_change_it(ceo):
    pat = person("pat")
    r = api(pat).get("/api/organization/")
    assert r.status_code == 200 and r.data["name"] == Organization.get_solo().name and r.data["can_edit"] is False
    assert api(ceo).get("/api/organization/").data["can_edit"] is True

    r = api(ceo).patch("/api/organization/", {"name": "  AFIT   Connect  "}, format="json")
    assert r.status_code == 200 and r.data["name"] == "AFIT Connect"
    assert Organization.get_solo().name == "AFIT Connect"
    entry = AuditEntry.objects.get(action="rename organisation", allowed=True)
    assert entry.actor == ceo and entry.detail == {"before": "TASKO", "after": "AFIT Connect"}

    assert api(ceo).patch("/api/organization/", {"name": "   "}, format="json").status_code == 400


def test_an_admin_who_is_not_the_ceo_is_refused_and_the_attempt_logged(ceo):
    admin = person("ann", is_staff=True)
    assert api(admin).patch("/api/organization/", {"name": "Mine"}, format="json").status_code == 403
    assert api(admin).patch(f"/api/users/{ceo.id}/", {"display_name": "X"}, format="json").status_code == 403
    assert Organization.get_solo().name == "TASKO"
    assert set(AuditEntry.objects.filter(allowed=False).values_list("action", flat=True)) == {"rename organisation", "rename person"}


def test_the_ceo_renames_a_person_and_their_job_title(ceo):
    pat = person("pat")
    r = api(ceo).patch(f"/api/users/{pat.id}/", {"display_name": " Patricia  Ng ", "job_title": "Senior accountant"}, format="json")
    assert r.status_code == 200 and r.data["display_name"] == "Patricia Ng" and r.data["job_title"] == "Senior accountant"
    pat.refresh_from_db()
    assert (pat.display_name, pat.job_title, pat.email) == ("Patricia Ng", "Senior accountant", "pat@example.com")
    assert AuditEntry.objects.get(action="rename person").target == "pat@example.com"
    # A name can't be emptied; the coordination agent's account isn't a person to rename.
    assert api(ceo).patch(f"/api/users/{pat.id}/", {"display_name": ""}, format="json").status_code == 400
    agent = person("bot", is_agent=True)
    assert api(ceo).patch(f"/api/users/{agent.id}/", {"display_name": "Robot"}, format="json").status_code == 404


def test_the_ceo_renames_workspaces_sub_workspaces_and_projects_through_their_own_endpoints(ceo):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    team = Team.objects.create(organization=Organization.get_solo(), name="Team 1")
    client = Client.objects.get(name="Smith")
    assert api(ceo).patch(f"/api/teams/{team.id}/", {"name": "Rentals"}, format="json").status_code == 200
    assert api(ceo).patch(f"/api/clients/{client.id}/", {"name": "Smith Family Trust"}, format="json").status_code == 200
    r = api(ceo).patch(f"/api/projects/{issue.project.key}/", {"name": "Smith rentals FY26"}, format="json")
    assert r.status_code == 200
    team.refresh_from_db()
    client.refresh_from_db()
    issue.project.refresh_from_db()
    assert (team.name, client.name, issue.project.name) == ("Rentals", "Smith Family Trust", "Smith rentals FY26")
