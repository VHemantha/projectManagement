"""Reports for the CEO (AFIT, 21 Nov 2026): the CEO asks the Practice Manager AI in Messages ("give me a report
on the team's hours this month") and gets a PDF with charts and tables. The model only chooses which of
the sections below answer the request, the period and the people, and writes a short summary from the
figures; code works out every figure and draws every chart. CEO only.
"""
import io
from collections import Counter
from datetime import timedelta

from django.utils import timezone

SECTIONS = {
    "hours_by_person": "Hours logged against the 7.5 hours a day expected, by person",
    "low_hours": "Days each person logged under 7.5 hours",
    "non_job_time": "Time on jobs against idle, administration and training",
    "jobs_by_status": "Open jobs by stage",
    "workload": "Open jobs by the person responsible",
    "overdue": "Overdue and escalated follow-ups",
    "budget_vs_actual": "Jobs' hours against their budget",
    "ratings": "Each person's KPI rating",
}

REPORT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["wanted", "title", "sections", "period_days", "person_ids"],
    "properties": {
        "wanted": {"type": "boolean"}, "title": {"type": "string"},
        "sections": {"type": "array", "items": {"type": "string", "enum": list(SECTIONS)}},
        "period_days": {"type": "integer"}, "person_ids": {"type": "array", "items": {"type": "integer"}},
    }}

RULES = """
Reports for the CEO:
- When the CEO asks for a report, a summary or a chart of anything below, set "report": wanted true, a short title, the sections that answer the request (from: """ + "; ".join(
    f"{k} = {v}" for k, v in SECTIONS.items()) + """), the period in days (default 30, at most 365) and person_ids from PEOPLE YOU CAN MESSAGE when the CEO names people ([] for everyone).
- Code makes the PDF with the charts and figures and attaches the link, so in your reply say briefly what the report covers. Otherwise set "report": wanted false, "", [], 30, []."""

MAX_ROWS = 25
MAROON = "#800000"


def _hours(d) -> float:
    return round(d.total_seconds() / 3600, 2) if d else 0.0


