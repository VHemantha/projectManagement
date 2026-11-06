"""Tasks in bulk from a CSV file (AFIT, 27 Oct 2026): the standard template is downloaded from the
app, filled in (or exported from the current tasks and edited) and uploaded.

A row with no Task Key adds a task; a row with a Task Key updates that task, and an empty cell
leaves its value as it is ("-" clears it). Every row goes through the same serializer as the task
form, so the budget, due-date and permission rules, history and notifications all apply.

A new task needs its sub-workspace, job name, group and accountant; the project is optional (without
one the task goes in the sub-workspace's own list). A blank start date is today and a blank due
date 5 days after the start (AFIT, 29 Oct 2026). The template's second and third rows say, for each
column, whether it is required and its type and format; rows starting with "#" are skipped.

The whole file is checked before anything is saved: if any row has a problem, nothing is
imported and every problem is reported with its row number.

Sub-tasks and Excel (AFIT, 6 Nov 2026): the file may be an Excel workbook (.xlsx; its "Tasks" sheet)
as well as CSV. A row whose Row Type is "Sub-task" adds a sub-task to the task row above it, so a
task can have any number of sub-task rows under it; Main Task Key adds one to a task already in the
app instead. A new sub-task needs only its name: the rest comes from its main task unless given.
"""
import csv
import io
import zipfile
from datetime import date, datetime, timedelta

from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.clients.models import Client
from apps.notifications.inbox import plain_text
from apps.projects.keys import resolve_project
from apps.projects.models import Label, Project
from apps.workflow.models import IssueType

from .models import Issue

# Column: (required for a new task, type, format and default). The template's guide rows.
SPEC = {
    "Row Type": ("Optional", "Choice", "Task or Sub-task; empty: Task. Sub-task rows go under their task's row, as many as it needs"),
    "Main Task Key": ("Optional", "Text", "Sub-task rows only: the key of a task already in the app to add it to (e.g. RWCA-12); "
                                          "empty: the task row above"),
    "Task Key": ("Optional", "Text", "Leave empty to add a new task; a task key (e.g. RWCA-12) updates that task"),
    "Sub-workspace": ("Required", "Text", "The sub-workspace's name exactly as it shows in the app"),
    "Job Name": ("Required", "Text", "Up to 500 characters; for a sub-task row, the sub-task's name (the only cell it needs)"),
    "Group": ("Required", "Text", "Up to 100 characters"),
    "Accountant": ("Required", "Person", "Email address, or the name as it shows in the app"),
    "Project Key": ("Optional", "Text", "A project of that sub-workspace (e.g. RWCA); empty: the sub-workspace's own task list"),
    "Status": ("Optional", "Stage", "To Start, In Progress, Waiting for Info, Sent to Client, Internal Adjustments, Client Adjustments, "
                                    "Complete or To be Archived; empty: To Start"),
    "Priority": ("Optional", "Choice", "Highest, High, Medium, Low or Lowest; empty: Medium"),
    "Team Lead": ("Optional", "Person", "Email address, or the name as it shows in the app"),
    "Reviewer": ("Optional", "Person", "Email address, or the name as it shows in the app"),
    "Currently Responsible": ("Optional", "Person", "Email address, or the name; empty: the accountant"),
    "Start Date": ("Optional", "Date", "YYYY-MM-DD (e.g. 2026-11-02) or DD/MM/YYYY (e.g. 02/11/2026); empty: today"),
    "Due Date": ("Optional", "Date", "YYYY-MM-DD or DD/MM/YYYY; empty: 5 days after the start date"),
    "Estimated Hours": ("Optional", "Number", "Hours, a point for decimals (e.g. 6.5); 0 to 10000"),
    "Budgeted Hours": ("Optional", "Number", "Hours, a point for decimals (e.g. 8); set by a team lead or above"),
    "Labels": ("Optional", "List", "The project's existing labels, separated by ; (e.g. GST; Urgent)"),
    "Description": ("Optional", "Text", "Plain text"),
    "Add Standard Sub-tasks": ("Optional", "Yes/No", "yes adds Pre-check, Preparation, Internal Review and Client Review; empty: no"),
}
COLUMNS = list(SPEC)
REQUIRED = [c for c, (need, _, _) in SPEC.items() if need == "Required"]
DUE_AFTER_START_DAYS = 5
PEOPLE = {"Team Lead": "assignee_id", "Accountant": "preparer_id", "Reviewer": "reviewer_id", "Currently Responsible": "current_responsible_id"}
CLEAR = "-"
MAX_ROWS = 3000  # tasks and sub-tasks together
MAX_BYTES = 5 * 1024 * 1024
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")
YES, NO = {"yes", "y", "true", "1"}, {"no", "n", "false", "0", ""}
TASK, SUBTASK = "task", "sub-task"
ROW_TYPES = {"": TASK, "task": TASK, "main task": TASK, "sub-task": SUBTASK, "subtask": SUBTASK, "sub task": SUBTASK}
# What a new sub-task takes from its main task when its own row leaves it empty.
INHERITED = ("preparer", "assignee", "reviewer", "current_responsible", "status", "priority", "group", "start_date", "due_date")


