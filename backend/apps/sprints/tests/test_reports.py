from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.sprints.models import Sprint
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="rpt_lead", email="rpt_lead@example.com", password="x")


@pytest.fixture
def project(user):
    project = Project.objects.create(organization=Organization.get_solo(), key="RPT", name="Report Test", lead=user)
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo", order=0)
    WorkflowStatus.objects.create(workflow=workflow, name="Done", category="done", order=1)
    return project


@pytest.fixture
def task_type():
    t, _ = IssueType.objects.get_or_create(name="Task", project=None)
    return t


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_burndown_requires_sprint_dates(api_client, project):
    sprint = Sprint.objects.create(project=project, name="No dates", order=0)
    resp = api_client.get(f"/api/sprints/{sprint.id}/burndown/")
    assert resp.status_code == 400


def test_burndown_computes_remaining_from_resolved_issues(api_client, project, task_type, user):
    today = timezone.now().date()
    sprint = Sprint.objects.create(
        project=project, name="S1", order=0, state=Sprint.State.ACTIVE,
        start_date=today - timedelta(days=4), end_date=today + timedelta(days=4),
    )
    todo = WorkflowStatus.objects.get(workflow__project=project, name="To Do")
    done = WorkflowStatus.objects.get(workflow__project=project, name="Done")

    Issue.objects.create(
        project=project, issue_type=task_type, summary="Open", status=todo, reporter=user,
        sprint=sprint, story_points=5,
    )
    Issue.objects.create(
        project=project, issue_type=task_type, summary="Resolved", status=done, reporter=user,
        sprint=sprint, story_points=3, resolved_at=timezone.now() - timedelta(days=1),
    )

    resp = api_client.get(f"/api/sprints/{sprint.id}/burndown/")
    assert resp.status_code == 200
    assert resp.data["total_points"] == 8
    # remaining should drop to 5 (8 - 3) once we reach the resolution day, then hold
    assert resp.data["remaining"][0] == 8
    assert 5 in resp.data["remaining"]


def test_velocity_reports_committed_and_completed_points(api_client, project, task_type, user):
    sprint = Sprint.objects.create(
        project=project, name="S1", order=0, state=Sprint.State.CLOSED, completed_at=timezone.now(),
    )
    todo = WorkflowStatus.objects.get(workflow__project=project, name="To Do")
    done = WorkflowStatus.objects.get(workflow__project=project, name="Done")
    Issue.objects.create(
        project=project, issue_type=task_type, summary="Done one", status=done, reporter=user,
        sprint=sprint, story_points=5,
    )
    Issue.objects.create(
        project=project, issue_type=task_type, summary="Not done", status=todo, reporter=user,
        sprint=sprint, story_points=2,
    )

    resp = api_client.get("/api/projects/RPT/velocity/")
    assert resp.status_code == 200
    row = next(r for r in resp.data if r["sprint"] == "S1")
    assert row["committed"] == 7
    assert row["completed"] == 5


def test_recent_activity_lists_across_projects(api_client, project, task_type, user):
    create = api_client.post(
        "/api/issues/", {"project": "RPT", "summary": "Track history", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    done = WorkflowStatus.objects.get(workflow__project=project, name="Done")
    api_client.patch(f"/api/issues/{key}/", {"status_id": done.id}, format="json")

    resp = api_client.get("/api/activity/recent/")
    assert resp.status_code == 200
    assert any(a["issue_key"] == key for a in resp.data)