def gather(spec: dict) -> dict:
    """The figures for each section asked for: {key: {"title", "headers", "rows", "chart"}}."""
    from django.db.models import Sum

    from apps.accounts.models import User
    from apps.timesheets.efficiency import team_tracker
    from apps.timesheets.models import TimeEntry

    from .facts import open_jobs, responsible
    from .models import AgentCase

    days = max(1, min(int(spec.get("period_days") or 30), 365))
    end = timezone.localdate()
    start = end - timedelta(days=days - 1)
    people = User.objects.filter(is_active=True, is_agent=False).exclude(role=User.Role.CEO).order_by("display_name")
    if spec.get("person_ids"):
        people = people.filter(id__in=spec["person_ids"])
    people = list(people)
    working = max(1, sum(1 for n in range(days) if (start + timedelta(days=n)).weekday() < 5))
    out: dict = {}
    for key in dict.fromkeys(spec.get("sections") or []):
        if key in ("hours_by_person", "low_hours"):
            team = team_tracker(people, end, min(working, 31))
            if key == "hours_by_person":
                rows = [[t["user"]["name"], t["summary"]["logged"], t["summary"]["expected"], f"{t['summary']['efficiency_pct'] or 0}%"] for t in team]
                out[key] = {"headers": ["Person", "Logged (h)", "Expected (h)", "Efficiency"], "rows": rows[:MAX_ROWS],
                            "chart": ("bars", [r[0] for r in rows][:MAX_ROWS], [[r[1] for r in rows][:MAX_ROWS], [r[2] for r in rows][:MAX_ROWS]],
                                      ["Logged", "Expected"])}
            else:
                rows = [[t["user"]["name"], t["summary"]["days_under"], t["summary"]["working_days"]] for t in team if t["summary"]["days_under"]]
                out[key] = {"headers": ["Person", "Days under 7.5h", "Working days"], "rows": rows[:MAX_ROWS],
                            "chart": ("bars", [r[0] for r in rows][:MAX_ROWS], [[r[1] for r in rows][:MAX_ROWS]], ["Days under 7.5h"])}
        elif key == "non_job_time":
            totals = Counter()
            for r in (TimeEntry.objects.filter(user__in=people, work_date__gte=start, work_date__lte=end, duration__isnull=False)
                      .values("issue__activity").annotate(t=Sum("duration"))):
                totals[r["issue__activity"] or "jobs"] += _hours(r["t"])
            labels = [("jobs", "On jobs"), ("idle", "Idle"), ("administration", "Administration"), ("training", "Training")]
            rows = [[label, round(totals[k], 2)] for k, label in labels]
            out[key] = {"headers": ["Time", "Hours"], "rows": rows, "chart": ("pie", [r[0] for r in rows], [[r[1] for r in rows]], [])}
        elif key in ("jobs_by_status", "workload"):
            jobs = list(open_jobs().filter(activity=""))
            if key == "jobs_by_status":
                counts = Counter(j.status.name for j in jobs)
                rows = [[name, n] for name, n in counts.most_common()]
                out[key] = {"headers": ["Stage", "Open jobs"], "rows": rows, "chart": ("pie", [r[0] for r in rows], [[r[1] for r in rows]], [])}
            else:
                counts = Counter((responsible(j).display_name if responsible(j) else "Nobody") for j in jobs)
                rows = [[name, n] for name, n in counts.most_common(MAX_ROWS)]
                out[key] = {"headers": ["Person", "Open jobs"], "rows": rows,
                            "chart": ("bars", [r[0] for r in rows], [[r[1] for r in rows]], ["Open jobs"])}
        elif key == "overdue":
            cases = (AgentCase.objects.exclude(state=AgentCase.State.RESOLVED).select_related("issue", "person")
                     .filter(kind__in=[AgentCase.Kind.PRECHECK_OVERDUE, AgentCase.Kind.PREP_OVERDUE, AgentCase.Kind.PROMISE_MISSED]))
            rows = [[c.issue.key, c.issue.summary[:40], c.person.display_name, c.get_kind_display(), f"{c.due_date:%d %b}", c.get_state_display()]
                    for c in cases[:MAX_ROWS]]
            out[key] = {"headers": ["Job", "Title", "Person", "What", "Due", "State"], "rows": rows, "chart": None}
        elif key == "budget_vs_actual":
            jobs = [j for j in open_jobs().filter(activity="", budgeted_hours__gt=0)]
            spent = dict(TimeEntry.objects.filter(issue__in=jobs, duration__isnull=False).values("issue_id").annotate(t=Sum("duration"))
                         .values_list("issue_id", "t"))
            rows = sorted(([j.key, j.budgeted_hours, _hours(spent.get(j.id)), f"{round(_hours(spent.get(j.id)) / j.budgeted_hours * 100)}%"]
                           for j in jobs), key=lambda r: -(r[2] / r[1] if r[1] else 0))[:MAX_ROWS]
            out[key] = {"headers": ["Job", "Budget (h)", "Logged (h)", "Used"], "rows": rows,
                        "chart": ("bars", [r[0] for r in rows], [[r[1] for r in rows], [r[2] for r in rows]], ["Budget", "Logged"])}
        elif key == "ratings":
            from . import kpi

            rows = [[r["person"]["display_name"], r["score"] if r["score"] is not None else "—", r["rating"]]
                    for r in kpi.ratings(end, days) if not spec.get("person_ids") or r["person"]["id"] in spec["person_ids"]][:MAX_ROWS]
            scored = [r for r in rows if isinstance(r[1], (int, float))]
            out[key] = {"headers": ["Person", "Score", "Rating"], "rows": rows,
                        "chart": ("bars", [r[0] for r in scored], [[r[1] for r in scored]], ["Score"]) if scored else None}
        if key in out:
            out[key]["title"] = SECTIONS[key]
    return {"start": start, "end": end, "days": days, "sections": out}


def facts_text(data: dict) -> str:
    """The figures, for the model's summary."""
    lines = [f"Period: {data['start']:%d %b %Y} to {data['end']:%d %b %Y}."]
    for s in data["sections"].values():
        lines.append(f"{s['title']}: " + "; ".join(", ".join(str(c) for c in r) for r in s["rows"][:15]) if s["rows"] else f"{s['title']}: none.")
    return "\n".join(lines)


def _chart(kind, labels, series, names):
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.legends import Legend
    from reportlab.graphics.charts.piecharts import Pie
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib import colors

    palette = [colors.HexColor(MAROON), colors.HexColor("#0f766e"), colors.HexColor("#2563eb"), colors.HexColor("#d97706"), colors.HexColor("#7c3aed"),
               colors.HexColor("#64748b")]
    d = Drawing(480, 200)
    if kind == "pie":
        values = series[0]
        if not any(values):
            return None
        pie = Pie()
        pie.x, pie.y, pie.width, pie.height = 40, 15, 170, 170
        pie.data, pie.labels = [v or 0.0001 for v in values], [f"{l} ({v:g})" for l, v in zip(labels, values)]
        pie.simpleLabels = 0
        for i in range(len(values)):
            pie.slices[i].fillColor = palette[i % len(palette)]
        d.add(pie)
        return d
    if not labels:
        return None
    bars = VerticalBarChart()
    bars.x, bars.y, bars.width, bars.height = 40, 50, 420, 130
    bars.data = [list(s) for s in series]
    bars.categoryAxis.categoryNames = [str(l)[:14] for l in labels]
    bars.categoryAxis.labels.angle, bars.categoryAxis.labels.boxAnchor, bars.categoryAxis.labels.fontSize = 30, "ne", 7
    bars.valueAxis.valueMin = 0
    bars.valueAxis.labels.fontSize = 7
    for i in range(len(series)):
        bars.bars[i].fillColor = palette[i % len(palette)]
    d.add(bars)
    if len(names) > 1:
        legend = Legend()
        legend.x, legend.y, legend.fontSize = 360, 195, 8
        legend.colorNamePairs = [(palette[i % len(palette)], n) for i, n in enumerate(names)]
        legend.alignment = "right"
        d.add(legend)
    return d


