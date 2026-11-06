"""Sub-tasks and Excel in the task import (AFIT, 6 Nov 2026): sub-task rows go under their task's row, as
many as each task needs; Main Task Key adds one to a task already in the app; a new sub-task takes
what its row leaves empty from its task; the file may be an Excel workbook."""
import io
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import Workbook, load_workbook

from apps.issues.csv_import import COLUMNS, read_rows, template_xlsx
from apps.issues.models import Issue
from apps.workflow.models import IssueType

from .test_csv_import import TODAY, accountant, api, lead, rwca, task, today, upload  # noqa: F401  (shared fixtures)

pytestmark = pytest.mark.django_db
XLSX = Path(__file__).resolve().parents[4] / "frontend" / "public" / "templates" / "tasks-import-template.xlsx"


def sub(name, **cells):
    return {"Row Type": "Sub-task", "Job Name": name, **cells}


def xlsx_file(*rows, sheet="Tasks"):
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    ws.append(COLUMNS)
    for row in rows:
        ws.append([row.get(c, "") for c in COLUMNS])
    out = io.BytesIO()
    wb.save(out)
    return SimpleUploadedFile("tasks.xlsx", out.getvalue(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def upload_xlsx(api, *rows, commit=False):
    return api.post("/api/issues/import/", {"file": xlsx_file(*rows), "commit": "true" if commit else "false"}, format="multipart")


def test_tasks_with_different_numbers_of_sub_tasks(api, accountant, lead):
    rows = [
        task(**{"Job Name": "Annual accounts FY26", "Priority": "High", "Due Date": "2026-11-30", "Team Lead": "lead@example.com"}),
        sub("Bank reconciliation", **{"Due Date": "2026-11-13", "Estimated Hours": "3"}),
        sub("Fixed asset register", Accountant="lead@example.com"),
        sub("Draft financial statements"),
        task(**{"Job Name": "GST return Oct"}),
        sub("Code the October invoices"),
        task(**{"Job Name": "Rates review"}),  # no sub-tasks at all
    ]
    checked = upload(api, *rows)
    assert checked.data["failed"] == 0, checked.data["results"]
    assert (checked.data["create"], checked.data["create_subtasks"]) == (7, 4)
    assert [r["parent"] for r in checked.data["results"]] == ["", "the task on row 2", "the task on row 2", "the task on row 2", "", "the task on row 6", ""]
    assert not Issue.objects.exists()  # checked only

    done = upload(api, *rows, commit=True)
    assert done.data["imported"], done.data
    accounts = Issue.objects.get(summary="Annual accounts FY26")
    subs = list(accounts.subtasks.order_by("rank"))
    assert [s.summary for s in subs] == ["Bank reconciliation", "Fixed asset register", "Draft financial statements"]
    assert all(s.issue_type.is_subtask and s.project == accounts.project for s in subs)
    first, second, third = subs
    # Taken from the task unless the row says otherwise.
    assert (first.preparer, first.assignee, first.priority, first.status, first.group) == (accountant, lead, "high", accounts.status, "Rentals")
    assert (first.due_date.isoformat(), first.estimated_hours, first.start_date) == ("2026-11-13", 3, TODAY)
    assert (second.preparer, second.current_responsible) == (lead, lead)  # its own accountant, and so responsible
    assert third.due_date == accounts.due_date
    assert [s.summary for s in Issue.objects.get(summary="GST return Oct").subtasks.all()] == ["Code the October invoices"]
    assert not Issue.objects.get(summary="Rates review").subtasks.exists()
    keys = [r["parent"] for r in done.data["results"]]
    assert keys[1] == accounts.key


def test_a_sub_task_added_to_a_task_already_in_the_app(api, accountant):
    upload(api, task(), commit=True)
    main = Issue.objects.get(summary="Smith FY26")
    r = upload(api, sub("Chase the rates notice", **{"Main Task Key": main.key.lower()}), commit=True)
    assert r.data["imported"], r.data
    assert [s.summary for s in main.subtasks.all()] == ["Chase the rates notice"]

    # A sub-task in the app is updated by its key; it can't be moved to another task.
    s = main.subtasks.get()
    r = upload(api, sub("Chase the rates notice and the insurance", **{"Task Key": s.key}), commit=True)
    assert r.data["imported"] and r.data["update_subtasks"] == 1, r.data
    s.refresh_from_db()
    assert s.summary == "Chase the rates notice and the insurance" and s.parent == main


def test_sub_task_rows_are_checked(api):
    upload(api, task(), commit=True)
    main = Issue.objects.get(summary="Smith FY26")
    r = upload(api,
               sub("Orphan"),  # no task above it
               task(**{"Sub-workspace": "Nowhere"}), sub("Under a broken task"),
               task(), sub(""), sub("Wrong type", **{"Add Standard Sub-tasks": "yes"}),
               {"Row Type": "Subtusk", "Job Name": "x"},
               sub("Nested", **{"Main Task Key": "NOPE-1"}),
               task(**{"Main Task Key": main.key}),
               {"Row Type": "Sub-task", "Task Key": main.key, "Job Name": "x"})
    errors = {res["row"]: res["errors"] for res in r.data["results"]}
    assert "task's row above it" in errors[2]["Row Type"]
    assert errors[4]["Row Type"] == "Fix the task on row 3 first: this sub-task goes under it."
    assert errors[6]["Job Name"] == "A sub-task needs its name in Job Name."
    assert "not to a sub-task" in errors[7]["Add Standard Sub-tasks"]
    assert errors[8]["Row Type"] == "Write Task or Sub-task (empty: Task)."
    assert "No task with the key" in errors[9]["Main Task Key"]
    assert "Only a sub-task row has a main task" in errors[10]["Main Task Key"]
    assert "is a task, not a sub-task" in errors[11]["Row Type"]
    assert not r.data["imported"] and Issue.objects.count() == 1


def test_the_import_reads_an_excel_workbook(api, accountant):
    r = upload_xlsx(api, task(**{"Due Date": "2026-11-30", "Estimated Hours": 6}), sub("Bank reconciliation"), commit=True)
    assert r.data["imported"] and (r.data["create"], r.data["create_subtasks"]) == (2, 1), r.data
    t = Issue.objects.get(summary="Smith FY26")
    assert t.due_date.isoformat() == "2026-11-30" and t.estimated_hours == 6
    assert t.subtasks.get().summary == "Bank reconciliation"


def test_excel_dates_and_numbers_read_as_written():
    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    ws.append(["Job Name", "Due Date", "Estimated Hours", "Task Key"])
    from datetime import datetime

    ws.append(["A", datetime(2026, 11, 30), 6.0, None])
    ws.append(["# a guide row", None, None, None])
    out = io.BytesIO()
    wb.save(out)
    (row,) = read_rows(out.getvalue())
    assert (row["Due Date"], row["Estimated Hours"], row["Task Key"]) == ("2026-11-30", "6", "")


def test_the_excel_template_has_the_tasks_sheet_an_example_and_a_guide():
    made = load_workbook(io.BytesIO(template_xlsx()))
    shipped = load_workbook(XLSX)  # the file the app serves is up to date
    assert made.sheetnames == shipped.sheetnames == ["Tasks", "Example", "How to fill in"]
    for name in made.sheetnames:
        assert [[c.value for c in r] for r in made[name].iter_rows()] == [[c.value for c in r] for r in shipped[name].iter_rows()]
    tasks = made["Tasks"]
    assert [c.value for c in tasks[1]] == COLUMNS and str(tasks["A2"].value).startswith("#") and str(tasks["A3"].value).startswith("#")
    assert any('"Task,Sub-task"' in dv.formula1 for dv in tasks.data_validations.dataValidation)
    example = [[c.value or "" for c in r] for r in made["Example"].iter_rows(min_row=2)]
    assert [r[0] for r in example] == ["Task", "Sub-task", "Sub-task", "Sub-task", "Task", "Sub-task", "Sub-task"]


def test_the_example_sheet_imports_as_shown(api, accountant, lead, rwca):
    """The worked example, with this test's sub-workspace and people, goes in as it reads."""
    from apps.clients.models import Client
    from apps.orgs.models import Organization

    Client.objects.create(organization=Organization.get_solo(), name="ABC Ltd")
    Client.objects.create(organization=Organization.get_solo(), name="Xyz Ltd")
    upload(api, task(), commit=True)
    existing = Issue.objects.get(summary="Smith FY26")
    wb = load_workbook(io.BytesIO(template_xlsx()))
    ws = wb["Example"]
    swap = {"Ann Smith": "acc@example.com", "Ben Jones": "lead@example.com", "RWCA-12": existing.key}
    for row in ws.iter_rows(min_row=2):
        for c in row:
            if c.value in swap:
                c.value = swap[c.value]
    wb.remove(wb["Tasks"])  # the import reads the Tasks sheet, else the first one
    out = io.BytesIO()
    wb.save(out)
    f = SimpleUploadedFile("example.xlsx", out.getvalue())
    r = api.post("/api/issues/import/", {"file": f, "commit": "true"}, format="multipart")
    assert r.data["imported"] and (r.data["create"], r.data["create_subtasks"]) == (7, 5), r.data
    assert Issue.objects.get(summary="Annual accounts FY26").subtasks.count() == 3
    assert existing.subtasks.get().summary == "Chase the rates notice"
    assert IssueType.objects.filter(is_subtask=True).exists()


def test_downloaded_tasks_list_each_task_with_its_sub_tasks_and_upload_unchanged(api, accountant):
    import csv

    upload(api, task(), sub("Bank reconciliation"), sub("Draft accounts"), task(**{"Job Name": "GST return"}), commit=True)
    r = api.get("/api/issues/export/?no_parent=true")
    rows = list(csv.DictReader(io.StringIO(r.content.decode("utf-8-sig"))))
    main = Issue.objects.get(summary="Smith FY26")
    assert [(x["Row Type"], x["Main Task Key"], x["Job Name"]) for x in rows] == [
        ("Task", "", "Smith FY26"), ("Sub-task", main.key, "Bank reconciliation"), ("Sub-task", main.key, "Draft accounts"),
        ("Task", "", "GST return")]
    again = api.post("/api/issues/import/", {"file": SimpleUploadedFile("t.csv", r.content), "commit": "false"}, format="multipart")
    assert again.data["failed"] == 0 and again.data["unchanged"] == 4, again.data["results"]