class FileProblem(ValueError):
    """The file as a whole can't be read (not a row's problem)."""


def _norm(name: str) -> str:
    return " ".join(str(name or "").replace("﻿", "").split()).lower()


def _cell_text(value) -> str:
    """An Excel cell as the text a CSV would have: dates as YYYY-MM-DD, whole numbers without .0."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _excel_lines(data: bytes):
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except (zipfile.BadZipFile, KeyError, ValueError, OSError):
        raise FileProblem("The file can't be read as an Excel workbook. Save it as .xlsx (or as CSV) and try again.") from None
    ws = wb["Tasks"] if "Tasks" in wb.sheetnames else wb.worksheets[0]
    return [[_cell_text(v) for v in row] for row in ws.iter_rows(values_only=True)]


def read_rows(data: bytes) -> list[dict]:
    """The rows of a CSV file or an Excel workbook (its Tasks sheet), by column name."""
    if len(data) > MAX_BYTES:
        raise FileProblem("The file is larger than 5 MB. Split it into smaller files.")
    if data[:2] == b"PK":  # .xlsx is a zip
        reader = iter(_excel_lines(data))
    else:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252", errors="replace")  # saved from Excel as plain "CSV"
        reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    # Excel keeps empty trailing columns; they aren't headings.
    while header and not str(header[-1] or "").strip():
        header = header[:-1]
    if not header:
        raise FileProblem("The file is empty. Download the template and fill in one task per row.")
    known = {_norm(c): c for c in COLUMNS}
    names = [known.get(_norm(h)) for h in header]
    unknown = [h for h, n in zip(header, names) if n is None and h.strip()]
    if unknown:
        raise FileProblem(f"Unknown column(s): {', '.join(unknown)}. Use the columns of the template.")
    if "Job Name" not in names and "Task Key" not in names:
        raise FileProblem("The file needs a Job Name column (or a Task Key column to update tasks).")
    rows = []
    for number, cells in enumerate(reader, start=2):
        if not any(c.strip() for c in cells) or (cells and cells[0].strip().startswith("#")):
            continue  # empty, or one of the template's guide rows
        rows.append({"_row": number, **{n: (c or "").strip() for n, c in zip(names, cells) if n}})
        if len(rows) > MAX_ROWS:
            raise FileProblem(f"The file has more than {MAX_ROWS} rows. Split it into smaller files.")
    if not rows:
        raise FileProblem("The file has no tasks in it: fill in one task per row under the headings.")
    return rows


def parse_date(value: str) -> date:
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"“{value}” isn't a date. Write it as 2026-11-30 or 30/11/2026.")


def doc_text(doc) -> str:
    """The editor's document as plain text, a line per paragraph."""
    if not doc:
        return ""
    blocks = doc.get("content") if isinstance(doc, dict) else None
    return "\n".join(plain_text(b, max_length=100_000) for b in blocks) if blocks else plain_text(doc, max_length=100_000)


def text_doc(text: str) -> dict:
    """Plain text as the editor's document, a paragraph per line."""
    return {"type": "doc", "content": [
        {"type": "paragraph", "content": [{"type": "text", "text": line}]} if line.strip() else {"type": "paragraph"}
        for line in text.splitlines()
    ]}


