"""Tasks in bulk from the CSV template (AFIT, 27 Oct 2026): checked first, then all saved or none.
Since 29 Oct 2026 a new task needs its sub-workspace, job name, group and accountant; the project is
optional; a blank start date is today and a blank due date 5 days after the start."""
import csv
import io
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.issues import stages
from apps.issues.csv_import import COLUMNS, REQUIRED, template_csv
from apps.issues.models import Issue, IssueHistory
from apps.orgs.models import Organization
from apps.projects.models import Label, Project
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db
TEMPLATE = Path(__file__).resolve().parents[4] / "frontend" / "public" / "templates" / "tasks-import-template.csv"
TODAY = date(2026, 11, 2)


@pytest.fixture(autouse=True)
def today(monkeypatch):
    monkeypatch.setattr(stages, "today", lambda: TODAY)


@pytest.fixture
def lead():
    return User.objects.create_user(username="lead", email="lead@example.com", password="x", display_name="Lead Person", is_staff=True)


@pytest.fixture
def accountant():
    return User.objects.create_user(username="acc", email="acc@example.com", password="x", display_name="Ann Accountant")


@pytest.fixture
def rwca(lead):
    org = Organization.get_solo()
    client = Client.objects.create(organization=org, name="RWCA")
    project = Project.objects.create(organization=org, key="RWCA", name="RWCA", lead=lead, client=client)
    provision_project_defaults(project)
    IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    Label.objects.create(project=project, name="GST")
    return client


@pytest.fixture
def api(lead, rwca, accountant):
    c = APIClient()
    c.force_authenticate(lead)
    return c


def task(**cells):
    """A new task's row: the required cells filled in, then any others."""
    return {"Sub-workspace": "RWCA", "Job Name": "Smith FY26", "Group": "Rentals", "Accountant": "acc@example.com", **cells}


def csv_file(*rows, header=COLUMNS, guide=False):
    out = io.StringIO()
    if guide:  # as the template comes: the headings and its two guide rows
        out.write(template_csv().lstrip("﻿"))
    else:
        csv.writer(out).writerow(header)
    w = csv.DictWriter(out, fieldnames=header)
    for row in rows:
        w.writerow(row)
    return SimpleUploadedFile("tasks.csv", out.getvalue().encode("utf-8-sig"), content_type="text/csv")


def upload(api, *rows, commit=False, **kw):
    return api.post("/api/issues/import/", {"file": csv_file(*rows, **kw), "commit": "true" if commit else "false"}, format="multipart")


def test_the_template_in_the_app_has_the_columns_and_the_guide():
    assert TEMPLATE.read_bytes().decode("utf-8") == template_csv()
    header, need, kind = list(csv.reader(io.StringIO(template_csv().lstrip("﻿"))))
    assert header == COLUMNS and header[:5] == ["Task Key", "Sub-workspace", "Job Name", "Group", "Accountant"]
    assert [c for c, n in zip(header, need) if n == "Required for a new task"] == REQUIRED == ["Sub-workspace", "Job Name", "Group", "Accountant"]
    assert need[0].startswith("#") and kind[0].startswith("#")
    formats = dict(zip(header, kind))
    assert formats["Start Date"].startswith("Date: YYYY-MM-DD (e.g. 2026-11-02) or DD/MM/YYYY") and "empty: today" in formats["Start Date"]
    assert "empty: 5 days after the start date" in formats["Due Date"]
    assert formats["Estimated Hours"].startswith("Number: Hours, a point for decimals")


def test_the_template_can_be_filled_in_and_uploaded_with_its_guide_rows(api):
    r = upload(api, task(), guide=True, commit=True)
    assert r.data["imported"] and r.data["create"] == 1, r.data
    assert r.data["results"][0]["row"] == 4  # the headings and two guide rows came first


