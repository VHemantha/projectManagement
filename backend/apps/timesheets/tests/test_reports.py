from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.timesheets.models import TimeEntry
from apps.workflow.models import Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="rep_user", email="rep_user@example.com", password="x")


@pytest.fixture
def project(user):
    project = Project.objects.create(organization=Organization.get_solo(), key="REP", name="Reports Test", lead=user)
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    return project


@pytest.fixture
def other_project(user):
    return Project.objects.create(organization=Organization.get_solo(), key="OTH", name="Other Project", lead=user)


@pytest.fixture
def client(user):
    api = APIClient()
    api.force_authenticate(user=user)
    return api


def test_csv_export_requires_authentication(project):
    resp = APIClient().get("/api/time-reports/export/")
    assert resp.status_code == 401


def test_csv_export_includes_matching_entries_and_respects_filters(client, user, project, other_project):
    TimeEntry.objects.create(
        user=user, project=project, work_date=date(2026, 2, 1),
        duration=timedelta(hours=2), description="Did the thing", is_billable=True,
    )
    TimeEntry.objects.create(
        user=user, project=other_project, work_date=date(2026, 2, 1),
        duration=timedelta(hours=3), description="Other project work", is_billable=False,
    )

    resp = client.get("/api/time-reports/export/", {"project": "REP"})
    assert resp.status_code == 200
    assert resp["Content-Type"] == "text/csv"
    body = resp.content.decode()
    lines = body.strip().splitlines()
    assert lines[0] == "Date,User,Project,Issue,Description,Hours,Billable,Created via"
    assert len(lines) == 2
    assert "Did the thing" in lines[1]
    assert "2.0" in lines[1]
    assert "Other project work" not in body


def test_csv_export_date_range_filter_excludes_entries_outside_range(client, user, project):
    TimeEntry.objects.create(
        user=user, project=project, work_date=date(2026, 1, 1), duration=timedelta(hours=1),
    )
    TimeEntry.objects.create(
        user=user, project=project, work_date=date(2026, 3, 1), duration=timedelta(hours=1),
    )

    resp = client.get("/api/time-reports/export/", {"date_from": "2026-02-01", "date_to": "2026-02-28"})
    lines = resp.content.decode().strip().splitlines()
    assert len(lines) == 1  # header only, both entries fall outside the range
