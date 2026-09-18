import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from apps.chat.models import Channel
from apps.issues.models import Attachment, Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="att_user", email="att_user@example.com", password="x")


@pytest.fixture
def issue(user):
    project = Project.objects.create(organization=Organization.get_solo(), key="ATT", name="Attach Test", lead=user)
    workflow = Workflow.objects.create(project=project)
    status = WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    issue_type, _ = IssueType.objects.get_or_create(name="Task", project=None)
    return Issue.objects.create(project=project, issue_type=issue_type, summary="Attach me", status=status, reporter=user)


def test_attachment_can_belong_to_an_issue(issue, user):
    attachment = Attachment.objects.create(
        issue=issue, file=SimpleUploadedFile("a.txt", b"hi"), uploaded_by=user
    )
    assert attachment.message_id is None


def test_attachment_can_belong_to_a_message(issue, user):
    channel = Channel.objects.get(linked_project=issue.project)
    from apps.chat.models import Message

    message = Message.objects.create(channel=channel, author=user, body={"type": "doc", "content": []})
    attachment = Attachment.objects.create(
        message=message, file=SimpleUploadedFile("a.txt", b"hi"), uploaded_by=user
    )
    assert attachment.issue_id is None


def test_attachment_cannot_have_both_or_neither_parent(issue, user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Attachment.objects.create(file=SimpleUploadedFile("a.txt", b"hi"), uploaded_by=user)
