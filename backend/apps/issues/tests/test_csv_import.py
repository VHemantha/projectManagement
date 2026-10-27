"""Tasks in bulk from the CSV template (AFIT, 27 Oct 2026): checked first, then all saved or none."""
import csv
import io
from datetime import date
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.csv_import import COLUMNS
from apps.issues.models import Issue, IssueHistory
from apps.orgs.models import Organization
from apps.projects.models import Label, Project
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db
TEMPLATE = Path(__file__).resolve().parents[4] / "frontend" / "public" / "templates" / "tasks-import-template.csv"


@pytest.fixture
def lead():
    return User.objects.create_user(username="lead", email="lead@example.com", password="x", display_name="Lead Person", is_staff=True)


@pytest.fixture
def project(lead):
    project = Project.objects.create(organization=Organization.get_solo(), key="RWCA", name="RWCA", lead=lead)
    provision_project_defaults(project)
    IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    Label.objects.create(project=project, name="GST")
    return project


@pytest.fixture
def api(lead, project):
    c = APIClient()
    c.force_authenticate(lead)
    return c


def csv_file(*rows, header=COLUMNS):
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=header)
    w.writeheader()
    for row in rows:
        w.writerow(row)
    return SimpleUploadedFile("tasks.csv", out.getvalue().encode("utf-8-sig"), content_type="text/csv")


def upload(api, *rows, commit=False, **kw):
    return api.post("/api/issues/import/", {"file": csv_file(*rows, **kw), "commit": "true" if commit else "false"}, format="multipart")


def test_the_template_in_the_app_has_the_import_columns():
    assert TEMPLATE.read_text(encoding="utf-8").strip().split(",") == COLUMNS


def test_checking_a_file_saves_nothing_and_importing_adds_the_tasks(api, lead):
    accountant = User.objects.create_user(username="acc", email="acc@example.com", password="x", display_name="Ann Accountant")
    row = {"Project Key": "rwca", "Job Name": "Smith FY26", "Group": "Rentals", "Status": "In Progress", "Priority": "High",
           "Team Lead": "lead@example.com", "Accountant": "Ann Accountant", "Start Date": "02/11/2026", "Due Date": "2026-11-30",
           "Estimated Hours": "6.5", "Budgeted Hours": "8", "Labels": "gst", "Description": "Line one\nLine two",
           "Add Standard Sub-tasks": "yes"}
    check = upload(api, row, {"Project Key": "RWCA", "Job Name": "Jones FY26"})
    assert check.status_code == 200, check.data
    assert check.data["create"] == 2 and check.data["failed"] == 0 and not check.data["imported"]
    assert Issue.objects.count() == 0

    done = upload(api, row, {"Project Key": "RWCA", "Job Name": "Jones FY26"}, commit=True)
    assert done.data["imported"] and [r["key"] for r in done.data["results"]] == ["RWCA-1", "RWCA-6"]
    smith = Issue.objects.get(key="RWCA-1")
    assert (smith.group, smith.status.name, smith.priority, smith.assignee, smith.preparer) == ("Rentals", "In Progress", "high", lead, accountant)
    assert (smith.start_date, smith.due_date, smith.estimated_hours, smith.budgeted_hours) == (date(2026, 11, 2), date(2026, 11, 30), 6.5, 8)
    assert [label.name for label in smith.labels.all()] == ["GST"]
    assert [b["content"][0]["text"] for b in smith.description["content"]] == ["Line one", "Line two"]
    assert smith.subtasks.count() == 4 and smith.issue_type.name == "Task"


def test_any_problem_stops_the_whole_file_and_says_which_row(api):
    r = upload(api, {"Project Key": "RWCA", "Job Name": "Fine"},
               {"Project Key": "NOPE", "Job Name": "x", "Due Date": "31/31/2026", "Team Lead": "nobody", "Status": "Done"},
               {"Project Key": "RWCA", "Job Name": "Stage", "Status": "Finished", "Labels": "VAT"}, commit=True)
    assert not r.data["imported"] and r.data["failed"] == 2 and Issue.objects.count() == 0
    bad, stage = r.data["results"][1], r.data["results"][2]
    assert bad["row"] == 3 and set(bad["errors"]) == {"Project Key", "Due Date", "Team Lead"}
    assert "isn't a date" in bad["errors"]["Due Date"] and "No one called “nobody”" in bad["errors"]["Team Lead"]
    assert "To Start" in stage["errors"]["Status"] and "no label “VAT”" in stage["errors"]["Labels"]