def test_no_project_needed_and_blank_dates_are_today_and_five_days_later(api, accountant, rwca):
    r = upload(api, task(), commit=True)
    assert r.data["imported"], r.data
    t = Issue.objects.get(key=r.data["results"][0]["key"])
    assert t.project.client == rwca and t.project.is_client_workspace  # the sub-workspace's own task list
    assert (t.summary, t.group, t.preparer, t.current_responsible) == ("Smith FY26", "Rentals", accountant, accountant)
    assert (t.start_date, t.due_date) == (TODAY, TODAY + timedelta(days=5))
    assert t.status.name == "To Start"


def test_a_given_start_date_moves_the_default_due_date(api):
    r = upload(api, task(**{"Start Date": "10/11/2026"}), task(**{"Job Name": "Due given", "Due Date": "2026-12-01"}), commit=True)
    a, b = (Issue.objects.get(key=x["key"]) for x in r.data["results"])
    assert (a.start_date, a.due_date) == (date(2026, 11, 10), date(2026, 11, 15))
    assert (b.start_date, b.due_date) == (TODAY, date(2026, 12, 1))


def test_with_the_standard_sub_tasks_the_default_due_date_is_not_before_the_internal_review(api):
    r = upload(api, task(**{"Add Standard Sub-tasks": "yes"}), commit=True)
    t = Issue.objects.get(key=r.data["results"][0]["key"])
    review = t.subtasks.get(summary="Internal Review").due_date
    assert t.due_date == review and t.due_date > TODAY + timedelta(days=5) and t.subtasks.count() == 4


def test_the_required_details_are_checked(api):
    r = upload(api, {"Job Name": "Only a name"}, task(Group="", Accountant="-"), task(**{"Sub-workspace": "Nobody Ltd"}), commit=True)
    assert not r.data["imported"] and Issue.objects.count() == 0
    first, second, third = (x["errors"] for x in r.data["results"])
    assert set(first) == {"Sub-workspace", "Group", "Accountant"}
    assert first["Accountant"] == "Accountant is required for a new task."
    assert set(second) == {"Group", "Accountant"}
    assert "No sub-workspace called “Nobody Ltd”" in third["Sub-workspace"]


def test_a_project_can_still_be_given_but_must_be_in_the_sub_workspace(api, lead):
    org = Organization.get_solo()
    other = Project.objects.create(organization=org, key="OTHER", name="Other", lead=lead,
                                   client=Client.objects.create(organization=org, name="Other Co"))
    r = upload(api, task(**{"Project Key": "rwca", "Status": "In Progress", "Labels": "gst"}), task(**{"Project Key": "OTHER"}), commit=True)
    assert "OTHER isn't in the sub-workspace RWCA" in r.data["results"][1]["errors"]["Project Key"]
    r = upload(api, task(**{"Project Key": "rwca", "Status": "In Progress", "Labels": "gst", "Priority": "High"}), commit=True)
    t = Issue.objects.get(key=r.data["results"][0]["key"])
    assert (t.project.key, t.status.name, t.priority, [label.name for label in t.labels.all()]) == ("RWCA", "In Progress", "high", ["GST"])
    assert other.issues.count() == 0


def test_a_stage_for_a_new_sub_workspace_list_is_set_once_it_exists(api, lead):
    org = Organization.get_solo()
    Client.objects.create(organization=org, name="Fresh Ltd")
    r = upload(api, task(**{"Sub-workspace": "Fresh Ltd", "Status": "Waiting for Info"}), commit=True)
    assert r.data["imported"], r.data
    t = Issue.objects.get(key=r.data["results"][0]["key"])
    assert t.project.client.name == "Fresh Ltd" and t.status.name == "Waiting for Info"
    bad = upload(api, task(**{"Sub-workspace": "Fresh Ltd", "Status": "Finished"}))
    assert "isn't a stage" in bad.data["results"][0]["errors"]["Status"]


def test_checking_a_file_saves_nothing_not_even_a_sub_workspace_list(api):
    Client.objects.create(organization=Organization.get_solo(), name="Fresh Ltd")
    check = upload(api, task(**{"Sub-workspace": "Fresh Ltd"}), task())
    assert check.status_code == 200 and check.data["create"] == 2 and not check.data["imported"], check.data
    assert Issue.objects.count() == 0 and not Project.objects.filter(client__name="Fresh Ltd").exists()


