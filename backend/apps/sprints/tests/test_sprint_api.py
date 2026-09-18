import pytest
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
    return User.objects.create_user(username="lead", email="lead2@example.com", password="x")


@pytest.fixture
def project(user):
    project = Project.objects.create(organization=Organization.get_solo(), key="SPR", name="Sprint Test", lead=user)
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


def test_create_sprint_assigns_incrementing_order(api_client, project):
    r1 = api_client.post("/api/projects/SPR/sprints/", {"name": "S1"}, format="json")
    r2 = api_client.post("/api/projects/SPR/sprints/", {"name": "S2"}, format="json")
    assert r1.data["order"] == 0
    assert r2.data["order"] == 1
    assert r1.data["state"] == "future"


def test_start_sprint_requires_no_other_active_sprint(api_client, project):
    s1 = Sprint.objects.create(project=project, name="S1", order=0)
    s2 = Sprint.objects.create(project=project, name="S2", order=1)

    resp = api_client.post(
        f"/api/sprints/{s1.id}/start/", {"start_date": "2025-01-01", "end_date": "2025-01-14"}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["state"] == "active"

    resp2 = api_client.post(
        f"/api/sprints/{s2.id}/start/", {"start_date": "2025-01-01", "end_date": "2025-01-14"}, format="json"
    )
    assert resp2.status_code == 400


def test_complete_sprint_moves_incomplete_issues_to_backlog(api_client, project, task_type, user):
    sprint = Sprint.objects.create(project=project, name="S1", order=0, state=Sprint.State.ACTIVE)
    todo = WorkflowStatus.objects.get(workflow__project=project, name="To Do")
    done = WorkflowStatus.objects.get(workflow__project=project, name="Done")

    incomplete = Issue.objects.create(
        project=project, issue_type=task_type, summary="Unfinished", status=todo, reporter=user, sprint=sprint
    )
    complete = Issue.objects.create(
        project=project, issue_type=task_type, summary="Finished", status=done, reporter=user, sprint=sprint
    )

    resp = api_client.post(f"/api/sprints/{sprint.id}/complete/", {"move_to": "backlog"}, format="json")
    assert resp.status_code == 200
    assert resp.data["state"] == "closed"

    incomplete.refresh_from_db()
    complete.refresh_from_db()
    assert incomplete.sprint_id is None
    assert complete.sprint_id == sprint.id


def test_complete_sprint_can_move_incomplete_issues_to_another_sprint(api_client, project, task_type, user):
    sprint = Sprint.objects.create(project=project, name="S1", order=0, state=Sprint.State.ACTIVE)
    next_sprint = Sprint.objects.create(project=project, name="S2", order=1, state=Sprint.State.FUTURE)
    todo = WorkflowStatus.objects.get(workflow__project=project, name="To Do")

    issue = Issue.objects.create(
        project=project, issue_type=task_type, summary="Carry over", status=todo, reporter=user, sprint=sprint
    )

    api_client.post(f"/api/sprints/{sprint.id}/complete/", {"move_to": str(next_sprint.id)}, format="json")
    issue.refresh_from_db()
    assert issue.sprint_id == next_sprint.id


def test_issue_move_sets_rank_between_neighbors_and_changes_sprint(api_client, project, task_type, user):
    sprint = Sprint.objects.create(project=project, name="S1", order=0)
    a = api_client.post("/api/issues/", {"project": "SPR", "summary": "A", "issue_type_id": task_type.id}, format="json")
    b = api_client.post("/api/issues/", {"project": "SPR", "summary": "B", "issue_type_id": task_type.id}, format="json")
    c = api_client.post("/api/issues/", {"project": "SPR", "summary": "C", "issue_type_id": task_type.id}, format="json")

    resp = api_client.post(
        f"/api/issues/{c.data['key']}/move/",
        {"before_id": a.data["id"], "after_id": b.data["id"], "sprint_id": sprint.id},
        format="json",
    )
    assert resp.status_code == 200
    assert a.data["rank"] < resp.data["rank"] < b.data["rank"]
    assert resp.data["sprint"]["id"] == sprint.id

    from apps.issues.models import IssueHistory

    assert IssueHistory.objects.filter(issue__key=c.data["key"], field_changed="sprint").exists()