class Lookups:
    """Names in the file to the app's people, projects, statuses and labels, cached for the file."""

    def __init__(self):
        self._users = {}

    def user(self, value: str) -> User:
        key = value.lower()
        if key not in self._users:
            found = list(User.objects.filter(is_active=True).filter(
                Q(email__iexact=value) | Q(username__iexact=value) | Q(display_name__iexact=value))[:2])
            self._users[key] = found
        found = self._users[key]
        if not found:
            raise ValueError(f"No one called “{value}”. Use their email address or their name as it shows in the app.")
        if len(found) > 1:
            raise ValueError(f"More than one person is called “{value}”. Use their email address.")
        return found[0]

    @staticmethod
    def status(project, value: str):
        workflow = getattr(project, "workflow", None)
        status = workflow.statuses.filter(name__iexact=value).first() if workflow else None
        if status is None:
            names = ", ".join(workflow.statuses.order_by("order").values_list("name", flat=True)) if workflow else ""
            raise ValueError(f"“{value}” isn't a stage of {project.key}. Use one of: {names}.")
        return status

    @staticmethod
    def labels(project, value: str) -> list[int]:
        ids = []
        for name in [n.strip() for n in value.split(";") if n.strip()]:
            label = Label.objects.filter(project=project, name__iexact=name).first()
            if label is None:
                raise ValueError(f"{project.key} has no label “{name}”. Add it to the project first, or leave it out.")
            ids.append(label.id)
        return ids


def _subtask_type():
    return IssueType.objects.filter(is_subtask=True, project__isnull=True).first() or IssueType.objects.filter(is_subtask=True).first()


