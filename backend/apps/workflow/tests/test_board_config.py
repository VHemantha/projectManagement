import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.orgs.models import Organization
from apps.projects.models import Project, ProjectMembership
from apps.workflow.models import Board
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


@pytest.fixture
def lead():
    return User.objects.create_user(username="bc_lead", email="bc_lead@example.com", password="x")


@pytest.fixture
def member():
    return User.objects.create_user(username="bc_member", email="bc_member@example.com", password="x")


@pytest.fixture
def project(lead):
    project = Project.objects.create(organization=Organization.get_solo(), key="BCF", name="Board Config Test", lead=lead)
    provision_project_defaults(project)
    ProjectMembership.objects.create(project=project, user=lead, role=ProjectMembership.Role.ADMIN)
    return project


@pytest.fixture
def board(project):
    return project.boards.first()


@pytest.fixture
def lead_client(lead):
    client = APIClient()
    client.force_authenticate(user=lead)
    return client


@pytest.fixture
def member_client(member):
    client = APIClient()
    client.force_authenticate(user=member)
    return client


def test_any_authenticated_user_can_read_board_config(member_client, board):
    resp = member_client.get(f"/api/boards/{board.id}/config/")
    assert resp.status_code == 200
    assert len(resp.data["column_config"]) == 4


def test_non_admin_member_cannot_patch_board_config(member_client, board):
    resp = member_client.patch(f"/api/boards/{board.id}/config/", {"swimlane_mode": "assignee"}, format="json")
    assert resp.status_code == 403


def test_project_lead_can_patch_swimlane_mode(lead_client, board):
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"swimlane_mode": "assignee"}, format="json")
    assert resp.status_code == 200
    board.refresh_from_db()
    assert board.swimlane_mode == "assignee"


def test_patching_card_fields_persists(lead_client, board):
    resp = lead_client.patch(
        f"/api/boards/{board.id}/config/", {"card_fields": ["assignee", "due_date"]}, format="json"
    )
    assert resp.status_code == 200
    board.refresh_from_db()
    assert board.card_fields == ["assignee", "due_date"]


def test_column_config_rejects_unknown_status_id(lead_client, board):
    bad_config = [{"name": "Ghost", "status_ids": [999999], "wip_limit": None}]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": bad_config}, format="json")
    assert resp.status_code == 400


def test_column_config_rejects_invalid_wip_limit(lead_client, board):
    status_id = board.column_config[0]["status_ids"][0]
    bad_config = [{"name": "To Do", "status_ids": [status_id], "wip_limit": -1}]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": bad_config}, format="json")
    assert resp.status_code == 400


def test_column_config_accepts_a_column_mapped_to_multiple_statuses(lead_client, board):
    status_ids = [c["status_ids"][0] for c in board.column_config[:2]]
    new_config = [{"name": "Ready for QA", "status_ids": status_ids, "wip_limit": 5}]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": new_config}, format="json")
    assert resp.status_code == 200
    board.refresh_from_db()
    assert board.column_config[0]["status_ids"] == status_ids


def test_workspace_admin_can_configure_board_without_being_project_lead(board):
    admin = User.objects.create_user(username="bc_admin", email="bc_admin@example.com", password="x", is_staff=True)
    admin_client = APIClient()
    admin_client.force_authenticate(user=admin)
    resp = admin_client.patch(f"/api/boards/{board.id}/config/", {"swimlane_mode": "epic"}, format="json")
    assert resp.status_code == 200


def test_default_transitions_are_provisioned_with_reassign_rules(project):
    transitions = project.workflow.transitions.all()
    assert transitions.count() == 5
    send_for_review = transitions.get(name="Send for review")
    assert send_for_review.set_current_responsible_to == "reviewer"


def test_workflow_transition_list_is_scoped_to_project(member_client, project):
    resp = member_client.get(f"/api/projects/{project.key}/workflow/transitions/")
    assert resp.status_code == 200
    assert len(resp.data) == 5


def test_only_set_current_responsible_to_is_editable_on_a_transition(lead_client, project):
    transition = project.workflow.transitions.get(name="Send for review")
    original_name = transition.name
    resp = lead_client.patch(
        f"/api/workflow-transitions/{transition.id}/",
        {"set_current_responsible_to": "assignee", "name": "Hacked name"},
        format="json",
    )
    assert resp.status_code == 200
    transition.refresh_from_db()
    assert transition.set_current_responsible_to == "assignee"
    assert transition.name == original_name


def test_non_admin_cannot_edit_transition_rules(member_client, project):
    transition = project.workflow.transitions.get(name="Send for review")
    resp = member_client.patch(
        f"/api/workflow-transitions/{transition.id}/", {"set_current_responsible_to": "assignee"}, format="json"
    )
    assert resp.status_code == 403
