import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Channel, Message, MessageIssueLink, MessageReaction
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project, ProjectMembership
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead():
    return User.objects.create_user(username="rest_lead", email="rest_lead@example.com", password="x")


@pytest.fixture
def outsider():
    return User.objects.create_user(username="rest_outsider", email="rest_outsider@example.com", password="x")


@pytest.fixture
def project(lead):
    project = Project.objects.create(organization=Organization.get_solo(), key="CRT", name="Chat REST Test", lead=lead)
    ProjectMembership.objects.create(project=project, user=lead, role="admin")
    workflow = Workflow.objects.create(project=project)
    WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    IssueType.objects.get_or_create(name="Task", project=None)
    return project


@pytest.fixture
def channel(project):
    return Channel.objects.get(linked_project=project)


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


def test_project_member_sees_project_channel_in_list(lead_client, channel):
    resp = lead_client.get("/api/chat/channels/")
    assert any(c["id"] == channel.id for c in resp.data["results"])


def test_non_member_does_not_see_project_channel(outsider_client, channel):
    resp = outsider_client.get("/api/chat/channels/")
    assert not any(c["id"] == channel.id for c in resp.data["results"])


def test_non_member_cannot_read_channel_detail(outsider_client, channel):
    resp = outsider_client.get(f"/api/chat/channels/{channel.id}/")
    assert resp.status_code == 403


def test_non_member_cannot_post_message(outsider_client, channel):
    resp = outsider_client.post(
        f"/api/chat/channels/{channel.id}/messages/",
        {"body": {"type": "doc", "content": []}},
        format="json",
    )
    assert resp.status_code == 403


def test_member_can_post_and_list_messages(lead_client, channel, lead):
    resp = lead_client.post(
        f"/api/chat/channels/{channel.id}/messages/",
        {"body": {"type": "doc", "content": []}},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["author"]["id"] == lead.id

    listing = lead_client.get(f"/api/chat/channels/{channel.id}/messages/")
    assert len(listing.data) == 1


def test_toggle_reaction_add_and_remove(lead_client, channel, lead):
    message = Message.objects.create(channel=channel, author=lead, body={"type": "doc", "content": []})

    add = lead_client.post(f"/api/chat/messages/{message.id}/reactions/", {"emoji": "🎉"}, format="json")
    assert add.status_code == 200
    assert MessageReaction.objects.filter(message=message, user=lead, emoji="🎉").exists()

    remove = lead_client.delete(f"/api/chat/messages/{message.id}/reactions/", {"emoji": "🎉"}, format="json")
    assert remove.status_code == 200
    assert not MessageReaction.objects.filter(message=message, user=lead, emoji="🎉").exists()


def test_create_task_from_message_writes_link_and_system_message(lead_client, channel, lead, project):
    message = Message.objects.create(channel=channel, author=lead, body={"type": "doc", "content": []})
    task_type = IssueType.objects.get(name="Task")

    resp = lead_client.post(
        f"/api/chat/messages/{message.id}/create-task/",
        {"project": "CRT", "summary": "Fix the thing", "issue_type_id": task_type.id},
        format="json",
    )
    assert resp.status_code == 201
    issue_key = resp.data["issue"]["key"]
    issue = Issue.objects.get(key=issue_key)

    assert MessageIssueLink.objects.filter(message=message, issue=issue, created_task=True).exists()
    system_message = Message.objects.get(id=resp.data["system_message"]["id"])
    assert system_message.is_system
    assert MessageIssueLink.objects.filter(message=system_message, issue=issue).exists()


def test_link_existing_task_to_message(lead_client, channel, lead, project):
    task_type = IssueType.objects.get(name="Task")
    status = WorkflowStatus.objects.get(workflow__project=project)
    issue = Issue.objects.create(project=project, issue_type=task_type, summary="Existing", status=status, reporter=lead)
    message = Message.objects.create(channel=channel, author=lead, body={"type": "doc", "content": []})

    resp = lead_client.post(f"/api/chat/messages/{message.id}/link-task/", {"issue_id": issue.id}, format="json")
    assert resp.status_code == 201
    assert MessageIssueLink.objects.filter(message=message, issue=issue, created_task=False).exists()


def test_issue_chat_links_surfaces_on_the_issue(lead_client, channel, lead, project):
    task_type = IssueType.objects.get(name="Task")
    status = WorkflowStatus.objects.get(workflow__project=project)
    issue = Issue.objects.create(project=project, issue_type=task_type, summary="Linked", status=status, reporter=lead)
    message = Message.objects.create(channel=channel, author=lead, body={"type": "doc", "content": []})
    MessageIssueLink.objects.create(message=message, issue=issue, created_task=False)

    resp = lead_client.get(f"/api/issues/{issue.key}/chat-links/")
    assert resp.status_code == 200
    assert len(resp.data) == 1
    assert resp.data[0]["channel_id"] == channel.id


def test_mark_read_updates_last_read_at(lead_client, channel, lead):
    resp = lead_client.post(f"/api/chat/channels/{channel.id}/mark-read/")
    assert resp.status_code == 200
    from apps.chat.models import ChannelMembership

    membership = ChannelMembership.objects.get(channel=channel, user=lead)
    assert membership.last_read_at is not None
