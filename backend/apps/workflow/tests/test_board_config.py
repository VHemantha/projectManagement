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


# --- Board customisation: new columns, validation, colour coding, unused statuses -------------


def _issue(project, status, summary="Card"):
    from apps.issues.models import Issue
    from apps.workflow.models import IssueType

    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    n = Issue.objects.filter(project=project).count() + 1
    return Issue.objects.create(
        project=project, key=f"{project.key}-{n}", summary=summary, issue_type=task, status=status,
        rank=f"{n:06d}", reporter=project.lead,
    )


def test_new_column_creates_and_maps_a_new_status(lead_client, board, project):
    config = board.column_config + [
        {"name": "QA", "status_ids": [], "wip_limit": 2, "color": "#FF5630", "new_status": {"category": "in_progress"}}
    ]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json")
    assert resp.status_code == 200, resp.data
    qa = project.workflow.statuses.get(name="QA")
    assert qa.category == "in_progress"
    assert qa.order > max(s.order for s in project.workflow.statuses.exclude(pk=qa.pk))
    board.refresh_from_db()
    assert board.column_config[-1] == {"name": "QA", "status_ids": [qa.id], "wip_limit": 2, "color": "#ff5630"}


def test_new_column_cannot_duplicate_an_existing_status_name(lead_client, board):
    config = board.column_config + [{"name": "in review", "status_ids": [], "new_status": {"category": "todo"}}]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json")
    assert resp.status_code == 400
    assert "already exists" in str(resp.data)


def test_a_status_cannot_be_in_two_columns(lead_client, board):
    config = [dict(c) for c in board.column_config]
    config[1]["status_ids"] = config[1]["status_ids"] + config[0]["status_ids"]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json")
    assert resp.status_code == 400
    assert "only be in one column" in str(resp.data)


def test_removing_a_column_that_still_has_issues_is_rejected(lead_client, board, project):
    in_review = project.workflow.statuses.get(name="In Review")
    _issue(project, in_review)
    config = [c for c in board.column_config if in_review.id not in c["status_ids"]]
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json")
    assert resp.status_code == 400
    assert "In Review (1 job)" in str(resp.data)


def test_column_color_must_be_hex(lead_client, board):
    config = [dict(c) for c in board.column_config]
    config[0]["color"] = "red"
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json")
    assert resp.status_code == 400


def test_card_colour_coding_persists(lead_client, board):
    payload = {
        "card_color_rule": "due_date",
        "card_color_style": "tint",
        "card_colors": {"due_date": {"overdue": "#AA0000"}, "priority": {"high": "#123456"}, "issue_type": {"3": "#00ff00"}},
    }
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", payload, format="json")
    assert resp.status_code == 200, resp.data
    board.refresh_from_db()
    assert board.card_color_rule == "due_date"
    assert board.card_color_style == "tint"
    assert board.card_colors["due_date"] == {"overdue": "#aa0000"}


@pytest.mark.parametrize(
    "card_colors",
    [
        {"label": {"1": "#000000"}},
        {"priority": {"urgent": "#000000"}},
        {"due_date": {"overdue": "crimson"}},
        {"issue_type": {"bug": "#000000"}},
    ],
)
def test_card_colours_are_validated(lead_client, board, card_colors):
    resp = lead_client.patch(f"/api/boards/{board.id}/config/", {"card_colors": card_colors}, format="json")
    assert resp.status_code == 400


def test_board_statuses_report_issue_counts(lead_client, project):
    todo = project.workflow.statuses.get(name="To Do")
    _issue(project, todo)
    resp = lead_client.get(f"/api/projects/{project.key}/board/")
    counts = {s["name"]: s["issue_count"] for s in resp.data["statuses"]}
    assert counts["To Do"] == 1
    assert counts["Done"] == 0


def test_unused_status_can_be_deleted_but_used_ones_cannot(lead_client, member_client, board, project):
    in_review = project.workflow.statuses.get(name="In Review")
    url = f"/api/boards/{board.id}/statuses/{in_review.id}/"

    # Still on a column.
    resp = lead_client.delete(url)
    assert resp.status_code == 400
    assert "column" in resp.data["detail"]

    config = [c for c in board.column_config if in_review.id not in c["status_ids"]]
    assert lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json").status_code == 200

    assert member_client.delete(url).status_code == 403
    assert lead_client.delete(url).status_code == 204
    assert not project.workflow.statuses.filter(pk=in_review.pk).exists()


def test_status_with_issues_cannot_be_deleted(lead_client, board, project):
    todo = project.workflow.statuses.get(name="To Do")
    _issue(project, todo)
    resp = lead_client.delete(f"/api/boards/{board.id}/statuses/{todo.id}/")
    assert resp.status_code == 400
    assert "1 job" in resp.data["detail"]


def test_new_issues_start_in_the_first_board_column(lead_client, board, project):
    from apps.workflow.models import IssueType

    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    # Put "In Progress" first.
    config = [board.column_config[1], board.column_config[0], *board.column_config[2:]]
    assert lead_client.patch(f"/api/boards/{board.id}/config/", {"column_config": config}, format="json").status_code == 200
    resp = lead_client.post(
        "/api/issues/", {"project": project.key, "summary": "Starts where?", "issue_type_id": task.id}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["status"]["name"] == "In Progress"
