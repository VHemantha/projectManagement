"""Keys kept as typed + renames, jobs without projects, archiving, actual time from timesheets,
saved table layouts and customisable report columns."""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType

pytestmark = pytest.mark.django_db


@pytest.fixture
def user():
    return User.objects.create_user(username="jobber", email="jobber@example.com", password="x")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.fixture
def task_type():
    return IssueType.objects.get_or_create(name="Task", project=None)[0]


def _project(api, key, name="Pochin Group", **extra):
    resp = api.post("/api/projects/", {"key": key, "name": name, "project_type": "kanban", **extra}, format="json")
    assert resp.status_code == 201, resp.data
    return resp.data


def _job(api, project, task_type, summary="Job", **extra):
    resp = api.post(
        "/api/issues/", {"project": project, "summary": summary, "issue_type_id": task_type.id, **extra}, format="json"
    )
    assert resp.status_code == 201, resp.data
    return resp.data


# --- 1. Keys ---------------------------------------------------------------------------------


def test_key_keeps_its_case_and_jobs_use_it(api, task_type):
    project = _project(api, "Pochin")
    assert project["key"] == "Pochin"
    assert _job(api, "Pochin", task_type)["key"] == "Pochin-1"


def test_keys_are_unique_ignoring_case(api):
    _project(api, "Pochin")
    resp = api.post("/api/projects/", {"key": "POCHIN", "name": "Other", "project_type": "kanban"}, format="json")
    assert resp.status_code == 400


def test_lookups_ignore_case(api, task_type):
    _project(api, "Pochin")
    _job(api, "Pochin", task_type)
    assert api.get("/api/projects/pochin/").data["key"] == "Pochin"
    assert api.get("/api/issues/POCHIN-1/").data["key"] == "Pochin-1"


def test_renaming_a_key_rekeys_jobs_and_old_keys_still_resolve(api, task_type):
    _project(api, "PG")
    _job(api, "PG", task_type, "First")
    _job(api, "PG", task_type, "Second")

    resp = api.patch("/api/projects/PG/", {"key": "Pochin"}, format="json")
    assert resp.status_code == 200, resp.data
    assert resp.data["key"] == "Pochin"
    assert sorted(Issue.objects.values_list("key", flat=True)) == ["Pochin-1", "Pochin-2"]

    # Old links still work and report the new key.
    assert api.get("/api/projects/PG/").data["key"] == "Pochin"
    old = api.get("/api/issues/PG-2/")
    assert old.status_code == 200 and old.data["key"] == "Pochin-2"
    assert api.get("/api/issues/PG-2/comments/").status_code == 200
    # New jobs continue the numbering under the new key.
    assert _job(api, "Pochin", task_type)["key"] == "Pochin-3"
    # The old key stays reserved so its links can't start pointing somewhere else.
    clash = api.post("/api/projects/", {"key": "pg", "name": "Clash", "project_type": "kanban"}, format="json")
    assert clash.status_code == 400


def test_renaming_back_to_an_old_key_frees_the_alias(api, task_type):
    _project(api, "PG")
    _job(api, "PG", task_type)
    api.patch("/api/projects/PG/", {"key": "Pochin"}, format="json")
    resp = api.patch("/api/projects/Pochin/", {"key": "PG"}, format="json")
    assert resp.status_code == 200
    assert Issue.objects.get().key == "PG-1"
    assert api.get("/api/issues/Pochin-1/").data["key"] == "PG-1"


# --- 8. Jobs for clients without a project -----------------------------------------------------


def test_job_for_a_client_without_projects_goes_to_its_job_list(api, task_type):
    acme = Client.objects.create(organization=Organization.get_solo(), name="Acme Corp")
    first = api.post("/api/issues/", {"client_id": acme.id, "summary": "Payroll", "issue_type_id": task_type.id}, format="json")
    assert first.status_code == 201, first.data
    workspace = Project.objects.get(client=acme, is_client_workspace=True)
    assert workspace.key == "Acme" and workspace.name == "Acme Corp"
    assert first.data["key"] == "Acme-1"
    assert first.data["project_name"] == "Acme Corp"
    second = api.post("/api/issues/", {"client_id": acme.id, "summary": "VAT", "issue_type_id": task_type.id}, format="json")
    assert second.data["key"] == "Acme-2"
    assert Project.objects.filter(client=acme).count() == 1
    client_data = api.get("/api/clients/").data
    acme_row = next(c for c in client_data if c["id"] == acme.id)
    assert acme_row["workspace_project_key"] == "Acme"
    assert acme_row["project_count"] == 0  # the automatic job list isn't counted as a project


