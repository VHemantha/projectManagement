"""Tasks to Excel (AFIT, 2 Nov 2026): the tasks the task table lists (its filters, search and order,
every page) as a workbook: a Tasks sheet with every column, filters and frozen headings, and a By
stage sheet with the count in each stage."""
import io
from collections import Counter

from django.db.models import DurationField, OuterRef, Subquery, Sum
from django.utils import timezone
from openpyxl import Workbook

from apps.reports.excel import TITLE_FONT, _table
from apps.timesheets.models import TimeEntry

from .models import Issue

DATE = "DD-MM-YY"
HEADERS = ["Key", "Task", "Sub-workspace", "Workspace", "Project", "Status", "Priority", "Accountant", "Team Lead", "Reviewer",
           "Currently responsible", "Start", "Due", "Days overdue", "Budget (h)", "Actual (h)", "Remaining (h)", "Created",
           "Completed", "Archived"]
WIDTHS = {0: 14, 1: 40, 2: 22, 3: 18, 4: 14, 5: 20, 6: 10, 7: 18, 8: 18, 9: 18, 10: 20, 11: 11, 12: 11, 13: 12, 14: 11,
          15: 11, 16: 13, 17: 11, 18: 11, 19: 10}


def _name(user):
    return user.display_name if user else ""


def build(keys: list[str]) -> bytes:
    logged = (TimeEntry.objects.filter(issue=OuterRef("pk"), duration__isnull=False)
              .values("issue").annotate(total=Sum("duration")).values("total"))
    issues = {i.key: i for i in Issue.objects.filter(key__in=keys)
              .select_related("status", "project__client__team", "preparer", "assignee", "reviewer", "current_responsible")
              .annotate(actual=Subquery(logged, output_field=DurationField()))}
    ordered = [issues[k] for k in dict.fromkeys(keys) if k in issues]
    today = timezone.localdate()

    rows = []
    for i in ordered:
        client = i.project.client if i.project_id else None
        actual = round(i.actual.total_seconds() / 3600, 2) if i.actual else 0.0
        done = i.status.category == "done"
        overdue = (today - i.due_date).days if i.due_date and not done and i.due_date < today else None
        rows.append([
            i.key, i.summary, client.name if client else "", client.team.name if client and client.team else "",
            i.project.key if i.project_id else "", i.status.name, i.get_priority_display(), _name(i.preparer), _name(i.assignee),
            _name(i.reviewer), _name(i.current_responsible), i.start_date, i.due_date, overdue, i.budgeted_hours, actual,
            round(i.budgeted_hours - actual, 2) if i.budgeted_hours is not None else None,
            timezone.localtime(i.created_at).date(), timezone.localtime(i.resolved_at).date() if i.resolved_at else None,
            "Yes" if i.is_archived else "",
        ])

    wb = Workbook()
    ws = wb.active
    ws.title = "Tasks"
    first, last = _table(ws, 1, 1, HEADERS, rows, WIDTHS, filters=True)
    ws.freeze_panes = "C2"
    for r in range(first, last + 1):
        for col in (12, 13, 18, 19):
            ws.cell(row=r, column=col).number_format = DATE
        for col in (15, 16, 17):
            ws.cell(row=r, column=col).number_format = "0.00"

    by_stage = wb.create_sheet("By stage")
    by_stage["A1"] = f"Tasks by stage, {today:%d-%m-%y}"
    by_stage["A1"].font = TITLE_FONT
    order = {}
    for i in ordered:
        order.setdefault(i.status.name, (i.status.order, i.status.name))
    counts = Counter(i.status.name for i in ordered)
    stage_rows = [[name, counts[name]] for name in sorted(counts, key=lambda n: order[n])] + [["Total", len(ordered)]]
    _table(by_stage, 3, 1, ["Stage", "Tasks"], stage_rows, {0: 28, 1: 10})

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
