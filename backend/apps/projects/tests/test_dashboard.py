"""The workspace dashboard panel: budget, deadline, description and special notes."""
from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.projects.models import Project, ProjectMembership
from apps.timesheets.models import TimeEntry

pytestmark = pytest.mark.django_db


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def lead():
    return User.objects.create_user(username="lead", email="lead@example.com", password="x")


@pytest.fixture
def worker():
    return User.objects.create_user(username="worker", email="worker@example.com", password="x")


@pytest.fixture
def project(lead, worker):
    resp = _client(lead).post("/api/projects/", {"key": "Dash", "name": "Dashboard", "project_type": "kanban"}, format="json")
    assert resp.status_code == 201
    project = Project.objects.get(key="Dash")
    ProjectMembership.objects.create(project=project, user=worker, role=ProjectMembership.Role.MEMBER)
    return project


def test_detail_reports_actual_hours_from_time_entries(lead, project):
    TimeEntry.objects.create(user=lead, project=project, work_date=date.today(), duration=timedelta(hours=3))
    TimeEntry.objects.create(user=lead, project=project, work_date=date.today(), duration=timedelta(minutes=90))
    TimeEntry.objects.create(user=lead, project=project, work_date=date.today(), duration=None)  # running timer
    data = _client(lead).get("/api/projects/Dash/").data
    assert data["actual_hours"] == 4.5
    assert data["deadline"] is None
    assert data["special_notes"] == ""


def test_lead_edits_dashboard_fields(lead, project):
    resp = _client(lead).patch(
        "/api/projects/Dash/",
        {"budgeted_hours": 40, "deadline": "2026-12-11", "description": "Year end", "special_notes": "Call first"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    project.refresh_from_db()
    assert project.budgeted_hours == 40
    assert project.deadline == date(2026, 12, 11)
    assert project.special_notes == "Call first"
    assert resp.data["can_manage"] is True


def test_workspace_admin_and_staff_can_edit(project, worker):
    ProjectMembership.objects.filter(project=project, user=worker).update(role=ProjectMembership.Role.ADMIN)
    assert _client(worker).patch("/api/projects/Dash/", {"special_notes": "x"}, format="json").status_code == 200
    staff = User.objects.create_user(username="boss", email="boss@example.com", password="x", is_staff=True)
    assert _client(staff).patch("/api/projects/Dash/", {"deadline": None}, format="json").status_code == 200


@pytest.mark.parametrize(
    "patch",
    [{"budgeted_hours": 10}, {"deadline": "2026-12-01"}, {"description": "new"}, {"special_notes": "new"}],
)
def test_worker_can_view_but_not_change_dashboard_fields(worker, project, patch):
    client = _client(worker)
    data = client.get("/api/projects/Dash/").data
    assert data["can_manage"] is False
    resp = client.patch("/api/projects/Dash/", patch, format="json")
    assert resp.status_code == 403
    assert "workspace lead" in str(resp.data["detail"])


def test_worker_can_still_save_settings_that_send_unchanged_dashboard_fields(worker, project):
    """The settings form sends every field back; unchanged budget/description must not block it."""
    resp = _client(worker).patch(
        "/api/projects/Dash/",
        {"name": "Dashboard", "description": "", "budgeted_hours": None, "job_value_currency": "GBP"},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    project.refresh_from_db()
    assert project.job_value_currency == "GBP"


def test_budget_cannot_be_negative(lead, project):
    resp = _client(lead).patch("/api/projects/Dash/", {"budgeted_hours": -1}, format="json")
    assert resp.status_code == 400
    assert "budgeted_hours" in resp.data
