import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="timer_user", email="timer_user@example.com", password="x")


@pytest.fixture
def project(user):
    project = Project.objects.create(organization=Organization.get_solo(), key="TMR", name="Timer Test", lead=user)
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    IssueType.objects.get_or_create(name="Task", project=None)
    return project


@pytest.fixture
def issue(project, user):
    from apps.issues.models import Issue

    status = WorkflowStatus.objects.get(workflow__project=project)
    task_type = IssueType.objects.get(name="Task")
    return Issue.objects.create(project=project, issue_type=task_type, summary="Track time", status=status, reporter=user)


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_running_is_null_when_no_timer_active(api_client):
    resp = api_client.get("/api/time-entries/running/")
    assert resp.status_code == 200
    assert resp.data is None


def test_start_creates_a_running_entry_linked_to_issue(api_client, issue, project):
    resp = api_client.post("/api/time-entries/start/", {"issue_id": issue.id}, format="json")
    assert resp.status_code == 201
    assert resp.data["is_running"] is True
    assert resp.data["issue"]["key"] == issue.key
    assert resp.data["project_key"] == project.key
    assert resp.data["created_via"] == "timer"


def test_starting_a_second_timer_stops_the_first(api_client, user):
    first = api_client.post("/api/time-entries/start/", {}, format="json")
    second = api_client.post("/api/time-entries/start/", {}, format="json")

    first_entry = TimeEntry.objects.get(id=first.data["id"])
    second_entry = TimeEntry.objects.get(id=second.data["id"])
    assert first_entry.is_running is False
    assert first_entry.duration is not None
    assert second_entry.is_running is True


def test_stop_sets_duration_and_running_false(api_client):
    start = api_client.post("/api/time-entries/start/", {}, format="json")
    resp = api_client.post(f"/api/time-entries/{start.data['id']}/stop/")
    assert resp.status_code == 200
    assert resp.data["is_running"] is False
    entry = TimeEntry.objects.get(id=start.data["id"])
    assert entry.duration is not None


def test_only_owner_can_stop_a_timer(api_client, user):
    start = api_client.post("/api/time-entries/start/", {}, format="json")
    other = User.objects.create_user(username="timer_other", email="timer_other@example.com", password="x")
    other_client = APIClient()
    other_client.force_authenticate(user=other)

    resp = other_client.post(f"/api/time-entries/{start.data['id']}/stop/")
    assert resp.status_code == 403


def test_manual_entry_sets_duration_from_hours_context(api_client, issue):
    resp = api_client.post(
        "/api/time-entries/",
        {"issue_id": issue.id, "work_date": "2026-01-05", "description": "manual work"},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["created_via"] == "manual"


def test_locked_entry_cannot_be_deleted(api_client, issue):
    entry = TimeEntry.objects.create(
        user=User.objects.get(username="timer_user"), issue=issue, project=issue.project,
        work_date="2026-01-01", locked=True,
    )
    resp = api_client.delete(f"/api/time-entries/{entry.id}/")
    assert resp.status_code == 400
    assert TimeEntry.objects.filter(id=entry.id).exists()


def test_duration_seconds_input_round_trips_to_duration_seconds_on_create(api_client, issue):
    resp = api_client.post(
        "/api/time-entries/",
        {"issue_id": issue.id, "work_date": "2026-01-05", "duration_seconds_input": 7200},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["duration_seconds"] == 7200
    entry = TimeEntry.objects.get(id=resp.data["id"])
    assert entry.duration.total_seconds() == 7200


def test_duration_seconds_input_round_trips_on_update(api_client, issue):
    created = api_client.post(
        "/api/time-entries/",
        {"issue_id": issue.id, "work_date": "2026-01-05", "duration_seconds_input": 3600},
        format="json",
    )
    resp = api_client.patch(
        f"/api/time-entries/{created.data['id']}/", {"duration_seconds_input": 5400}, format="json",
    )
    assert resp.status_code == 200
    assert resp.data["duration_seconds"] == 5400


def test_duration_seconds_input_rejects_negative_values(api_client, issue):
    resp = api_client.post(
        "/api/time-entries/",
        {"issue_id": issue.id, "work_date": "2026-01-05", "duration_seconds_input": -100},
        format="json",
    )
    assert resp.status_code == 400


def test_locked_entry_cannot_be_edited(api_client, issue):
    entry = TimeEntry.objects.create(
        user=User.objects.get(username="timer_user"), issue=issue, project=issue.project,
        work_date="2026-01-01", locked=True, duration=None,
    )
    resp = api_client.patch(f"/api/time-entries/{entry.id}/", {"description": "sneaky edit"}, format="json")
    assert resp.status_code == 400
