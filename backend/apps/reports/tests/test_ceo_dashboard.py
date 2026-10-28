"""The CEO's organisation dashboard (AFIT, 28 Oct 2026)."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType, WorkflowStatus
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup():
    org = Organization.get_solo()
    ceo = User.objects.create_user(username="dushan", email="dushan@afitconnect.com", password="x", role=User.Role.CEO)
    pat = User.objects.create_user(username="pat", email="pat@example.com", password="x", display_name="Pat")
    team = Team.objects.create(organization=org, name="Team 1")
    rwca = Client.objects.create(organization=org, name="RWCA", team=team)
    project = Project.objects.create(organization=org, key="RWCA", name="RWCA", lead=ceo, client=rwca)
    provision_project_defaults(project)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    stage = {s.name: s for s in WorkflowStatus.objects.filter(workflow__project=project)}
    today = timezone.localdate()

    def make(summary, status, **kw):
        return Issue.objects.create(project=project, issue_type=task, summary=summary, status=stage[status], reporter=ceo, assignee=pat, **kw)

    late = make("Late", "In Progress", due_date=today - timedelta(days=3), budgeted_hours=2)
    make("Soon", "To Start", due_date=today + timedelta(days=2), priority="high")
    make("Done", "Complete", resolved_at=timezone.now())
    TimeEntry.objects.create(user=pat, issue=late, project=project, work_date=today, duration=timedelta(hours=3))
    return ceo, pat


def test_the_ceo_sees_the_whole_organisation(setup):
    ceo, _ = setup
    c = APIClient()
    c.force_authenticate(ceo)
    r = c.get("/api/reports/ceo-dashboard/")
    assert r.status_code == 200, r.data
    t = r.data["totals"]
    assert (t["open"], t["overdue"], t["due_this_week"], t["completed_30_days"], t["hours_this_month"]) == (2, 1, 1, 1, 3.0)
    assert [s["stage"] for s in r.data["stages"]][:3] == ["To Start", "In Progress", "Waiting for Info"]
    assert {s["stage"]: s["tasks"] for s in r.data["stages"]}["Complete"] == 1
    assert r.data["workspaces"] == [{"workspace": "Team 1", "open": 2, "overdue": 1, "completed_30": 1, "on_time": 1}]
    assert r.data["workload"] == [{"person": "Pat", "open": 2, "overdue": 1, "on_time": 1}]
    assert r.data["over_budget"][0]["key"] == "RWCA-1" and r.data["over_budget"][0]["actual"] == 3.0
    assert len(r.data["flow"]) == 12 and sum(w["completed"] for w in r.data["flow"]) == 1
    assert sum(w["billable"] for w in r.data["hours"]) == 3.0
    assert {p["priority"]: p["tasks"] for p in r.data["priorities"]}["High"] == 1


def test_no_one_else_can_see_it(setup):
    _, pat = setup
    c = APIClient()
    c.force_authenticate(pat)
    assert c.get("/api/reports/ceo-dashboard/").status_code == 403
