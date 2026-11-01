"""Employee ratings (AFIT, 31 Oct 2026): the coordination agent keeps each person's KPIs and rates
them, for the CEO only.

Every KPI is worked out by code from the job records over the rating period, as a share from 0 to
100, for the person the agent follows up on each task (its Accountant, else its Team Lead):

    On time      finished tasks whose finish date is on or before the task's due date
    Pre-check    pre-checks done by their target date (start + the pre-check days rule)
    Promises     revised dates given to the agent that the job record shows were met
    Response     the agent's follow-ups answered without being escalated to the team lead
    Budget       finished tasks with a budget whose hours stayed within it (and the tolerance)
    Quality      finished tasks that never went back to Internal Adjustments
    Timesheets   working days (leave and holidays excluded) with the minimum hours recorded

    Rating = sum(weight x KPI score) / sum(weight), over the KPIs with enough data

A KPI with fewer than "least data" items is left out and the others are re-weighted. A rating built
on less than half of the total weight says "Not enough data". Bands: 85 and above Excellent, 70 Good,
55 Needs improvement, below 55 At risk. The weights, the period and the least data are the CEO's
rules (the console's Rules tab); each rating keeps the weights it was worked out with.
"""
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Q, Sum
from django.utils import timezone

from . import calendar, policies

METRICS = [
    ("on_time", "Tasks finished by their due date"),
    ("precheck", "Pre-checks done on time"),
    ("promises", "Revised dates kept"),
    ("response", "Follow-ups answered"),
    ("budget", "Within the hours budget"),
    ("quality", "Right first time"),
    ("timesheet", "Timesheets complete"),
]
BANDS = [(85, "Excellent"), (70, "Good"), (55, "Needs improvement"), (0, "At risk")]
NOT_ENOUGH = "Not enough data"
MIN_COVERAGE = 0.5  # of the total weight
ADJUSTMENTS = "internal adjustments"


def band(score: float | None) -> str:
    if score is None:
        return NOT_ENOUGH
    return next(label for floor, label in BANDS if score >= floor)


def weights() -> dict[str, float]:
    return {key: float(policies.resolve(f"kpi_weight_{key}")) for key, _ in METRICS}


@dataclass
class Metric:
    key: str
    label: str
    good: int
    total: int
    detail: str

    @property
    def score(self) -> float | None:
        return round(self.good / self.total * 100, 1) if self.total else None


def _tasks_of(person):
    """Top-level tasks the agent would follow this person up on."""
    from apps.issues.models import Issue

    return (Issue.objects.filter(parent__isnull=True, issue_type__is_subtask=False)
            .filter(Q(preparer=person) | Q(preparer__isnull=True, assignee=person))
            .exclude(issue_type__name__iexact="epic"))


def _local(dt) -> date:
    from .facts import local_now

    return local_now(dt).date()


def on_time(finished) -> Metric:
    dated = [t for t in finished if t.due_date]
    good = sum(1 for t in dated if _local(t.resolved_at) <= t.due_date)
    return Metric("on_time", dict(METRICS)["on_time"], good, len(dated), f"{good} of {len(dated)} finished tasks by their due date")


def precheck(person, start: date, end: date) -> Metric:
    from apps.precheck.models import AIPrecheck, TaskMilestone

    from .facts import precheck_due

    good = total = 0
    for task in _tasks_of(person).filter(Q(start_date__lte=end) | Q(start_date__isnull=True, created_at__date__lte=end)).select_related("project__client"):
        due = precheck_due(task, person)
        if not start <= due <= min(end, _local(timezone.now())):
            continue
        stamped = TaskMilestone.objects.filter(issue=task, kind="precheck").order_by("on").values_list("on", flat=True).first()
        run = (AIPrecheck.objects.filter(issue=task, kind=AIPrecheck.Kind.PRECHECK, status__in=["complete", "partial"])
               .order_by("created_at").values_list("created_at", flat=True).first())
        done = min([d for d in (stamped, _local(run) if run else None) if d], default=None)
        total += 1
        good += 1 if done and done <= due else 0
    return Metric("precheck", dict(METRICS)["precheck"], good, total, f"{good} of {total} pre-checks done by their target date")


def promises(person, start: date, end: date) -> Metric:
    from .models import Commitment

    rows = Commitment.objects.filter(person=person, eta_date__gte=start, eta_date__lte=end,
                                     status__in=[Commitment.Status.KEPT, Commitment.Status.MISSED])
    kept, total = rows.filter(status=Commitment.Status.KEPT).count(), rows.count()
    return Metric("promises", dict(METRICS)["promises"], kept, total, f"{kept} of {total} revised dates kept")


def response(person, start: date, end: date) -> Metric:
    from .models import AgentCase

    cases = AgentCase.objects.filter(person=person, asked__gt=0, opened_at__date__gte=start, opened_at__date__lte=end)
    total = cases.count()
    good = cases.filter(answered_at__isnull=False, escalated_to__isnull=True).count()
    return Metric("response", dict(METRICS)["response"], good, total, f"{good} of {total} follow-ups answered without escalation")


def budget(finished) -> Metric:
    from apps.timesheets.budget import issue_actual_hours

    tolerance = float(policies.resolve("hours_tolerance_pct"))
    rows = [t for t in finished if t.budgeted_hours]
    good = sum(1 for t in rows if not policies.over_tolerance(float(issue_actual_hours(t.id) or 0), t.budgeted_hours, tolerance))
    return Metric("budget", dict(METRICS)["budget"], good, len(rows), f"{good} of {len(rows)} budgeted tasks within {tolerance:g}% of the budget")