def _payload(row: dict, issue, lookups: Lookups, *, parent_project=None) -> tuple[dict, dict]:
    """The serializer's data for one row, and the row's own problems by column. parent_project:
    a new sub-task's row, in its main task's project."""
    data, problems = {}, {}
    creating = issue is None
    new_subtask = creating and parent_project is not None
    project = issue.project if issue else parent_project

    def cell(name):
        return row.get(name, "")

    project_key, client_name = cell("Project Key"), cell("Sub-workspace")
    if new_subtask:
        if cell("Job Name") in ("", CLEAR):
            problems["Job Name"] = "A sub-task needs its name in Job Name."
        if project_key and resolve_project(project_key) != parent_project:
            problems["Project Key"] = f"A sub-task goes in its main task's project ({parent_project.key}): leave Project Key empty."
        data["project"] = parent_project.key
        subtask_type = _subtask_type()
        if subtask_type is None:
            problems["Row Type"] = "The app has no Sub-task type set up."
        else:
            data["issue_type_id"] = subtask_type.id
    elif creating:
        for column in REQUIRED:
            if cell(column) in ("", CLEAR):
                problems[column] = f"{column} is required for a new task."
        client = None
        if client_name:
            found = list(Client.objects.filter(name__iexact=client_name)[:2])
            if not found:
                problems["Sub-workspace"] = f"No sub-workspace called “{client_name}”."
            elif len(found) > 1:
                problems["Sub-workspace"] = f"More than one sub-workspace is called “{client_name}”. Rename one in the app, or give the project key."
            else:
                client = found[0]
        if project_key:
            project = resolve_project(project_key)
            if project is None:
                problems["Project Key"] = f"No project with the key “{project_key}”."
            elif client is not None and project.client_id != client.id:
                problems["Project Key"] = f"{project.key} isn't in the sub-workspace {client.name}."
            else:
                data["project"] = project.key
        elif client is not None:
            # The sub-workspace's own task list (made with the first task if it doesn't exist yet).
            data["client_id"] = client.id
            project = Project.objects.filter(client=client, is_client_workspace=True).first()
        task_type = IssueType.objects.filter(name__iexact="Task", project__isnull=True).first() or IssueType.objects.filter(name__iexact="Task").first()
        if task_type is None:
            problems["Job Name"] = "The app has no Task type set up."
        else:
            data["issue_type_id"] = task_type.id
    elif project_key and resolve_project(project_key) != issue.project:
        problems["Project Key"] = f"{issue.key} is in {issue.project.key}; a task can't be moved to another project from a file."

    def text(column, field, limit):
        value = cell(column)
        if value == CLEAR:
            if column == "Job Name":
                problems[column] = "A task must have a job name."
            else:
                data[field] = ""
        elif value:
            if len(value) > limit:
                problems[column] = f"Keep it to {limit} characters."
            data[field] = value

    text("Job Name", "summary", 500)
    text("Group", "group", 100)

    # A stage is one of the project's; a sub-workspace's own list this file makes has the standard
    # stages, so there the stage is set by name once the list exists.
    if value := cell("Status"):
        if project is not None:
            try:
                data["status_id"] = lookups.status(project, value).id
            except ValueError as e:
                problems["Status"] = str(e)
        elif creating and "client_id" in data:
            from apps.workflow.services import STATUS_DEFS

            names = {name.lower(): name for name, _, _ in STATUS_DEFS}
            if value.lower() in names:
                data["_stage"] = names[value.lower()]
            else:
                problems["Status"] = f"“{value}” isn't a stage. Use one of: {', '.join(names.values())}."

    if value := cell("Priority"):
        choices = {c.lower(): c for c, _ in Issue.Priority.choices} | {label.lower(): c for c, label in Issue.Priority.choices}
        if value.lower() in choices:
            data["priority"] = choices[value.lower()]
        else:
            problems["Priority"] = f"Use one of: {', '.join(label for _, label in Issue.Priority.choices)}."

    for column, field in PEOPLE.items():
        value = cell(column)
        if value == CLEAR:
            data[field] = None
        elif value:
            try:
                data[field] = lookups.user(value).id
            except ValueError as e:
                problems[column] = str(e)

    for column, field in (("Start Date", "start_date"), ("Due Date", "due_date")):
        value = cell(column)
        if value == CLEAR:
            data[field] = None
        elif value:
            try:
                data[field] = parse_date(value).isoformat()
            except ValueError as e:
                problems[column] = str(e)
    if creating and not new_subtask and "Start Date" not in problems and "Due Date" not in problems:
        from . import stages

        start = date.fromisoformat(data["start_date"]) if data.get("start_date") else stages.today()
        data["start_date"] = start.isoformat()
        if not data.get("due_date"):
            due = start + timedelta(days=DUE_AFTER_START_DAYS)
            if cell("Add Standard Sub-tasks").lower() in YES:
                # Never before the internal review that the standard sub-tasks bring.
                due = max(due, stages.stage_dates(start)[stages.INTERNAL_REVIEW])
            data["due_date"] = due.isoformat()

    for column, field in (("Estimated Hours", "estimated_hours"), ("Budgeted Hours", "budgeted_hours")):
        value = cell(column)
        if value == CLEAR:
            data[field] = None
        elif value:
            try:
                data[field] = float(value.replace(",", "").removesuffix("h"))
            except ValueError:
                problems[column] = f"“{value}” isn't a number of hours."

    if value := cell("Labels"):
        if value == CLEAR:
            data["label_ids"] = []
        elif project is not None:
            try:
                data["label_ids"] = lookups.labels(project, value)
            except ValueError as e:
                problems["Labels"] = str(e)
        elif "Project Key" not in problems:
            problems["Labels"] = "This sub-workspace has no labels yet: leave Labels empty, or give a project key."

    if value := cell("Description"):
        data["description"] = None if value == CLEAR else text_doc(value.replace("\\n", "\n"))

    value = cell("Add Standard Sub-tasks").lower()
    if value in YES and (new_subtask or (issue is not None and issue.parent_id)):
        problems["Add Standard Sub-tasks"] = "Standard sub-tasks are added to a task, not to a sub-task."
    elif value in YES:
        if creating:
            data["default_subtasks"] = True
        else:
            problems["Add Standard Sub-tasks"] = "The standard sub-tasks are added only when a task is created."
    elif value not in NO:
        problems["Add Standard Sub-tasks"] = "Write yes or no."
    return data, problems