def render(title: str, summary: str, data: dict, request: str) -> bytes:
    """The PDF: a title, the period, the summary, then each section's chart and table."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=title, author="Practice Manager AI")
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor(MAROON)
    story = [Paragraph(escape(title), styles["Title"]),
             Paragraph(f"{data['start']:%d %b %Y} to {data['end']:%d %b %Y} · prepared by the Practice Manager AI on "
                       f"{timezone.localtime():%d %b %Y, %H:%M} for the CEO", styles["Normal"]),
             Spacer(1, 4 * mm), Paragraph(f"<i>You asked:</i> {escape(request[:400])}", styles["Normal"]), Spacer(1, 3 * mm)]
    if summary:
        story += [Paragraph(escape(summary), styles["BodyText"]), Spacer(1, 4 * mm)]
    for s in data["sections"].values():
        story += [Paragraph(escape(s["title"]), styles["Heading2"])]
        if not s["rows"]:
            story += [Paragraph("Nothing to show for this period.", styles["Normal"]), Spacer(1, 3 * mm)]
            continue
        if s.get("chart"):
            drawing = _chart(*s["chart"])
            if drawing is not None:
                story += [drawing]
        table = Table([s["headers"]] + [[escape(str(c)) for c in r] for r in s["rows"]], repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(MAROON)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                                   ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                                   ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")])]))
        story += [table, Spacer(1, 5 * mm)]
    story += [Paragraph("Every figure and chart is worked out from TASKO's records by code; the summary is the AI's, from those figures.",
                        styles["Italic"])]
    doc.build(story)
    return buf.getvalue()


SUMMARY_SYSTEM = """You are the Practice Manager AI at AFIT Connect, writing the summary at the top of a report for the CEO. From the figures given, write 2 to 4 short sentences on what stands out and what the CEO may want to act on. Use only the figures given; never invent a person, a figure or a cause. Be fair: low figures are things to look into, not verdicts. No greeting; New Zealand English."""


def make(ceo, spec: dict, request: str) -> tuple:
    """Build and keep the report. Returns (CeoReport, cost of the summary)."""
    from . import llm
    from .models import CeoReport

    title = " ".join(str(spec.get("title") or "").split())[:200] or "Report for the CEO"
    sections = [s for s in dict.fromkeys(spec.get("sections") or []) if s in SECTIONS] or ["hours_by_person", "jobs_by_status"]
    spec = {"sections": sections, "period_days": max(1, min(int(spec.get("period_days") or 30), 365)),
            "person_ids": [int(i) for i in spec.get("person_ids") or [] if isinstance(i, int)]}
    data = gather(spec)
    cost = 0.0
    try:
        answer, cost = llm.structured(SUMMARY_SYSTEM, [{"role": "user", "content": facts_text(data)}],
                                      {"type": "object", "additionalProperties": False, "required": ["summary"],
                                       "properties": {"summary": {"type": "string"}}}, max_tokens=500)
        summary = str(answer.get("summary", "")).strip()
    except llm.Unavailable:
        summary = ""
    pdf = render(title, summary, data, request)
    report = CeoReport.objects.create(requested_by=ceo, request=request[:2000], title=title, summary=summary[:2000], spec=spec, pdf=pdf)
    return report, cost


def attach(report, message) -> None:
    """The PDF as an attachment of the agent's reply in the CEO's own conversation."""
    from django.core.files.base import ContentFile

    from apps.issues.models import Attachment

    from .services import agent_user

    name = "".join(c if c.isalnum() or c in " -_" else "" for c in report.title).strip()[:80] or "Report"
    filename = f"{name} {report.created_at:%Y-%m-%d}.pdf"
    Attachment.objects.create(message=message, file=ContentFile(bytes(report.pdf), name=filename), filename=filename, uploaded_by=agent_user())