def quality(finished) -> Metric:
    from apps.issues.models import IssueHistory

    reworked = set(IssueHistory.objects.filter(issue__in=finished, field_changed="status", new_value__iexact=ADJUSTMENTS)
                   .values_list("issue_id", flat=True))
    good = sum(1 for t in finished if t.id not in reworked)
    return Metric("quality", dict(METRICS)["quality"], good, len(finished),
                  f"{good} of {len(finished)} finished tasks never went back for internal adjustments")


def timesheet(person, start: date, end: date) -> Metric:
    from apps.timesheets.models import TimeEntry

    minimum = float(policies.resolve("timesheet_min_hours", person=person))
    end = min(end, _local(timezone.now()) - timedelta(days=1))
    logged = {r["work_date"]: r["t"].total_seconds() / 3600 for r in TimeEntry.objects.filter(
        user=person, work_date__gte=start, work_date__lte=end, duration__isnull=False).values("work_date").annotate(t=Sum("duration"))}
    good = total = 0
    day = max(start, _local(person.date_joined))
    while day <= end:
        expected = calendar.expected_hours(person, day)
        if expected > 0:
            total += 1
            good += 1 if logged.get(day, 0) >= min(minimum, expected) else 0
        day += timedelta(days=1)
    return Metric("timesheet", dict(METRICS)["timesheet"], good, total, f"{good} of {total} working days with at least {minimum:g}h recorded")


def reasons(person, start: date, end: date) -> dict[str, int]:
    """The causes the person gave the agent for delays in the period, most often first."""
    from .models import Commitment

    rows = Commitment.objects.filter(person=person, created_at__date__gte=start, created_at__date__lte=end).exclude(cause="none")
    return dict(Counter(c.get_cause_display() for c in rows).most_common())


def rate(person, start: date, end: date) -> dict:
    """The person's KPIs and rating for the period."""
    finished = list(_tasks_of(person).filter(status__category="done", resolved_at__isnull=False,
                                             resolved_at__date__gte=start, resolved_at__date__lte=end))
    minimum = int(policies.resolve("kpi_min_items"))
    w = weights()
    found = [on_time(finished), precheck(person, start, end), promises(person, start, end), response(person, start, end),
             budget(finished), quality(finished), timesheet(person, start, end)]
    rows, total_w, used_w, weighted = [], sum(w.values()), 0.0, 0.0
    for m in found:
        least = 5 if m.key == "timesheet" else minimum
        counted = m.total >= least and w[m.key] > 0
        if counted:
            used_w += w[m.key]
            weighted += w[m.key] * m.score
        rows.append({"key": m.key, "label": m.label, "score": m.score, "n": m.total, "detail": m.detail, "weight": w[m.key], "counted": counted,
                     "note": "" if counted else f"Not counted: fewer than {least} to go on"})
    score = round(weighted / used_w, 1) if used_w else None
    if score is not None and total_w and used_w / total_w < MIN_COVERAGE:
        rating = NOT_ENOUGH
    else:
        rating = band(score)
    return {"person": {"id": person.id, "display_name": person.display_name}, "period": {"from": start, "to": end},
            "score": score, "rating": rating, "metrics": rows, "weights": w, "reasons": reasons(person, start, end),
            "finished_tasks": len(finished)}


def people():
    """Everyone the agent rates: active staff (not the CEO or the agent) who have had tasks."""
    from apps.accounts.models import User

    ids = set(_tasks_of_any().values_list("preparer_id", flat=True)) | set(_tasks_of_any().filter(preparer__isnull=True).values_list("assignee_id", flat=True))
    return User.objects.filter(id__in=[i for i in ids if i], is_active=True, is_agent=False).exclude(role=User.Role.CEO).order_by("display_name")


def _tasks_of_any():
    from apps.issues.models import Issue

    return Issue.objects.filter(parent__isnull=True, issue_type__is_subtask=False).exclude(issue_type__name__iexact="epic")


def period(end: date | None = None, days: int | None = None) -> tuple[date, date]:
    end = end or _local(timezone.now())
    return end - timedelta(days=(days or int(policies.resolve("kpi_period_days"))) - 1), end


def ratings(end: date | None = None, days: int | None = None) -> list[dict]:
    start, end = period(end, days)
    rows = [rate(p, start, end) for p in people()]
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0), r["person"]["display_name"]))
    return rows


def snapshot(end: date | None = None) -> list:
    """Keep today's ratings (one per person per day; a second run the same day replaces it)."""
    from .models import KpiSnapshot

    rows = ratings(end)
    for r in rows:
        KpiSnapshot.objects.update_or_create(
            person_id=r["person"]["id"], period_end=r["period"]["to"],
            defaults={"period_start": r["period"]["from"], "score": r["score"], "rating": r["rating"], "metrics": r["metrics"],
                      "weights": r["weights"], "reasons": r["reasons"]})
    return rows


def previous_scores(before: date) -> dict[int, float | None]:
    """Each person's latest kept rating before this date (for "since last week")."""
    from .models import KpiSnapshot

    out = {}
    for s in KpiSnapshot.objects.filter(period_end__lt=before).order_by("person_id", "-period_end"):
        out.setdefault(s.person_id, s.score)
    return out