def _changes(issue, data: dict) -> dict:
    """Only what differs from the task now, so an exported file uploaded again changes nothing
    (and a rich-text description isn't replaced by its own plain text)."""
    current = {
        "summary": issue.summary, "group": issue.group, "status_id": issue.status_id, "priority": issue.priority,
        "assignee_id": issue.assignee_id, "preparer_id": issue.preparer_id, "reviewer_id": issue.reviewer_id,
        "current_responsible_id": issue.current_responsible_id,
        "start_date": issue.start_date.isoformat() if issue.start_date else None,
        "due_date": issue.due_date.isoformat() if issue.due_date else None,
        "estimated_hours": issue.estimated_hours, "budgeted_hours": issue.budgeted_hours,
    }
    changed = {k: v for k, v in data.items() if k not in current or current[k] != v}
    if "label_ids" in changed and sorted(changed["label_ids"]) == sorted(issue.labels.values_list("id", flat=True)):
        del changed["label_ids"]
    if "description" in changed and doc_text(changed["description"]) == doc_text(issue.description):
        del changed["description"]
    return changed


def _messages(errors) -> dict:
    """A serializer's errors as {field: "message"}."""
    if isinstance(errors, dict):
        return {k: " ".join(str(m) for m in (v if isinstance(v, list) else [v])) for k, v in errors.items()}
    return {"row": " ".join(str(m) for m in errors)}


FIELD_COLUMNS = {
    "project": "Project Key", "client_id": "Sub-workspace", "summary": "Job Name", "group": "Group", "status_id": "Status",
    "priority": "Priority", "assignee_id": "Team Lead", "preparer_id": "Accountant", "reviewer_id": "Reviewer",
    "current_responsible_id": "Currently Responsible", "start_date": "Start Date", "due_date": "Due Date",
    "estimated_hours": "Estimated Hours", "budgeted_hours": "Budgeted Hours", "label_ids": "Labels", "description": "Description",
}


def import_rows(rows: list[dict], request, *, commit: bool) -> dict:
    """Check every row; with commit and no problems, save them all (all or nothing)."""
    from .serializers import IssueDetailSerializer

    with transaction.atomic():
        # Checking may make a sub-workspace's task list (the serializer does, for a task without a
        # project); nothing stays unless the file is imported.
        summary = _check_and_save(rows, request, commit=commit, serializer_class=IssueDetailSerializer)
        if not summary["imported"]:
            transaction.set_rollback(True)
    return summary


class _Main:
    """The last task row read: the main task of the sub-task rows under it."""

    def __init__(self, row: int, issue=None, serializer=None, failed=False):
        self.row, self.issue, self.serializer, self.failed = row, issue, serializer, failed

    @property
    def project(self):
        if self.issue is not None:
            return self.issue.project
        return self.serializer.validated_data.get("project") if self.serializer is not None else None

    @property
    def label(self) -> str:
        return self.issue.key if self.issue is not None else f"the task on row {self.row}"


def _row_type(row: dict, result: dict) -> str | None:
    value = " ".join(row.get("Row Type", "").split()).lower()
    if value in ROW_TYPES:
        return ROW_TYPES[value]
    result["errors"]["Row Type"] = "Write Task or Sub-task (empty: Task)."
    return None


def _main_for(row: dict, issue, main, result: dict):
    """A sub-task row's main task: the task named in Main Task Key, else the task row above."""
    errors = result["errors"]
    if value := row.get("Main Task Key", ""):
        found = Issue.objects.select_related("project").filter(key__iexact=value).first()
        if found is None:
            errors["Main Task Key"] = f"No task with the key “{value}”."
        elif found.parent_id:
            errors["Main Task Key"] = f"{found.key} is itself a sub-task: give its main task's key."
        else:
            return _Main(result["row"], issue=found)
        return None
    if issue is not None:
        return None  # updating a sub-task already in the app: its main task stays as it is
    if main is None:
        errors["Row Type"] = "A sub-task row needs its task's row above it, or the task's key in Main Task Key."
    elif main.failed:
        errors["Row Type"] = f"Fix {main.label} first: this sub-task goes under it."
    else:
        return main
    return None


