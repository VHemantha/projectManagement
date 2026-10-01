"""Default Kanban columns (Backlog … Done) and the migration that brings old boards in line."""
import importlib

import pytest
from django.apps import apps as django_apps
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import Board, IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db

DEFAULT_COLUMNS = ["Backlog", "To do", "In progress", "In review", "Blocked", "Done"]
migration = importlib.import_module("apps.workflow.migrations.0006_kanban_default_columns")


def run_migration():
    migration.add_default_columns(django_apps, None)


def old_style_project(key, extra=()):
    """A workspace as created before this change: To do / In progress / In review / Done, plus
    any extra (name, category, column index) statuses a team added."""
    project = Project.objects.create(organization=Organization.get_solo(), key=key, name=key)
    workflow = Workflow.objects.create(project=project)
    names = [("To do", "todo"), ("In progress", "in_progress"), ("In review", "in_progress"), ("Done", "done")]
    statuses = {n: WorkflowStatus.objects.create(workflow=workflow, name=n, category=c, order=i) for i, (n, c) in enumerate(names)}
    columns = [{"name": n, "status_ids": [statuses[n].id], "wip_limit": None} for n, _ in names]
    for name, category, index in extra:
        statuses[name] = WorkflowStatus.objects.create(workflow=workflow, name=name, category=category, order=len(statuses))
        if index is not None:
            columns.insert(index, {"name": name, "status_ids": [statuses[name].id], "wip_limit": None, "color": "#123456"})
    Board.objects.create(project=project, name=f"{key} board", board_type="kanban", column_config=columns)
    return project, statuses


def column_names(project):
    return [c["name"] for c in project.boards.first().column_config]


def status_names_in_order(project):
    return list(project.workflow.statuses.order_by("order").values_list("name", flat=True))


def test_new_workspace_gets_the_default_columns_and_new_jobs_start_in_backlog():
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    client = APIClient()
    client.force_authenticate(user=user)
    assert client.post("/api/projects/", {"key": "Fresh", "name": "Fresh", "project_type": "kanban"}, format="json").status_code == 201
    project = Project.objects.get(key="Fresh")
    assert column_names(project) == DEFAULT_COLUMNS
    assert status_names_in_order(project) == DEFAULT_COLUMNS
    assert project.workflow.statuses.get(name="Blocked").category == "in_progress"
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    resp = client.post("/api/issues/", {"project": "Fresh", "summary": "New job", "issue_type_id": task.id}, format="json")
    assert resp.status_code == 201, resp.data
    assert resp.data["status"]["name"] == "Backlog"


def test_migration_adds_backlog_first_and_blocked_before_done_keeping_custom_columns_and_jobs():
    project, statuses = old_style_project("Old", extra=[("QA", "in_progress", 3)])
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    reporter = User.objects.create_user(username="r", email="r@example.com", password="x")
    job = Issue.objects.create(project=project, summary="x", issue_type=task, status=statuses["QA"], reporter=reporter)

    run_migration()

    project.refresh_from_db()
    assert column_names(project) == ["Backlog", "To do", "In progress", "In review", "QA", "Blocked", "Done"]
    assert status_names_in_order(project) == ["Backlog", "To do", "In progress", "In review", "QA", "Blocked", "Done"]
    qa_column = project.boards.first().column_config[4]
    assert qa_column["color"] == "#123456"  # column settings untouched
    job.refresh_from_db()
    assert job.status_id == statuses["QA"].id  # jobs keep their status


def test_migration_reuses_existing_backlog_and_blocked_statuses():
    # A team that already had an unmapped "blocked" status and a Backlog column in the middle.
    project, statuses = old_style_project("Mine", extra=[("blocked", "in_progress", None), ("Backlog", "todo", 2)])
    run_migration()
    project.refresh_from_db()
    assert column_names(project) == ["Backlog", "To do", "In progress", "In review", "Blocked", "Done"]
    blocked_column = project.boards.first().column_config[4]
    assert blocked_column["status_ids"] == [statuses["blocked"].id]
    assert project.workflow.statuses.filter(name__iexact="blocked").count() == 1
    assert project.workflow.statuses.filter(name__iexact="backlog").count() == 1


def test_migration_keeps_a_blocked_column_where_the_team_put_it_and_is_idempotent():
    project, statuses = old_style_project("Kept", extra=[("Blocked", "in_progress", 1)])
    run_migration()
    first = column_names(project)
    assert first == ["Backlog", "To do", "Blocked", "In progress", "In review", "Done"]
    run_migration()
    project.refresh_from_db()
    assert column_names(project) == first
    assert project.workflow.statuses.count() == 6


def test_reordering_columns_reorders_statuses():
    lead = User.objects.create_user(username="lead", email="lead@example.com", password="x", is_staff=True)
    client = APIClient()
    client.force_authenticate(user=lead)
    client.post("/api/projects/", {"key": "Order", "name": "Order", "project_type": "kanban"}, format="json")
    board = Project.objects.get(key="Order").boards.first()
    columns = board.column_config
    columns.insert(1, columns.pop(4))  # Blocked right after Backlog
    resp = client.patch(f"/api/boards/{board.id}/config/", {"column_config": columns}, format="json")
    assert resp.status_code == 200, resp.data
    assert status_names_in_order(board.project) == ["Backlog", "Blocked", "To do", "In progress", "In review", "Done"]
