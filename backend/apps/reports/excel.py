"""The CEO's Excel report (AFIT, 31 Oct 2026): the organisation's project status as a workbook, with
Excel's own charts, downloaded when wanted. CEO only.

Sheets: Summary (the key figures and five charts), Projects (each project's status), Open tasks,
Team (workload and the coordinator's ratings), Follow-ups (what the coordinator is chasing and the
reasons given), About (how the figures are worked out). The figures are the dashboard's (ceo.dashboard)
and the ratings' (coordinator.kpi), so the report and the screens always agree.
"""
import io
from collections import defaultdict
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# The same validated colours as the dashboard's charts.
SERIES_1, SERIES_2, CRITICAL = "2A78D6", "EB6834", "D03B3B"
BRAND = "800000"
HEAD_FILL = PatternFill("solid", fgColor="F3EEEE")
HEAD_FONT = Font(bold=True, color="333333")
TITLE_FONT = Font(bold=True, size=16, color=BRAND)
THIN = Border(bottom=Side(style="thin", color="DDDDDD"))
STATUS_FILL = {"Overdue": "FDE2E2", "Due soon": "FEF3C7", "On track": "DCFCE7", "Not started": "F3F4F6", "Done": "DCFCE7"}


def _hours(duration) -> float:
    return round(duration.total_seconds() / 3600, 1) if duration else 0.0


def _table(ws, top: int, left: int, headers: list[str], rows: list[list], widths: dict | None = None, filters: bool = False) -> tuple[int, int]:
    """Write a table with a styled header; returns (first data row, last data row)."""
    for j, h in enumerate(headers):
        c = ws.cell(row=top, column=left + j, value=h)
        c.font, c.fill, c.alignment = HEAD_FONT, HEAD_FILL, Alignment(wrap_text=True, vertical="center")
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            c = ws.cell(row=top + i, column=left + j, value=v)
            c.border = THIN
    for j, w in (widths or {}).items():
        ws.column_dimensions[get_column_letter(left + j)].width = w
    if filters and rows:
        ws.auto_filter.ref = f"{get_column_letter(left)}{top}:{get_column_letter(left + len(headers) - 1)}{top + len(rows)}"
    return top + 1, top + len(rows)


def _colour(series, hex_colour: str, line: bool = False) -> None:
    if line:
        series.graphicalProperties.line.solidFill = hex_colour
        series.graphicalProperties.line.width = 22000  # about 2px
        series.smooth = False
    else:
        series.graphicalProperties.solidFill = hex_colour
        series.graphicalProperties.line.solidFill = hex_colour


def _bar(title, ws, cats, data_cols, first, last, colours, *, horizontal=False, stacked=False, y_title=""):
    chart = BarChart()
    chart.type = "bar" if horizontal else "col"
    chart.title, chart.style, chart.height, chart.width = title, 10, 7.5, 16
    chart.y_axis.title = y_title
    chart.y_axis.majorGridlines = None if horizontal else chart.y_axis.majorGridlines
    if stacked:
        chart.grouping, chart.overlap = "stacked", 100
    for col in data_cols:
        chart.add_data(Reference(ws, min_col=col, min_row=first - 1, max_row=last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=cats, min_row=first, max_row=last))
    for s, colour in zip(chart.series, colours):
        _colour(s, colour)
    if len(data_cols) == 1:
        chart.legend = None
    else:
        chart.legend.position = "b"
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    return chart


