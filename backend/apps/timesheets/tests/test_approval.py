from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.timesheets.models import TimeEntry, Timesheet
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead():
    return User.objects.create_user(username="appr_lead", email="appr_lead@example.com", password="x")


@pytest.fixture
def member():
    return User.objects.create_user(username="appr_member", email="appr_member@example.com", password="x")


@pytest.fixture
def outsider():
    return User.objects.create_user(username="appr_outsider", email="appr_outsider@example.com", password="x")


@pytest.fixture
def project(lead):
    project = Project.objects.create(organization=Organization.get_solo(), key="APR", name="Approval Test", lead=lead)
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    IssueType.objects.get_or_create(name="Task", project=None)
    return project


def _week():
    start = date(2026, 1, 5)
    return start, start + timedelta(days=6)


@pytest.fixture
def timesheet(member, project):
    start, end = _week()
    TimeEntry.objects.create(
        user=member, project=project, work_date=start, duration=timedelta(hours=8), is_running=False,
    )
    return Timesheet.objects.create(user=member, period_start=start, period_end=end)


@pytest.fixture
def member_client(member):
    client = APIClient()
    client.force_authenticate(user=member)
    return client


@pytest.fixture
def lead_client(lead):
    client = APIClient()
    client.force_authenticate(user=lead)
    return client


@pytest.fixture
def outsider_client(outsider):
    client = APIClient()
    client.force_authenticate(user=outsider)
    return client


def test_submit_locks_entries_in_the_period(member_client, timesheet, member, project):
    resp = member_client.post(f"/api/timesheets/{timesheet.id}/submit/")
    assert resp.status_code == 200
    assert resp.data["status"] == "submitted"
    assert TimeEntry.objects.filter(user=member, project=project).first().locked is True


def test_project_lead_can_approve_submitted_timesheet(member_client, lead_client, timesheet):
    member_client.post(f"/api/timesheets/{timesheet.id}/submit/")
    resp = lead_client.post(f"/api/timesheets/{timesheet.id}/approve/")
    assert resp.status_code == 200
    assert resp.data["status"] == "approved"


def test_non_lead_non_admin_cannot_approve(member_client, outsider_client, timesheet):
    member_client.post(f"/api/timesheets/{timesheet.id}/submit/")
    resp = outsider_client.post(f"/api/timesheets/{timesheet.id}/approve/")
    assert resp.status_code == 403


def test_reject_requires_a_note_and_unlocks_entries(member_client, lead_client, timesheet, member, project):
    member_client.post(f"/api/timesheets/{timesheet.id}/submit/")

    no_note = lead_client.post(f"/api/timesheets/{timesheet.id}/reject/", {}, format="json")
    assert no_note.status_code == 400

    resp = lead_client.post(f"/api/timesheets/{timesheet.id}/reject/", {"note": "Missing details"}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "rejected"
    assert resp.data["reviewer_note"] == "Missing details"
    assert TimeEntry.objects.filter(user=member, project=project).first().locked is False


def test_workspace_admin_can_approve_without_being_project_lead(member_client, timesheet):
    admin = User.objects.create_user(username="ws_admin", email="ws_admin@example.com", password="x", is_staff=True)
    admin_client = APIClient()
    admin_client.force_authenticate(user=admin)

    member_client.post(f"/api/timesheets/{timesheet.id}/submit/")
    resp = admin_client.post(f"/api/timesheets/{timesheet.id}/approve/")
    assert resp.status_code == 200


def test_inbox_lists_submitted_sheets_for_the_lead(member_client, lead_client, timesheet):
    member_client.post(f"/api/timesheets/{timesheet.id}/submit/")
    resp = lead_client.get("/api/timesheets/?inbox=true")
    assert any(t["id"] == timesheet.id for t in resp.data["results"])


def test_creating_a_timesheet_for_the_same_week_twice_is_idempotent(member_client):
    start, end = _week()
    r1 = member_client.post(
        "/api/timesheets/", {"period_start": str(start), "period_end": str(end)}, format="json"
    )
    r2 = member_client.post(
        "/api/timesheets/", {"period_start": str(start), "period_end": str(end)}, format="json"
    )
    assert r1.status_code == 201
    assert r2.status_code == 200
    assert r1.data["id"] == r2.data["id"]
    assert Timesheet.objects.filter(period_start=start).count() == 1