def test_the_task_rules_apply_to_each_row(api, project):
    other = User.objects.create_user(username="staff", email="staff@example.com", password="x")
    c = APIClient()
    c.force_authenticate(other)
    r = upload(c, {"Project Key": "RWCA", "Job Name": "Budget", "Budgeted Hours": "5"})
    assert "team lead or above" in r.data["results"][0]["errors"]["Budgeted Hours"]
    early = upload(api, {"Project Key": "RWCA", "Job Name": "Early", "Start Date": "2026-11-02", "Due Date": "2026-11-10", "Add Standard Sub-tasks": "yes"})
    assert "before the internal review" in early.data["results"][0]["errors"]["Due Date"]


def test_a_task_key_updates_that_task_and_empty_cells_keep_their_value(api, lead):
    created = upload(api, {"Project Key": "RWCA", "Job Name": "Smith FY26", "Group": "Rentals", "Estimated Hours": "4", "Team Lead": "lead@example.com"}, commit=True)
    key = created.data["results"][0]["key"]
    r = upload(api, {"Task Key": key.lower(), "Status": "Waiting for Info", "Estimated Hours": "7", "Group": "-"}, commit=True)
    assert r.data["imported"] and r.data["update"] == 1, r.data
    task = Issue.objects.get(key=key)
    assert (task.summary, task.group, task.status.name, task.estimated_hours, task.assignee) == ("Smith FY26", "", "Waiting for Info", 7, lead)
    assert set(IssueHistory.objects.filter(issue=task).values_list("field_changed", flat=True)) == {"status", "estimated_hours", "group"}


def test_unknown_keys_repeated_rows_and_moves_are_refused(api):
    key, moved = [r["key"] for r in upload(api, {"Project Key": "RWCA", "Job Name": "A"}, {"Project Key": "RWCA", "Job Name": "M"}, commit=True).data["results"]]
    Project.objects.create(organization=Organization.get_solo(), key="OTHER", name="Other")
    r = upload(api, {"Task Key": "RWCA-999"}, {"Task Key": key, "Job Name": "B"}, {"Task Key": key, "Job Name": "C"}, {"Task Key": moved, "Project Key": "OTHER"})
    errors = [res["errors"].get("Task Key") or res["errors"].get("Project Key") for res in r.data["results"]]
    assert "No task with the key “RWCA-999”" in errors[0] and errors[1] is None
    assert "already on row 3" in errors[2] and "can't be moved to another project" in errors[3]


def test_the_export_uploads_again_without_changing_anything(api):
    upload(api, {"Project Key": "RWCA", "Job Name": "Smith FY26", "Labels": "GST", "Estimated Hours": "3", "Due Date": "2026-12-01",
                 "Team Lead": "Lead Person", "Description": "Two\nlines"}, commit=True)
    exported = api.get("/api/issues/export/?project=RWCA")
    assert exported.status_code == 200 and exported["Content-Type"].startswith("text/csv")
    text = exported.content.decode("utf-8-sig")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert rows[0]["Task Key"] == "RWCA-1" and rows[0]["Team Lead"] == "lead@example.com" and rows[0]["Description"] == "Two\nlines"
    again = api.post("/api/issues/import/", {"file": SimpleUploadedFile("t.csv", exported.content), "commit": "true"}, format="multipart")
    assert again.data["unchanged"] == 1 and again.data["failed"] == 0
    assert not IssueHistory.objects.exists()


def test_files_that_cannot_be_read_are_explained(api):
    assert "Unknown column(s): Colour" in str(upload(api, {"Job Name": "x", "Colour": "red"}, header=["Job Name", "Colour"]).data["detail"])
    assert "no tasks" in str(upload(api).data["detail"])
    assert api.post("/api/issues/import/", {}, format="multipart").status_code == 400
