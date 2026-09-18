import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def reporter():
    return User.objects.create_user(username="notif_reporter", email="notif_reporter@example.com", password="x")


@pytest.fixture
def assignee():
    return User.objects.create_user(username="notif_assignee", email="notif_assignee@example.com", password="x")


@pytest.fixture
def project(reporter):
    project = Project.objects.create(organization=Organization.get_solo(), key="NTF", name="Notif Test", lead=reporter)
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo", order=0)
    WorkflowStatus.objects.create(workflow=workflow, name="Done", category="done", order=1)
    return project


@pytest.fixture
def task_type():
    t, _ = IssueType.objects.get_or_create(name="Task", project=None)
    return t


@pytest.fixture
def api_client(reporter):
    client = APIClient()
    client.force_authenticate(user=reporter)
    return client


def test_assigning_issue_notifies_new_assignee(api_client, project, task_type, assignee):
    create = api_client.post(
        "/api/issues/", {"project": "NTF", "summary": "Notify me", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]

    api_client.patch(f"/api/issues/{key}/", {"assignee_id": assignee.id}, format="json")

    notif = Notification.objects.get(user=assignee, verb=Notification.Verb.ASSIGNED)
    assert notif.target_issue.key == key
    assert notif.actor.email == "notif_reporter@example.com"


def test_assigning_to_self_does_not_notify(api_client, project, task_type, reporter):
    create = api_client.post(
        "/api/issues/", {"project": "NTF", "summary": "Self assign", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]

    api_client.patch(f"/api/issues/{key}/", {"assignee_id": reporter.id}, format="json")

    assert not Notification.objects.filter(user=reporter, verb=Notification.Verb.ASSIGNED).exists()


def test_comment_notifies_assignee_and_watchers_but_not_author(api_client, project, task_type, assignee):
    create = api_client.post(
        "/api/issues/", {"project": "NTF", "summary": "Comment test", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    api_client.patch(f"/api/issues/{key}/", {"assignee_id": assignee.id}, format="json")
    Notification.objects.all().delete()

    api_client.post(f"/api/issues/{key}/comments/", {"body": {"type": "doc", "content": []}}, format="json")

    assert Notification.objects.filter(user=assignee, verb=Notification.Verb.COMMENTED).exists()


def test_notification_list_and_mark_read(api_client, project, task_type, assignee):
    create = api_client.post(
        "/api/issues/", {"project": "NTF", "summary": "Mark read test", "issue_type_id": task_type.id}, format="json"
    )
    key = create.data["key"]
    api_client.patch(f"/api/issues/{key}/", {"assignee_id": assignee.id}, format="json")

    assignee_client = APIClient()
    assignee_client.force_authenticate(user=assignee)

    unread = assignee_client.get("/api/notifications/unread-count/")
    assert unread.data["count"] == 1

    listing = assignee_client.get("/api/notifications/")
    notif_id = listing.data["results"][0]["id"]

    assignee_client.patch(f"/api/notifications/{notif_id}/read/")
    unread_after = assignee_client.get("/api/notifications/unread-count/")
    assert unread_after.data["count"] == 0
