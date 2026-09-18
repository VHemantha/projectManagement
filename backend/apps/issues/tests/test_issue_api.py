import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue, IssueHistory, Watcher
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="reporter", email="reporter@example.com", password="x")


@pytest.fixture
def other_user():
    return User.objects.create_user(username="assignee", email="assignee@example.com", password="x")


@pytest.fixture
def project(user):
    org = Organization.get_solo()
    project = Project.objects.create(organization=org, key="TST", name="Test Project", lead=user)
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo", order=0)
    WorkflowStatus.objects.create(workflow=workflow, name="Done", category="done", order=1)
    return project


@pytest.fixture
def task_type():
    task, _ = IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    return task


@pytest.fixture
def subtask_type():
    st, _ = IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    return st


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_create_issue_gets_default_status_and_rank(api_client, project, task_type):
    resp = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "First issue", "issue_type_id": task_type.id}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["key"] == "TST-1"
    assert resp.data["status"]["name"] == "To Do"
    assert resp.data["rank"]


def test_second_issue_ranks_after_first(api_client, project, task_type):
    r1 = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "One", "issue_type_id": task_type.id}, format="json"
    )
    r2 = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Two", "issue_type_id": task_type.id}, format="json"
    )
    assert r1.data["rank"] < r2.data["rank"]


def test_patch_status_writes_history_and_sets_resolved_at(api_client, project, task_type):
    create = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Track me", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    done_status = WorkflowStatus.objects.get(workflow__project=project, name="Done")

    resp = api_client.patch(f"/api/issues/{key}/", {"status_id": done_status.id}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"]["name"] == "Done"
    assert resp.data["resolved_at"] is not None

    issue = Issue.objects.get(key=key)
    history = IssueHistory.objects.filter(issue=issue, field_changed="status")
    assert history.count() == 1
    assert history.first().old_value == "To Do"
    assert history.first().new_value == "Done"


def test_patch_status_back_to_todo_clears_resolved_at(api_client, project, task_type):
    create = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Track me", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    done_status = WorkflowStatus.objects.get(workflow__project=project, name="Done")
    todo_status = WorkflowStatus.objects.get(workflow__project=project, name="To Do")

    api_client.patch(f"/api/issues/{key}/", {"status_id": done_status.id}, format="json")
    resp = api_client.patch(f"/api/issues/{key}/", {"status_id": todo_status.id}, format="json")
    assert resp.data["resolved_at"] is None


def test_assignee_change_is_tracked_in_history(api_client, project, task_type, other_user):
    create = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Assign me", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    resp = api_client.patch(f"/api/issues/{key}/", {"assignee_id": other_user.id}, format="json")
    assert resp.data["assignee"]["id"] == other_user.id
    history = IssueHistory.objects.get(issue__key=key, field_changed="assignee")
    assert history.new_value == other_user.display_name


def test_add_comment(api_client, project, task_type):
    create = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Comment me", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    body = {"type": "doc", "content": []}
    resp = api_client.post(f"/api/issues/{key}/comments/", {"body": body}, format="json")
    assert resp.status_code == 201
    assert resp.data["author"]["email"] == "reporter@example.com"

    list_resp = api_client.get(f"/api/issues/{key}/comments/")
    assert list_resp.data["count"] == 1


def test_add_subtask_links_parent_and_project(api_client, project, task_type, subtask_type):
    create = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Parent issue", "issue_type_id": task_type.id}, format="json"
    )
    parent_key = create.data["key"]
    resp = api_client.post(f"/api/issues/{parent_key}/subtasks/", {"summary": "Child work"}, format="json")
    assert resp.status_code == 201
    assert resp.data["parent"]["key"] == parent_key
    assert resp.data["issue_type"]["is_subtask"] is True

    parent_detail = api_client.get(f"/api/issues/{parent_key}/")
    assert len(parent_detail.data["subtasks"]) == 1


def test_watch_toggle(api_client, project, task_type, user):
    create = api_client.post(
        "/api/issues/", {"project": "TST", "summary": "Watch me", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]

    resp = api_client.post(f"/api/issues/{key}/watch/")
    assert resp.data["is_watching"] is True
    assert Watcher.objects.filter(issue__key=key, user=user).exists()

    resp = api_client.delete(f"/api/issues/{key}/watch/")
    assert resp.data["is_watching"] is False
    assert not Watcher.objects.filter(issue__key=key, user=user).exists()


def test_issue_list_filters_by_project(api_client, project, task_type):
    api_client.post("/api/issues/", {"project": "TST", "summary": "A", "issue_type_id": task_type.id}, format="json")
    other_project = Project.objects.create(
        organization=Organization.get_solo(), key="OTH", name="Other", lead=None
    )
    other_workflow = Workflow.objects.create(project=other_project)
    WorkflowStatus.objects.create(workflow=other_workflow, name="To Do", category="todo", order=0)
    api_client.post(
        "/api/issues/", {"project": "OTH", "summary": "B", "issue_type_id": task_type.id}, format="json"
    )

    resp = api_client.get("/api/issues/?project=TST")
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["summary"] == "A"