def project_rows(today) -> list[dict]:
    """Each project's status: its open, overdue and due-soon tasks, what finished lately, its hours."""
    from apps.issues.models import Issue
    from apps.projects.models import Project
    from apps.timesheets.models import TimeEntry

    week_end, month_ago = today + timedelta(days=7), timezone.now() - timedelta(days=30)
    tasks = (Issue.objects.filter(parent__isnull=True, is_archived=False).exclude(issue_type__name__iexact="epic")
             .values("project_id", "status__category", "due_date", "resolved_at", "budgeted_hours"))
    by_project = defaultdict(lambda: {"total": 0, "open": 0, "done": 0, "overdue": 0, "due_soon": 0, "done_30": 0, "budget": 0.0})
    for t in tasks:
        p = by_project[t["project_id"]]
        p["total"] += 1
        if t["status__category"] == "done":
            p["done"] += 1
            if t["resolved_at"] and t["resolved_at"] >= month_ago:
                p["done_30"] += 1
        else:
            p["open"] += 1
            p["budget"] += t["budgeted_hours"] or 0
            if t["due_date"] and t["due_date"] < today:
                p["overdue"] += 1
            elif t["due_date"] and t["due_date"] <= week_end:
                p["due_soon"] += 1
    hours = {r["project_id"]: _hours(r["t"]) for r in TimeEntry.objects.filter(duration__isnull=False, project_id__in=list(by_project))
             .values("project_id").annotate(t=Sum("duration"))}
    rows = []
    for project in Project.objects.filter(id__in=list(by_project), is_archived=False).select_related("client__team", "primary_team"):
        p = by_project[project.id]
        status = ("Overdue" if p["overdue"] else "Due soon" if p["due_soon"] else "Done" if not p["open"] else "On track")
        team = (project.client.team if project.client_id and project.client.team_id else project.primary_team)
        rows.append({
            "workspace": team.name if team else "", "sub_workspace": project.client.name if project.client_id else "",
            "project": f"{project.client.name} (own task list)" if project.is_client_workspace and project.client_id else project.name,
            "key": project.key, "status": status, "total": p["total"], "open": p["open"], "overdue": p["overdue"], "due_soon": p["due_soon"],
            "done": p["done"], "done_30": p["done_30"], "complete_pct": round(p["done"] / p["total"], 3) if p["total"] else 0,
            "hours": hours.get(project.id, 0.0), "budget_open": round(p["budget"], 1),
        })
    order = {"Overdue": 0, "Due soon": 1, "On track": 2, "Done": 3}
    rows.sort(key=lambda r: (order[r["status"]], -r["overdue"], -r["open"], r["project"]))
    return rows


def open_task_rows(today) -> list[list]:
    from apps.issues.models import Issue
    from apps.timesheets.models import TimeEntry

    tasks = list(Issue.objects.filter(parent__isnull=True, is_archived=False).exclude(status__category="done")
                 .exclude(issue_type__name__iexact="epic")
                 .select_related("project__client", "status", "preparer", "assignee").order_by("due_date", "key"))
    hours = {r["issue_id"]: _hours(r["t"]) for r in TimeEntry.objects.filter(issue__in=tasks, duration__isnull=False)
             .values("issue_id").annotate(t=Sum("duration"))}
    rows = []
    for t in tasks:
        logged = hours.get(t.id, 0.0)
        late = (today - t.due_date).days if t.due_date and t.due_date < today else None
        rows.append([
            t.key, t.summary, t.project.client.name if t.project.client_id else "", t.project.name, t.status.name, t.get_priority_display(),
            t.preparer.display_name if t.preparer else "", t.assignee.display_name if t.assignee else "", t.start_date, t.due_date, late,
            logged, t.budgeted_hours, (round(logged / t.budgeted_hours, 3) if t.budgeted_hours else None),
        ])
    return rows


def follow_up_rows() -> list[list]:
    from apps.coordinator.models import AgentCase

    rows = []
    for c in (AgentCase.objects.exclude(state=AgentCase.State.RESOLVED).select_related("issue", "person", "escalated_to")
              .prefetch_related("commitments").order_by("due_date")):
        last = max(c.commitments.all(), key=lambda x: x.created_at, default=None)
        rows.append([c.issue.key, c.issue.summary, c.person.display_name, c.get_kind_display(), c.due_date, c.revised_due,
                     c.get_state_display(), c.asked, c.escalated_to.display_name if c.escalated_to else "",
                     last.get_cause_display() if last and last.cause != "none" else "", last.blockers if last else ""])
    return rows