def test_any_problem_stops_the_whole_file_and_says_which_row(api):
    r = upload(api, task(), task(**{"Due Date": "31/31/2026", "Team Lead": "nobody", "Estimated Hours": "six"}), commit=True)
    assert not r.data["imported"] and r.data["failed"] == 1 and Issue.objects.count() == 0
    bad = r.data["results"][1]
    assert bad["row"] == 3 and set(bad["errors"]) == {"Due Date", "Team Lead", "Estimated Hours"}
    assert "isn't a date" in bad["errors"]["Due Date"] and "isn't a number of hours" in bad["errors"]["Estimated Hours"]


def test_the_task_rules_apply_to_each_row(api):
    other = User.objects.create_user(username="staff", email="staff@example.com", password="x")
    c = APIClient()
    c.force_authenticate(other)
    r = upload(c, task(**{"Project Key": "RWCA", "Budgeted Hours": "5"}))
    assert "team lead or above" in r.data["results"][0]["errors"]["Budgeted Hours"]
    early = upload(api, task(**{"Start Date": "2026-11-02", "Due Date": "2026-11-10", "Add Standard Sub-tasks": "yes"}))
    assert "before the internal review" in early.data["results"][0]["errors"]["Due Date"]


def test_a_task_key_updates_that_task_and_empty_cells_keep_their_value(api, lead):
    key = upload(api, task(**{"Estimated Hours": "4", "Team Lead": "lead@example.com"}), commit=True).data["results"][0]["key"]
    r = upload(api, {"Task Key": key.lower(), "Status": "Waiting for Info", "Estimated Hours": "7"}, commit=True)
    assert r.data["imported"] and r.data["update"] == 1, r.data
    t = Issue.objects.get(key=key)
    assert (t.summary, t.group, t.status.name, t.estimated_hours, t.assignee) == ("Smith FY26", "Rentals", "Waiting for Info", 7, lead)
    assert set(IssueHistory.objects.filter(issue=t).values_list("field_changed", flat=True)) == {"status", "estimated_hours"}


def test_unknown_keys_and_repeated_rows_are_refused(api):
    key = upload(api, task(), commit=True).data["results"][0]["key"]
    r = upload(api, {"Task Key": "RWCA-999"}, {"Task Key": key, "Job Name": "B"}, {"Task Key": key, "Job Name": "C"})
    errors = [res["errors"].get("Task Key") for res in r.data["results"]]
    assert "No task with the key “RWCA-999”" in errors[0] and errors[1] is None and "already on row 3" in errors[2]


def test_the_export_uploads_again_without_changing_anything(api):
    upload(api, task(**{"Project Key": "RWCA", "Labels": "GST", "Estimated Hours": "3", "Description": "Two\nlines"}), task(**{"Job Name": "Own list"}),
           commit=True)
    exported = api.get("/api/issues/export/")
    assert exported.status_code == 200 and exported["Content-Type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(exported.content.decode("utf-8-sig"))))
    by_name = {r["Job Name"]: r for r in rows}
    assert by_name["Smith FY26"]["Project Key"] == "RWCA" and by_name["Smith FY26"]["Description"] == "Two\nlines"
    assert by_name["Own list"]["Project Key"] == "" and by_name["Own list"]["Sub-workspace"] == "RWCA"  # no project of its own
    assert by_name["Own list"]["Accountant"] == "acc@example.com"
    again = api.post("/api/issues/import/", {"file": SimpleUploadedFile("t.csv", exported.content), "commit": "true"}, format="multipart")
    assert again.data["unchanged"] == 2 and again.data["failed"] == 0, again.data
    assert not IssueHistory.objects.exists()


def test_files_that_cannot_be_read_are_explained(api):
    assert "Unknown column(s): Colour" in str(upload(api, {"Job Name": "x", "Colour": "red"}, header=["Job Name", "Colour"]).data["detail"])
    assert "no tasks" in str(upload(api).data["detail"])
    assert api.post("/api/issues/import/", {}, format="multipart").status_code == 400