def test_a_client_that_requires_projects_rejects_project_less_jobs(api, task_type):
    rwca = Client.objects.create(organization=Organization.get_solo(), name="RWCA", requires_projects=True)
    resp = api.post("/api/issues/", {"client_id": rwca.id, "summary": "x", "issue_type_id": task_type.id}, format="json")
    assert resp.status_code == 400
    assert "must belong to one of its projects" in str(resp.data)
    assert not Project.objects.filter(client=rwca).exists()


def test_a_job_needs_a_project_or_a_client(api, task_type):
    resp = api.post("/api/issues/", {"summary": "x", "issue_type_id": task_type.id}, format="json")
    assert resp.status_code == 400


def test_requires_projects_is_editable_on_the_client(api):
    acme = Client.objects.create(organization=Organization.get_solo(), name="Acme")
    resp = api.patch(f"/api/clients/{acme.id}/", {"requires_projects": True}, format="json")
    assert resp.status_code == 200 and resp.data["requires_projects"] is True


# --- 6. Archive ------------------------------------------------------------------------------


def test_archived_jobs_leave_boards_and_lists(api, task_type):
    _project(api, "Arc")
    keep = _job(api, "Arc", task_type, "Keep")
    old = _job(api, "Arc", task_type, "Old")
    IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    sub = api.post(f"/api/issues/{old['key']}/subtasks/", {"summary": "Old sub"}, format="json")
    assert sub.status_code == 201, sub.data

    resp = api.patch(f"/api/issues/{old['key']}/", {"is_archived": True}, format="json")
    assert resp.status_code == 200
    assert resp.data["is_archived"] is True and resp.data["archived_at"]
    assert Issue.objects.get(key=sub.data["key"]).is_archived  # sub-tasks go with it

    listed = {r["key"] for r in api.get("/api/issues/", {"project": "Arc"}).data["results"]}
    assert listed == {keep["key"]}
    everything = {r["key"] for r in api.get("/api/issues/", {"project": "Arc", "include_archived": "true"}).data["results"]}
    assert old["key"] in everything
    only = {r["key"] for r in api.get("/api/issues/", {"project": "Arc", "archived": "true"}).data["results"]}
    assert only == {old["key"], sub.data["key"]}
    # Still reachable directly.
    assert api.get(f"/api/issues/{old['key']}/").status_code == 200

    api.patch(f"/api/issues/{old['key']}/", {"is_archived": False}, format="json")
    restored = Issue.objects.get(key=old["key"])
    assert not restored.is_archived and restored.archived_at is None


def test_bulk_archive_and_restore(api, task_type):
    _project(api, "Blk")
    keys = [_job(api, "Blk", task_type, f"J{i}")["key"] for i in range(3)]
    resp = api.post("/api/issues/archive/", {"keys": keys[:2], "archived": True}, format="json")
    assert resp.status_code == 200 and resp.data["updated"] == 2
    assert [r["key"] for r in api.get("/api/issues/", {"project": "Blk"}).data["results"]] == [keys[2]]
    api.post("/api/issues/archive/", {"keys": keys[:2], "archived": False}, format="json")
    assert len(api.get("/api/issues/", {"project": "Blk"}).data["results"]) == 3
    assert api.post("/api/issues/archive/", {"keys": "nope"}, format="json").status_code == 400


# --- 5. Actual time --------------------------------------------------------------------------


