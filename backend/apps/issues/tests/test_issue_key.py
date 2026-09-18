import pytest

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


def _make_project(key="TRK"):
    org = Organization.get_solo()
    user = User.objects.create_user(username=f"u{key}", email=f"{key.lower()}@example.com", password="x")
    project = Project.objects.create(organization=org, key=key, name="Track", lead=user)
    workflow = Workflow.objects.create(project=project)
    status = WorkflowStatus.objects.create(workflow=workflow, name="To Do", category="todo")
    issue_type = IssueType.objects.create(name="Task")
    return project, user, status, issue_type


def test_issue_keys_are_sequential_per_project():
    project, user, status, issue_type = _make_project("TRK")
    issue1 = Issue.objects.create(
        project=project, issue_type=issue_type, summary="First", status=status, reporter=user
    )
    issue2 = Issue.objects.create(
        project=project, issue_type=issue_type, summary="Second", status=status, reporter=user
    )
    assert issue1.key == "TRK-1"
    assert issue2.key == "TRK-2"


def test_issue_keys_are_independent_per_project():
    project_a, user_a, status_a, type_a = _make_project("AAA")
    project_b, user_b, status_b, type_b = _make_project("BBB")
    issue_a = Issue.objects.create(
        project=project_a, issue_type=type_a, summary="A1", status=status_a, reporter=user_a
    )
    issue_b = Issue.objects.create(
        project=project_b, issue_type=type_b, summary="B1", status=status_b, reporter=user_b
    )
    assert issue_a.key == "AAA-1"
    assert issue_b.key == "BBB-1"


def test_new_issues_default_to_sequential_ranks():
    project, user, status, issue_type = _make_project("RNK")
    issue1 = Issue.objects.create(
        project=project, issue_type=issue_type, summary="First", status=status, reporter=user
    )
    issue2 = Issue.objects.create(
        project=project, issue_type=issue_type, summary="Second", status=status, reporter=user
    )
    assert issue1.rank
    assert issue2.rank