def _check_and_save(rows: list[dict], request, *, commit: bool, serializer_class) -> dict:
    lookups = Lookups()
    results, checked, seen = [], [], {}
    main = None  # the task row the next sub-task rows belong to
    for row in rows:
        number, key = row["_row"], row.get("Task Key", "")
        issue = None
        result = {"row": number, "key": key, "summary": row.get("Job Name", ""), "action": "update" if key else "create",
                  "type": TASK, "parent": "", "errors": {}}
        kind = _row_type(row, result)
        if kind == SUBTASK:
            result["type"] = SUBTASK
        elif row.get("Main Task Key"):
            result["errors"]["Main Task Key"] = "Only a sub-task row has a main task: set Row Type to Sub-task, or leave this empty."
        if key:
            issue = Issue.objects.select_related("project", "parent").filter(key__iexact=key).first()
            if issue is None:
                result["errors"]["Task Key"] = f"No task with the key “{key}”. Leave the key empty to add a new task."
            elif issue.key in seen:
                result["errors"]["Task Key"] = f"{issue.key} is already on row {seen[issue.key]}."
            else:
                seen[issue.key] = number
                result["key"] = issue.key
                result["summary"] = result["summary"] or issue.summary
                if kind == TASK and issue.parent_id:
                    result["errors"]["Row Type"] = f"{issue.key} is a sub-task of {issue.parent.key}: set Row Type to Sub-task."
                elif kind == SUBTASK and not issue.parent_id:
                    result["errors"]["Row Type"] = f"{issue.key} is a task, not a sub-task: set Row Type to Task."
        parent = None
        if kind == SUBTASK and not result["errors"]:
            parent = _main_for(row, issue, main, result)
            if issue is not None and issue.parent_id:
                result["parent"] = issue.parent.key
                if parent is not None and parent.issue is not None and parent.issue.pk != issue.parent_id:
                    result["errors"]["Main Task Key"] = f"{issue.key} is under {issue.parent.key}; a sub-task can't be moved from a file."
            elif parent is not None:
                result["parent"] = parent.label
        serializer = None
        if not result["errors"]:
            data, problems = _payload(row, issue, lookups, parent_project=parent.project if (parent and issue is None) else None)
            result["errors"].update(problems)
            stage = data.pop("_stage", None)
            if issue is not None and not problems:
                data = _changes(issue, data)
            if not problems:
                serializer = serializer_class(instance=issue, data=data, partial=issue is not None, context={"request": request})
                if serializer.is_valid():
                    checked.append((result, serializer, stage, parent if issue is None else None))
                    if issue is not None and not data:
                        result["action"] = "unchanged"
                else:
                    result["errors"].update({FIELD_COLUMNS.get(k, k): v for k, v in _messages(serializer.errors).items()})
                    serializer = None
        if kind != SUBTASK:
            main = _Main(number, issue=issue, serializer=serializer, failed=bool(result["errors"]))
        results.append(result)

    def count(action, kind=None):
        return sum(1 for r in results if r["action"] == action and not r["errors"] and (kind is None or r["type"] == kind))

    failed = sum(1 for r in results if r["errors"])
    summary = {
        "rows": len(results), "failed": failed,
        "create": count("create"), "update": count("update"), "unchanged": count("unchanged"),
        "create_subtasks": count("create", SUBTASK), "update_subtasks": count("update", SUBTASK),
        "imported": False, "results": results,
    }
    if commit and not failed:
        saved_rows = {}
        for result, serializer, stage, parent in checked:
            if result["action"] == "unchanged":
                continue
            extra = {}
            if parent is not None:  # a new sub-task: under its main task, with what its row leaves empty
                main_task = parent.issue or saved_rows[parent.row]
                given = serializer.validated_data
                extra["parent"] = main_task
                for field in INHERITED:
                    if field in given:
                        continue
                    if field == "current_responsible" and "preparer" in given:
                        continue  # empty: the sub-task's own accountant, as for a task
                    extra[field] = getattr(main_task, field)
            saved = serializer.save(**extra)
            if stage:  # the stage of a task in a sub-workspace's own list, now it exists
                status = saved.project.workflow.statuses.filter(name__iexact=stage).first()
                if status and status.pk != saved.status_id:
                    saved.status = status
                    saved.save(update_fields=["status"])
            saved_rows[result["row"]] = saved
            result["key"] = saved.key
            if parent is not None:
                result["parent"] = saved.parent.key
        summary["imported"] = True
    return summary


def _person(user) -> str:
    return (user.email or user.display_name or user.username) if user else ""


