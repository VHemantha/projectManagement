from datetime import date, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.timesheets.models import BillableRate, TimeEntry
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="bva_user", email="bva_user@example.com", password="x")


@pytest.fixture
def other_user():
    return User.objects.create_user(username="bva_other", email="bva_other@example.com", password="x")


@pytest.fixture
def project(user):
    project = Project.objects.create(
        organization=Organization.get_solo(), key="BVA", name="Budget Test", lead=user,
        budgeted_hours=10, job_value=Decimal("5000.00"),
    )
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    return project


@pytest.fixture
def task_type():
    task, _ = IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    return task


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_project_actual_hours_and_variance(api_client, project, user, task_type):
    status = WorkflowStatus.objects.get(workflow__project=project)
    issue = Issue.objects.create(project=project, issue_type=task_type, summary="Work", status=status, reporter=user)
    TimeEntry.objects.create(user=user, project=project, issue=issue, work_date=date.today(), duration=timedelta(hours=4))
    TimeEntry.objects.create(user=user, project=project, issue=issue, work_date=date.today(), duration=timedelta(hours=3))

    resp = api_client.get(f"/api/reports/budget-vs-actual/?project={project.key}")
    assert resp.status_code == 200
    row = resp.data["project"]
    assert row["budgeted_hours"] == 10
    assert row["actual_hours"] == 7.0
    assert row["variance_hours"] == -3.0
    assert row["pct_complete"] == 70.0


def test_effective_cost_uses_user_rate_over_project_and_org_defaults(api_client, project, user, other_user):
    BillableRate.objects.create(organization=Organization.get_solo(), scope="organization", hourly_rate=Decimal("50.00"))
    BillableRate.objects.create(organization=Organization.get_solo(), scope="project", project=project, hourly_rate=Decimal("80.00"))
    BillableRate.objects.create(organization=Organization.get_solo(), scope="user", user=user, hourly_rate=Decimal("120.00"))

    TimeEntry.objects.create(user=user, project=project, work_date=date.today(), duration=timedelta(hours=2), is_billable=True)
    TimeEntry.objects.create(user=other_user, project=project, work_date=date.today(), duration=timedelta(hours=1), is_billable=True)

    resp = api_client.get(f"/api/reports/budget-vs-actual/?project={project.key}")
    row = resp.data["project"]
    # user's own rate (120) x 2h = 240; other_user has no user rate, falls back to project rate
    # (80) x 1h = 80. Total = 320.
    assert Decimal(str(row["effective_cost"])) == Decimal("320.00")
    assert Decimal(str(row["margin"])) == Decimal("5000.00") - Decimal("320.00")


def test_non_billable_entries_are_excluded_from_effective_cost(api_client, project, user):
    BillableRate.objects.create(organization=Organization.get_solo(), scope="user", user=user, hourly_rate=Decimal("100.00"))
    TimeEntry.objects.create(user=user, project=project, work_date=date.today(), duration=timedelta(hours=5), is_billable=False)

    resp = api_client.get(f"/api/reports/budget-vs-actual/?project={project.key}")
    assert Decimal(str(resp.data["project"]["effective_cost"])) == Decimal("0.00")


def test_issue_level_breakdown_only_lists_issues_with_budget_or_logged_time(api_client, project, user, task_type):
    status = WorkflowStatus.objects.get(workflow__project=project)
    with_time = Issue.objects.create(project=project, issue_type=task_type, summary="Has time", status=status, reporter=user)
    untouched = Issue.objects.create(project=project, issue_type=task_type, summary="Untouched", status=status, reporter=user)
    TimeEntry.objects.create(user=user, project=project, issue=with_time, work_date=date.today(), duration=timedelta(hours=1))

    resp = api_client.get(f"/api/reports/budget-vs-actual/?project={project.key}")
    keys = {row["issue_key"] for row in resp.data["issues"]}
    assert with_time.key in keys
    assert untouched.key not in keys


def test_all_projects_summary_when_no_project_param(api_client, project):
    resp = api_client.get("/api/reports/budget-vs-actual/")
    assert resp.status_code == 200
    assert any(row["project_key"] == project.key for row in resp.data["projects"])
