"""Tasks in bulk from a CSV file (AFIT, 27 Oct 2026): the standard template is downloaded from the
app, filled in (or exported from the current tasks and edited) and uploaded.

A row with no Task Key adds a task; a row with a Task Key updates that task, and an empty cell
leaves its value as it is ("-" clears it). Every row goes through the same serializer as the task
form, so the budget, due-date and permission rules, history and notifications all apply.

The whole file is checked before anything is saved: if any row has a problem, nothing is
imported and every problem is reported with its row number.
"""
import csv
import io
from datetime import date, datetime

from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User
from apps.clients.models import Client
from apps.notifications.inbox import plain_text
from apps.projects.keys import resolve_project
from apps.projects.models import Label
from apps.workflow.models import IssueType

from .models import Issue

COLUMNS = [
    "Task Key", "Project Key", "Sub-workspace", "Job Name", "Group", "Status", "Priority",
    "Team Lead", "Accountant", "Reviewer", "Currently Responsible",
    "Start Date", "Due Date", "Estimated Hours", "Budgeted Hours", "Labels", "Description",
    "Add Standard Sub-tasks",
]
PEOPLE = {"Team Lead": "assignee_id", "Accountant": "preparer_id", "Reviewer": "reviewer_id", "Currently Responsible": "current_responsible_id"}
CLEAR = "-"
MAX_ROWS = 1000
MAX_BYTES = 2 * 1024 * 1024
DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y")
YES, NO = {"yes", "y", "true", "1"}, {"no", "n", "false", "0", ""}


class FileProblem(ValueError):
    """The file as a whole can't be read (not a row's problem)."""


def _norm(name: str) -> str:
    return " ".join(str(name or "").replace("﻿", "").split()).lower()


def read_rows(data: bytes) -> list[dict]:
    if len(data) > MAX_BYTES:
        raise FileProblem("The file is larger than 2 MB. Split it into smaller files.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")  # saved from Excel as plain "CSV"
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
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
        if not any(c.strip() for c in cells):
            continue
        rows.append({"_row": number, **{n: (c or "").strip() for n, c in zip(names, cells) if n}})
        if len(rows) > MAX_ROWS:
            raise FileProblem(f"The file has more than {MAX_ROWS} tasks. Split it into smaller files.")
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


def _payload(row: dict, issue, lookups: Lookups) -> tuple[dict, dict]:
    """The serializer's data for one row, and the row's own problems by column."""
    data, problems = {}, {}
    creating = issue is None
    project = issue.project if issue else None

    def cell(name):
        return row.get(name, "")

    project_key, client_name = cell("Project Key"), cell("Sub-workspace")
    if creating:
        if project_key:
            project = resolve_project(project_key)
            if project is None:
                problems["Project Key"] = f"No project with the key “{project_key}”."
            else:
                data["project"] = project.key
        elif client_name:
            client = Client.objects.filter(name__iexact=client_name).first()
            if client is None:
                problems["Sub-workspace"] = f"No sub-workspace called “{client_name}”."
            else:
                data["client_id"] = client.id
        else:
            problems["Project Key"] = "Give the project key (or the sub-workspace) the task belongs to."
        task_type = IssueType.objects.filter(name__iexact="Task", project__isnull=True).first() or IssueType.objects.filter(name__iexact="Task").first()
        if task_type is None:
            problems["Job Name"] = "The app has no Task type set up."
        else:
            data["issue_type_id"] = task_type.id
        if not cell("Job Name"):
            problems["Job Name"] = "Give the task a job name."
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

    # A status or labels need the project; for a new task in a sub-workspace's own list (no
    # project yet) the stage and labels are left to the defaults.
    if value := cell("Status"):
        if project is not None:
            try:
                data["status_id"] = lookups.status(project, value).id
            except ValueError as e:
                problems["Status"] = str(e)
        elif "Project Key" not in problems:
            problems["Status"] = "Give the project key to set the stage."

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
            problems["Labels"] = "Give the project key to add labels."

    if value := cell("Description"):
        data["description"] = None if value == CLEAR else text_doc(value.replace("\\n", "\n"))

    value = cell("Add Standard Sub-tasks").lower()
    if value in YES:
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

    lookups = Lookups()
    results, checked, seen = [], [], {}
    for row in rows:
        number, key = row["_row"], row.get("Task Key", "")
        issue = None
        result = {"row": number, "key": key, "summary": row.get("Job Name", ""), "action": "update" if key else "create", "errors": {}}
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
        if not result["errors"]:
            data, problems = _payload(row, issue, lookups)
            result["errors"].update(problems)
            if issue is not None and not problems:
                data = _changes(issue, data)
            if not problems:
                serializer = IssueDetailSerializer(instance=issue, data=data, partial=issue is not None, context={"request": request})
                if serializer.is_valid():
                    checked.append((result, serializer))
                    if issue is not None and not data:
                        result["action"] = "unchanged"
                else:
                    result["errors"].update({FIELD_COLUMNS.get(k, k): v for k, v in _messages(serializer.errors).items()})
        results.append(result)

    failed = sum(1 for r in results if r["errors"])
    summary = {
        "rows": len(results), "failed": failed,
        "create": sum(1 for r in results if r["action"] == "create" and not r["errors"]),
        "update": sum(1 for r in results if r["action"] == "update" and not r["errors"]),
        "unchanged": sum(1 for r in results if r["action"] == "unchanged" and not r["errors"]),
        "imported": False, "results": results,
    }
    if commit and not failed:
        with transaction.atomic():
            for result, serializer in checked:
                if result["action"] != "unchanged":
                    result["key"] = serializer.save().key
        summary["imported"] = True
    return summary


def _person(user) -> str:
    return (user.email or user.display_name or user.username) if user else ""


def export_csv(issues) -> str:
    """Tasks in the template's format, to edit and upload again."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(COLUMNS)
    for issue in issues.select_related("project__client", "status", "assignee", "preparer", "reviewer", "current_responsible").prefetch_related("labels"):
        writer.writerow([
            issue.key, issue.project.key, issue.project.client.name if issue.project.client_id else "", issue.summary, issue.group,
            issue.status.name, issue.get_priority_display(),
            _person(issue.assignee), _person(issue.preparer), _person(issue.reviewer), _person(issue.current_responsible),
            issue.start_date.isoformat() if issue.start_date else "", issue.due_date.isoformat() if issue.due_date else "",
            "" if issue.estimated_hours is None else f"{issue.estimated_hours:g}",
            "" if issue.budgeted_hours is None else f"{issue.budgeted_hours:g}",
            "; ".join(label.name for label in issue.labels.all()),
            doc_text(issue.description),
            "",
        ])
    return "﻿" + out.getvalue()  # Excel reads it as UTF-8