def _with_subtasks(issues) -> list:
    """The tasks, each followed by its sub-tasks (as in the template), each task once."""
    related = ("project__client", "status", "assignee", "preparer", "reviewer", "current_responsible", "parent")
    tasks = list(issues.select_related(*related).prefetch_related("labels"))
    listed = {t.pk for t in tasks}
    subs = {}
    for sub in (Issue.objects.filter(parent_id__in=listed, is_archived=False).select_related(*related).prefetch_related("labels")
                .order_by("rank", "id")):
        subs.setdefault(sub.parent_id, []).append(sub)
    out = []
    for t in tasks:
        if t.parent_id in listed:
            continue  # comes under its main task
        out.append(t)
        out += subs.get(t.pk, [])
    return out


def export_csv(issues) -> str:
    """Tasks in the template's format, each with its sub-tasks under it, to edit and upload again."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for issue in _with_subtasks(issues):
        project = issue.project
        row = {
            "Row Type": "Sub-task" if issue.parent_id else "Task",
            "Main Task Key": issue.parent.key if issue.parent_id else "",
            "Task Key": issue.key,
            "Sub-workspace": project.client.name if project.client_id else "",
            "Job Name": issue.summary, "Group": issue.group, "Accountant": _person(issue.preparer),
            # A task in a sub-workspace's own list has no project of its own.
            "Project Key": "" if project.is_client_workspace else project.key,
            "Status": issue.status.name, "Priority": issue.get_priority_display(),
            "Team Lead": _person(issue.assignee), "Reviewer": _person(issue.reviewer), "Currently Responsible": _person(issue.current_responsible),
            "Start Date": issue.start_date.isoformat() if issue.start_date else "",
            "Due Date": issue.due_date.isoformat() if issue.due_date else "",
            "Estimated Hours": "" if issue.estimated_hours is None else f"{issue.estimated_hours:g}",
            "Budgeted Hours": "" if issue.budgeted_hours is None else f"{issue.budgeted_hours:g}",
            "Labels": "; ".join(label.name for label in issue.labels.all()),
            "Description": doc_text(issue.description), "Add Standard Sub-tasks": "",
        }
        writer.writerow([row[c] for c in COLUMNS])
    return "\ufeff" + out.getvalue()  # Excel reads it as UTF-8


def template_xlsx() -> bytes:
    """The standard template as an Excel workbook (AFIT, 6 Nov 2026): the Tasks sheet to fill in
    (the headings and the two guide rows, with drop-down lists), a worked Example of tasks with
    different numbers of sub-tasks, and How to fill in."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    from apps.workflow.services import STATUS_DEFS

    head_fill, guide_fill, sub_fill = PatternFill("solid", fgColor="800000"), PatternFill("solid", fgColor="F3F3F3"), PatternFill("solid", fgColor="FBF1F1")
    bold_white, grey = Font(bold=True, color="FFFFFF"), Font(italic=True, color="666666", size=9)
    widths = {"Row Type": 11, "Main Task Key": 14, "Task Key": 11, "Sub-workspace": 18, "Job Name": 34, "Group": 14, "Accountant": 24,
              "Description": 30, "Add Standard Sub-tasks": 14}

    def headings(ws):
        ws.append(COLUMNS)
        for i, column in enumerate(COLUMNS, start=1):
            c = ws.cell(row=1, column=i)
            c.font, c.fill, c.alignment = bold_white, head_fill, Alignment(vertical="center", wrap_text=True)
            ws.column_dimensions[get_column_letter(i)].width = widths.get(column, 16)
        ws.freeze_panes = "A2"

    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    headings(ws)
    need = ["Required for a new task" if SPEC[c][0] == "Required" else "Optional" for c in COLUMNS]
    kind = [f"{SPEC[c][1]}: {SPEC[c][2]}" for c in COLUMNS]
    ws.append([f"# {need[0]} (this row and the next are a guide: leave them in or delete them)"] + need[1:])
    ws.append([f"# {kind[0]}"] + kind[1:])
    for r in (2, 3):
        for i in range(1, len(COLUMNS) + 1):
            c = ws.cell(row=r, column=i)
            c.font, c.fill, c.alignment = grey, guide_fill, Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[3].height = 90
    letter = {c: get_column_letter(i) for i, c in enumerate(COLUMNS, start=1)}
    lists = {
        "Row Type": "Task,Sub-task",
        "Status": ",".join(name for name, _, _ in STATUS_DEFS),
        "Priority": ",".join(label for _, label in Issue.Priority.choices),
        "Add Standard Sub-tasks": "Yes,No",
    }
    for column, values in lists.items():
        dv = DataValidation(type="list", formula1=f'"{values}"', allow_blank=True, showErrorMessage=False)
        dv.add(f"{letter[column]}4:{letter[column]}{MAX_ROWS + 3}")
        ws.add_data_validation(dv)

    # A worked example: one task with three sub-tasks, one with one, and a sub-task for a task in the app.
    ex = wb.create_sheet("Example")
    headings(ex)
    example = [
        {"Row Type": "Task", "Sub-workspace": "ABC Ltd", "Job Name": "Annual accounts FY26", "Group": "Companies", "Accountant": "Ann Smith",
         "Priority": "High", "Start Date": "2026-11-09", "Due Date": "2026-11-30", "Budgeted Hours": "12"},
        {"Row Type": "Sub-task", "Job Name": "Bank reconciliation", "Due Date": "2026-11-13", "Estimated Hours": "3"},
        {"Row Type": "Sub-task", "Job Name": "Fixed asset register", "Accountant": "Ben Jones", "Due Date": "2026-11-18"},
        {"Row Type": "Sub-task", "Job Name": "Draft financial statements", "Due Date": "2026-11-25", "Estimated Hours": "5"},
        {"Row Type": "Task", "Sub-workspace": "Xyz Ltd", "Job Name": "GST return Oct", "Group": "GST", "Accountant": "Ben Jones",
         "Due Date": "2026-11-28"},
        {"Row Type": "Sub-task", "Job Name": "Code the October invoices"},
        {"Row Type": "Sub-task", "Main Task Key": "RWCA-12", "Job Name": "Chase the rates notice", "Due Date": "2026-11-12"},
    ]
    for row in example:
        ex.append([row.get(c, "") for c in COLUMNS])
        if row["Row Type"] == "Sub-task":
            for i in range(1, len(COLUMNS) + 1):
                ex.cell(row=ex.max_row, column=i).fill = sub_fill

    how = wb.create_sheet("How to fill in")
    how.column_dimensions["A"].width = 24
    how.column_dimensions["B"].width = 24
    how.column_dimensions["C"].width = 12
    how.column_dimensions["D"].width = 90
    notes = [
        "Fill in the Tasks sheet: one row per task, and one row per sub-task straight under its task.",
        "A task can have any number of sub-task rows (none, one, or many). Set Row Type to Sub-task on them; they belong to the Task row above.",
        "To add a sub-task to a task already in the app, put that task's key in Main Task Key (the row can then go anywhere).",
        "A new sub-task needs only its name in Job Name. Its accountant, team lead, reviewer, stage, priority, group and dates come from its task "
        "unless you fill them in.",
        "A row with a Task Key updates that task or sub-task: an empty cell keeps its value and - clears it.",
        "Check the file in the app first: nothing is saved until every row is right. The Example sheet shows a filled-in file.",
    ]
    how.append(["How to fill in the Tasks sheet"])
    how["A1"].font = Font(bold=True, size=13)
    for n in notes:
        how.append([f"• {n}"])
    how.append([])
    how.append(["Column", "Required", "Type", "Format and default"])
    for i in range(1, 5):
        c = how.cell(row=how.max_row, column=i)
        c.font, c.fill = bold_white, head_fill
    for column in COLUMNS:
        need_, type_, fmt = SPEC[column]
        how.append([column, "Required for a new task" if need_ == "Required" else "Optional", type_, fmt])
        how.cell(row=how.max_row, column=4).alignment = Alignment(wrap_text=True)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def template_csv() -> str:
    """The standard template: the headings, then a row saying which are required for a new task
    and a row with each column's type and format (both start with "#", so an upload skips them)."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(COLUMNS)
    need = ["Required for a new task" if SPEC[c][0] == "Required" else "Optional" for c in COLUMNS]
    kind = [f"{SPEC[c][1]}: {SPEC[c][2]}" for c in COLUMNS]
    writer.writerow([f"# {need[0]} (this row and the next are a guide: leave them in or delete them)"] + need[1:])
    writer.writerow([f"# {kind[0]}"] + kind[1:])
    return "\ufeff" + out.getvalue()