def test_actual_hours_come_from_timesheets(api, user, task_type):
    _project(api, "Act")
    job = _job(api, "Act", task_type, "Timed", budgeted_hours=8)
    issue = Issue.objects.get(key=job["key"])
    other = User.objects.create_user(username="other", email="other@example.com", password="x")
    for who, hours in [(user, 2), (user, 1.5), (other, 3)]:
        TimeEntry.objects.create(user=who, issue=issue, project=issue.project, work_date=date.today(), duration=timedelta(hours=hours))
    TimeEntry.objects.create(user=user, issue=issue, project=issue.project, work_date=date.today(), duration=None)  # running timer

    row = next(r for r in api.get("/api/issues/", {"project": "Act"}).data["results"] if r["key"] == job["key"])
    assert row["actual_hours"] == 6.5
    assert row["budgeted_hours"] == 8
    detail = api.get(f"/api/issues/{job['key']}/").data
    assert detail["actual_hours"] == 6.5
    assert [(r["display_name"], r["hours"]) for r in detail["time_by_user"]] == [
        (user.display_name, 3.5), (other.display_name, 3.0)
    ]


def test_actual_hours_are_not_double_counted_by_label_filters(api, task_type):
    from apps.projects.models import Label

    _project(api, "Lbl")
    job = _job(api, "Lbl", task_type)
    issue = Issue.objects.get(key=job["key"])
    labels = [Label.objects.create(project=issue.project, name=n) for n in ("a", "b")]
    issue.labels.set(labels)
    TimeEntry.objects.create(user=issue.reporter, issue=issue, work_date=date.today(), duration=timedelta(hours=2))
    rows = api.get("/api/issues/", {"project": "Lbl", "label": labels[0].id}).data["results"]
    assert rows[0]["actual_hours"] == 2.0


# --- 2/3/4. Saved table layouts + report columns --------------------------------------------


def test_table_layouts_are_saved_per_user(api, user):
    state = {"columnOrder": ["key", "summary"], "columnVisibility": {"assignee": False}, "sorting": [{"id": "key", "desc": True}]}
    assert api.put("/api/auth/me/table-preferences/project-jobs/", {"state": state}, format="json").status_code == 200
    assert api.get("/api/auth/me/table-preferences/").data == {"project-jobs": state}

    someone_else = APIClient()
    someone_else.force_authenticate(User.objects.create_user(username="x2", email="x2@example.com", password="x"))
    assert someone_else.get("/api/auth/me/table-preferences/").data == {}

    assert api.delete("/api/auth/me/table-preferences/project-jobs/").status_code == 204
    assert api.get("/api/auth/me/table-preferences/").data == {}
    assert api.put("/api/auth/me/table-preferences/x/", {"state": [1]}, format="json").status_code == 400


def test_budget_report_offers_extra_columns(api, task_type):
    acme = Client.objects.create(organization=Organization.get_solo(), name="Acme")
    _project(api, "Rep", client_id=acme.id)
    _job(api, "Rep", task_type, budgeted_hours=3)
    row = next(r for r in api.get("/api/reports/budget-vs-actual/").data["projects"] if r["project_key"] == "Rep")
    assert row["client"] == "Acme" and row["job_count"] == 1 and row["open_jobs"] == 1
    detail = api.get("/api/reports/budget-vs-actual/", {"project": "Rep"}).data["issues"][0]
    assert {"status", "issue_type", "assignee", "due_date", "is_archived"} <= detail.keys()


def test_suggested_keys_use_the_full_first_word():
    from apps.projects.keys import suggest_key

    assert suggest_key("Pochin Group") == "Pochin"
    assert suggest_key("2026 Accounts") == "Accounts"
    assert suggest_key("A Team") == "ATeam"
    assert suggest_key("!!!") == "Project"
    Project.objects.create(organization=Organization.get_solo(), key="Pochin", name="x")
    assert suggest_key("Pochin Group") == "Pochin2"  # taken -> numbered


def test_job_value_is_listed_and_editable(api, task_type):
    _project(api, "Val", job_value_currency="GBP")
    job = _job(api, "Val", task_type)
    resp = api.patch(f"/api/issues/{job['key']}/", {"allocated_value": "1250.50"}, format="json")
    assert resp.status_code == 200
    row = api.get("/api/issues/", {"project": "Val"}).data["results"][0]
    assert row["allocated_value"] == "1250.50"
    assert row["value_currency"] == "GBP"
    api.patch(f"/api/issues/{job['key']}/", {"allocated_value": None}, format="json")
    assert api.get("/api/issues/", {"project": "Val"}).data["results"][0]["allocated_value"] is None


def test_new_boards_show_job_value_on_cards(api):
    project = _project(api, "Card")
    board = api.get(f"/api/projects/{project['key']}/board/").data
    assert "job_value" in board["card_fields"]
