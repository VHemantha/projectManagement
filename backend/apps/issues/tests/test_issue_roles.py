import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue, IssueHistory
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team, TeamMembership
from apps.workflow.models import IssueType, WorkflowStatus
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


@pytest.fixture
def preparer():
    return User.objects.create_user(username="ir_preparer", email="ir_preparer@example.com", password="x")


@pytest.fixture
def reviewer():
    return User.objects.create_user(username="ir_reviewer", email="ir_reviewer@example.com", password="x")


@pytest.fixture
def assignee():
    return User.objects.create_user(username="ir_assignee", email="ir_assignee@example.com", password="x")


@pytest.fixture
def project(preparer):
    project = Project.objects.create(organization=Organization.get_solo(), key="ROL", name="Roles Test", lead=preparer)
    provision_project_defaults(project)
    return project


@pytest.fixture
def task_type():
    task, _ = IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    return task


@pytest.fixture
def api_client(preparer):
    client = APIClient()
    client.force_authenticate(user=preparer)
    return client


@pytest.fixture
def issue(project, task_type, preparer, reviewer, assignee):
    status = WorkflowStatus.objects.get(workflow__project=project, name="To Do")
    return Issue.objects.create(
        project=project, issue_type=task_type, summary="Do the thing", status=status,
        reporter=preparer, preparer=preparer, reviewer=reviewer, assignee=assignee,
        current_responsible=preparer,
    )


def test_creating_an_issue_defaults_preparer_and_current_responsible_to_requester(api_client, project, task_type):
    resp = api_client.post(
        "/api/issues/", {"project": "ROL", "summary": "New task", "issue_type_id": task_type.id}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["preparer"]["username"] == "ir_preparer"
    assert resp.data["current_responsible"]["username"] == "ir_preparer"


def test_patching_reviewer_id_sets_reviewer(api_client, issue):
    other = User.objects.create_user(username="ir_other_reviewer", email="ir_other_reviewer@example.com", password="x")
    resp = api_client.patch(f"/api/issues/{issue.key}/", {"reviewer_id": other.id}, format="json")
    assert resp.status_code == 200
    assert resp.data["reviewer"]["id"] == other.id


def test_role_changes_are_recorded_in_issue_history(api_client, issue, reviewer):
    other = User.objects.create_user(username="ir_other2", email="ir_other2@example.com", password="x")
    api_client.patch(f"/api/issues/{issue.key}/", {"current_responsible_id": other.id}, format="json")
    row = IssueHistory.objects.filter(issue=issue, field_changed="current_responsible").latest("timestamp")
    assert row.new_value == other.display_name


def test_status_transition_with_matching_rule_auto_reassigns_current_responsible(api_client, project, issue, reviewer):
    in_progress = WorkflowStatus.objects.get(workflow__project=project, name="In Progress")
    in_review = WorkflowStatus.objects.get(workflow__project=project, name="In Review")
    issue.status = in_progress
    issue.save(update_fields=["status"])

    resp = api_client.patch(f"/api/issues/{issue.key}/", {"status_id": in_review.id}, format="json")
    assert resp.status_code == 200
    assert resp.data["current_responsible"]["id"] == reviewer.id

    history_row = IssueHistory.objects.filter(issue=issue, field_changed="current_responsible").latest("timestamp")
    assert history_row.new_value == reviewer.display_name


def test_status_transition_without_a_matching_rule_leaves_current_responsible_unchanged(api_client, project, issue):
    todo = WorkflowStatus.objects.get(workflow__project=project, name="To Do")
    done = WorkflowStatus.objects.get(workflow__project=project, name="Done")
    # There's no seeded "To Do -> Done" transition row, so this should be a pure no-op on
    # current_responsible even though the status itself changes freely (unenforced).
    resp = api_client.patch(f"/api/issues/{issue.key}/", {"status_id": done.id}, format="json")
    assert resp.status_code == 200
    assert resp.data["current_responsible"]["id"] == issue.preparer_id


def test_move_action_also_applies_transition_reassignment(api_client, project, issue, reviewer):
    in_progress = WorkflowStatus.objects.get(workflow__project=project, name="In Progress")
    in_review = WorkflowStatus.objects.get(workflow__project=project, name="In Review")
    issue.status = in_progress
    issue.save(update_fields=["status"])

    resp = api_client.post(f"/api/issues/{issue.key}/move/", {"status_id": in_review.id}, format="json")
    assert resp.status_code == 200
    issue.refresh_from_db()
    assert issue.current_responsible_id == reviewer.id


def test_reviewer_and_current_responsible_filters(api_client, project, issue, reviewer):
    resp = api_client.get(f"/api/issues/?reviewer={reviewer.id}")
    assert resp.status_code == 200
    assert any(i["key"] == issue.key for i in resp.data["results"])

    resp2 = api_client.get(f"/api/issues/?current_responsible={issue.preparer_id}")
    assert any(i["key"] == issue.key for i in resp2.data["results"])


def test_creating_an_issue_defaults_reporter_to_the_projects_team_lead(api_client, project, task_type):
    team = Team.objects.create(organization=Organization.get_solo(), name="Reporter Test Team")
    lead = User.objects.create_user(username="ir_team_lead", email="ir_team_lead@example.com", password="x")
    TeamMembership.objects.create(team=team, user=lead, role=TeamMembership.Role.LEAD)
    project.primary_team = team
    project.save(update_fields=["primary_team"])

    resp = api_client.post(
        "/api/issues/", {"project": "ROL", "summary": "Team-led task", "issue_type_id": task_type.id}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["reporter"]["id"] == lead.id


def test_creating_an_issue_without_a_team_lead_falls_back_to_the_requester(api_client, project, task_type):
    resp = api_client.post(
        "/api/issues/", {"project": "ROL", "summary": "No team task", "issue_type_id": task_type.id}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["reporter"]["username"] == "ir_preparer"


def test_creating_an_issue_with_an_explicit_reporter_id_overrides_the_team_lead_default(api_client, project, task_type):
    team = Team.objects.create(organization=Organization.get_solo(), name="Reporter Override Team")
    lead = User.objects.create_user(username="ir_override_lead", email="ir_override_lead@example.com", password="x")
    TeamMembership.objects.create(team=team, user=lead, role=TeamMembership.Role.LEAD)
    project.primary_team = team
    project.save(update_fields=["primary_team"])

    explicit_reporter = User.objects.create_user(
        username="ir_explicit_reporter", email="ir_explicit_reporter@example.com", password="x"
    )
    resp = api_client.post(
        "/api/issues/",
        {
            "project": "ROL",
            "summary": "Explicit reporter task",
            "issue_type_id": task_type.id,
            "reporter_id": explicit_reporter.id,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["reporter"]["id"] == explicit_reporter.id


def test_team_and_client_issue_filters(api_client, project, issue):
    from apps.clients.models import Client

    team = Team.objects.create(organization=Organization.get_solo(), name="Filter Test Team")
    client_obj = Client.objects.create(organization=Organization.get_solo(), name="Filter Test Client")
    project.primary_team = team
    project.client = client_obj
    project.save(update_fields=["primary_team", "client"])

    resp = api_client.get(f"/api/issues/?team={team.id}")
    assert resp.status_code == 200
    assert any(i["key"] == issue.key for i in resp.data["results"])

    resp2 = api_client.get(f"/api/issues/?client={client_obj.id}")
    assert resp2.status_code == 200
    assert any(i["key"] == issue.key for i in resp2.data["results"])