def build() -> bytes:
    """The workbook, as bytes."""
    from apps.coordinator import kpi

    from .ceo import dashboard

    now = timezone.now()
    today = timezone.localdate()
    data = dashboard(now)
    wb = Workbook()

    # --- Summary: the key figures and the charts --------------------------------------------------
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "Organisation report"
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"As at {timezone.localtime(now):%A %d %B %Y, %H:%M}. For the CEO."
    ws["A2"].font = Font(italic=True, color="666666")
    t = data["totals"]
    stats = [["Open tasks", t["open"]], ["Overdue", t["overdue"]], ["Due in the next 7 days", t["due_this_week"]],
             ["Completed in the last 30 days", t["completed_30_days"]], ["Hours logged this month", t["hours_this_month"]],
             ["Timesheets waiting for approval", t["timesheets_to_approve"]],
             ["Coordinator follow-ups waiting for a reply", data["follow_ups"]["waiting"]],
             ["Escalated to a team lead", data["follow_ups"]["escalated"]],
             ["Revised dates kept (90 days)", f"{data['commitments_90_days']['kept']} of {data['commitments_90_days']['kept'] + data['commitments_90_days']['missed']}"],
             ["On leave today", ", ".join(data["on_leave_today"]) or "No one"]]
    _table(ws, 4, 1, ["Figure", "Value"], stats, {0: 40, 1: 18})
    ws["B6"].font = Font(bold=True, color=CRITICAL)  # overdue

    # Chart data, side by side under the figures; each chart sits to the right.
    r = 16
    stages = [[s["stage"], s["tasks"]] for s in data["stages"]]
    f1, l1 = _table(ws, r, 1, ["Stage", "Tasks"], stages)
    ws.add_chart(_bar("Tasks by stage", ws, 1, [2], f1, l1, [SERIES_1], horizontal=True), "D4")

    r = l1 + 3
    flow = [[f"{x['week']:%d %b}", x["created"], x["completed"]] for x in data["flow"]]
    f2, l2 = _table(ws, r, 1, ["Week of", "Created", "Completed"], flow)
    line = LineChart()
    line.title, line.style, line.height, line.width = "Tasks created and completed, per week", 10, 7.5, 16
    line.add_data(Reference(ws, min_col=2, max_col=3, min_row=f2 - 1, max_row=l2), titles_from_data=True)
    line.set_categories(Reference(ws, min_col=1, min_row=f2, max_row=l2))
    _colour(line.series[0], SERIES_1, line=True)
    _colour(line.series[1], SERIES_2, line=True)
    line.legend.position = "b"
    line.x_axis.delete = line.y_axis.delete = False
    ws.add_chart(line, "D20")

    r = l2 + 3
    hours = [[f"{x['week']:%d %b}", x["billable"], x["non_billable"]] for x in data["hours"]]
    f3, l3 = _table(ws, r, 1, ["Week of", "Billable", "Non-billable"], hours)
    ws.add_chart(_bar("Hours logged, per week", ws, 1, [2, 3], f3, l3, [SERIES_1, SERIES_2], stacked=True, y_title="Hours"), "D36")

    r = l3 + 3
    spaces = [[w["workspace"], w["on_time"], w["overdue"]] for w in data["workspaces"]]
    if spaces:
        f4, l4 = _table(ws, r, 1, ["Workspace", "On time", "Overdue"], spaces)
        ws.add_chart(_bar("Open tasks by workspace", ws, 1, [2, 3], f4, l4, [SERIES_1, CRITICAL], horizontal=True, stacked=True), "M4")
        r = l4 + 3
    prio = [[p["priority"], p["tasks"]] for p in data["priorities"]]
    f5, l5 = _table(ws, r, 1, ["Priority", "Open tasks"], prio)
    ws.add_chart(_bar("Open tasks by priority", ws, 1, [2], f5, l5, [SERIES_1]), "M20")
    ws.column_dimensions["C"].width = 14

    # --- Projects ---------------------------------------------------------------------------------
    wp = wb.create_sheet("Projects")
    projects = project_rows(today)
    headers = ["Workspace", "Sub-workspace", "Project", "Key", "Status", "Tasks", "Open", "Overdue", "Due in 7 days", "Done",
               "Done (30 days)", "% complete", "Hours logged", "Budgeted hours (open tasks)"]
    first, last = _table(wp, 1, 1, headers, [[p[k] for k in ("workspace", "sub_workspace", "project", "key", "status", "total", "open", "overdue",
                                                          "due_soon", "done", "done_30", "complete_pct", "hours", "budget_open")] for p in projects],
                         {0: 18, 1: 22, 2: 34, 3: 12, 4: 12, 5: 8, 6: 8, 7: 9, 8: 12, 9: 8, 10: 13, 11: 12, 12: 13, 13: 16}, filters=True)
    for row in range(first, last + 1):
        wp.cell(row=row, column=12).number_format = "0%"
        status = wp.cell(row=row, column=5)
        status.fill = PatternFill("solid", fgColor=STATUS_FILL.get(status.value, "FFFFFF"))
    wp.freeze_panes = "A2"

    # --- Open tasks -------------------------------------------------------------------------------
    wt = wb.create_sheet("Open tasks")
    headers = ["Task", "Job name", "Sub-workspace", "Project", "Stage", "Priority", "Accountant", "Team Lead", "Start", "Due",
               "Days overdue", "Hours logged", "Budgeted hours", "% of budget used"]
    first, last = _table(wt, 1, 1, headers, open_task_rows(today),
                         {0: 14, 1: 34, 2: 20, 3: 22, 4: 18, 5: 10, 6: 18, 7: 18, 8: 11, 9: 11, 10: 12, 11: 12, 12: 14, 13: 15}, filters=True)
    for row in range(first, last + 1):
        for col in (9, 10):
            wt.cell(row=row, column=col).number_format = "dd/mm/yyyy"
        wt.cell(row=row, column=14).number_format = "0%"
        late = wt.cell(row=row, column=11)
        if late.value:
            late.font = Font(bold=True, color=CRITICAL)
    wt.freeze_panes = "C2"

    # --- Team: workload and ratings ---------------------------------------------------------------
    wm = wb.create_sheet("Team")
    ratings = kpi.ratings()
    metric_labels = [label for _, label in kpi.METRICS]
    rows = [[r["person"]["display_name"], r["score"], r["rating"]] + [m["score"] if m["counted"] else None for m in r["metrics"]]
            + ["; ".join(f"{c}: {n}" for c, n in r["reasons"].items())] for r in ratings]
    wm["A1"] = f"Ratings, {ratings[0]['period']['from']:%d %b} to {ratings[0]['period']['to']:%d %b %Y}" if ratings else "Ratings"
    wm["A1"].font = Font(bold=True, size=13, color=BRAND)
    first, last = _table(wm, 3, 1, ["Person", "Rating score", "Rating"] + metric_labels + ["Reasons given for delays"], rows,
                         {0: 20, 1: 12, 2: 18, **{3 + i: 16 for i in range(len(metric_labels))}, 3 + len(metric_labels): 40})
    if rows:
        wm.add_chart(_bar("Rating by person", wm, 1, [2], first, last, [SERIES_1], horizontal=True), f"A{last + 3}")
    top = last + 20 if rows else 6
    wm.cell(row=top, column=1, value="Open tasks by Team Lead").font = Font(bold=True, size=13, color=BRAND)
    load = [[w["person"], w["on_time"], w["overdue"], w["open"]] for w in data["workload"]]
    if load:
        f6, l6 = _table(wm, top + 1, 1, ["Team Lead", "On time", "Overdue", "Open"], load)
        wm.add_chart(_bar("Open tasks by Team Lead", wm, 1, [2, 3], f6, l6, [SERIES_1, CRITICAL], horizontal=True, stacked=True), f"F{top + 1}")

    # --- Follow-ups -------------------------------------------------------------------------------
    wf = wb.create_sheet("Follow-ups")
    first, last = _table(wf, 1, 1, ["Task", "Job name", "Person", "Matter", "Due", "Revised date", "State", "Messages", "Escalated to",
                                    "Reason given", "Details"], follow_up_rows(),
                         {0: 14, 1: 32, 2: 18, 3: 24, 4: 11, 5: 12, 6: 22, 7: 10, 8: 16, 9: 26, 10: 40}, filters=True)
    for row in range(first, last + 1):
        for col in (5, 6):
            wf.cell(row=row, column=col).number_format = "dd/mm/yyyy"
    wf.freeze_panes = "A2"

    # --- About ------------------------------------------------------------------------------------
    wa = wb.create_sheet("About")
    notes = [
        ("Tasks", "Top-level tasks (not sub-tasks or epics) that are not archived."),
        ("Overdue", "Open tasks whose due date has passed."),
        ("Project status", "Overdue: a task is overdue. Due soon: a task is due within 7 days. On track: open, nothing due soon. Done: no open tasks."),
        ("Hours", "Hours logged in timesheets against the task or project."),
        ("Ratings", "The coordinator's weighted KPI rating (see the coordinator console's Ratings tab for the formula and weights). "
                    "A blank KPI had too little data to count."),
        ("Follow-ups", "What the coordinator is following up now, with the latest reason the person gave."),
    ]
    _table(wa, 1, 1, ["Item", "How it is worked out"], [list(n) for n in notes], {0: 18, 1: 110})
    for row in range(2, len(notes) + 2):
        wa.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical="top")

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
