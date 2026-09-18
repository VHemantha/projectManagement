import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project, ProjectMembership
from apps.workflow.models import Board, IssueType, Workflow

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="lead", email="lead@example.com", password="x")


@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def test_create_project_provisions_workflow_and_board(api_client, user):
    resp = api_client.post(
        "/api/projects/", {"key": "abc", "name": "ABC Project", "project_type": "kanban"}, format="json"
    )
    assert resp.status_code == 201
    project = Project.objects.get(key="ABC")  # key is upper-cased on save
    assert Workflow.objects.filter(project=project).exists()
    board = Board.objects.get(project=project)
    assert board.board_type == "kanban"
    assert len(board.column_config) == 4


def test_create_project_makes_creator_an_admin_member(api_client, user):
    resp = api_client.post(
        "/api/projects/", {"key": "XYZ", "name": "XYZ Project", "project_type": "scrum"}, format="json"
    )
    project = Project.objects.get(key="XYZ")
    membership = ProjectMembership.objects.get(project=project, user=user)
    assert membership.role == ProjectMembership.Role.ADMIN
    assert resp.data["lead"]["id"] == user.id


def test_project_list_reports_issue_counts(api_client, user):
    project = Project.objects.create(
        organization=Organization.get_solo(), key="CNT", name="Counter Project", lead=user
    )
    workflow = Workflow.objects.create(project=project)
    status = workflow.statuses.create(name="To Do", category="todo")
    issue_type, _ = IssueType.objects.get_or_create(name="Task", project=None)
    Issue.objects.create(project=project, issue_type=issue_type, summary="One", status=status, reporter=user)
    Issue.objects.create(project=project, issue_type=issue_type, summary="Two", status=status, reporter=user)

    resp = api_client.get("/api/projects/")
    row = next(r for r in resp.data["results"] if r["key"] == "CNT")
    assert row["issue_count"] == 2
