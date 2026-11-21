"""The efficiency tracker (AFIT, 21 Nov 2026): for each working day, the hours a person logged against the
7.5 hours the firm expects (less a holiday, approved leave or a part-time day), split into hours on jobs
and the time logged to idle, administration and training. Also each person's open jobs, hours against
the budget. Worked out by code from the timesheets; used on the landing page and by the Practice
Manager AI's daily check of who logged under 7.5 hours.
"""
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Sum

TARGET_HOURS = 7.5
MAX_DAYS = 31


def _hours(d) -> float:
    return round(d.total_seconds() / 3600, 2) if d else 0.0


def expected_for(user, day: date) -> float:
    """What the person should log that day: 7.5 hours on a working day, less leave, a holiday or a part day."""
    from apps.coordinator.calendar import expected_hours

    scheduled = expected_hours(user, day)
    return round(min(TARGET_HOURS, scheduled), 2) if scheduled > 0 else 0.0


def working_days(end: date, days: int) -> list[date]:
    """The last `days` weekdays up to and including `end`, oldest first."""
    out, d = [], end
    while len(out) < days:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def logged_by_day(users, days: list[date]) -> dict:
    """{(user_id, day): {"jobs": h, "idle": h, "administration": h, "training": h}}."""
    from .models import TimeEntry

    rows = (TimeEntry.objects.filter(user__in=users, work_date__in=days, duration__isnull=False)
            .values("user_id", "work_date", "issue__activity").annotate(total=Sum("duration")))
    out: dict = defaultdict(lambda: {"jobs": 0.0, "idle": 0.0, "administration": 0.0, "training": 0.0})
    for r in rows:
        kind = r["issue__activity"] or "jobs"
        out[(r["user_id"], r["work_date"])][kind if kind in ("idle", "administration", "training") else "jobs"] += _hours(r["total"])
    return out


def day_rows(user, days: list[date], logged: dict | None = None) -> list[dict]:
    logged = logged if logged is not None else logged_by_day([user], days)
    rows = []
    for d in days:
        split = logged.get((user.id, d), {"jobs": 0.0, "idle": 0.0, "administration": 0.0, "training": 0.0})
        total = round(sum(split.values()), 2)
        expected = expected_for(user, d)
        rows.append({"date": d.isoformat(), "expected": expected, "logged": total, **{k: round(v, 2) for k, v in split.items()},
                     "under": expected > 0 and total < expected})
    return rows


def summary(rows: list[dict]) -> dict:
    expected = round(sum(r["expected"] for r in rows), 2)
    logged = round(sum(r["logged"] for r in rows), 2)
    jobs = round(sum(r["jobs"] for r in rows), 2)
    return {"expected": expected, "logged": logged, "jobs": jobs, "non_job": round(logged - jobs, 2),
            "efficiency_pct": round(logged / expected * 100) if expected else None,
            "on_jobs_pct": round(jobs / logged * 100) if logged else None,
            "days_under": sum(1 for r in rows if r["under"]), "working_days": sum(1 for r in rows if r["expected"] > 0)}


def job_rows(user) -> list[dict]:
    """The person's open jobs: hours logged against the budget."""
    from apps.coordinator.facts import open_jobs

    from .models import TimeEntry

    jobs = [i for i in open_jobs().filter(activity="") if user.id in (i.assignee_id, i.preparer_id, i.current_responsible_id)][:15]
    spent = dict(TimeEntry.objects.filter(issue__in=jobs, duration__isnull=False).values("issue_id").annotate(t=Sum("duration"))
                 .values_list("issue_id", "t"))
    return [{"key": i.key, "summary": i.summary[:80], "budget": i.budgeted_hours, "logged": _hours(spent.get(i.id)),
             "used_pct": round(_hours(spent.get(i.id)) / i.budgeted_hours * 100) if i.budgeted_hours else None} for i in jobs]


def person_tracker(user, end: date, days: int) -> dict:
    rows = day_rows(user, working_days(end, days))
    return {"user": {"id": user.id, "name": user.display_name}, "target": TARGET_HOURS, "days": rows, "summary": summary(rows),
            "jobs": job_rows(user)}


def team_tracker(people, end: date, days: int) -> list[dict]:
    """Each person's summary over the days, most under-logged first."""
    span = working_days(end, days)
    logged = logged_by_day(people, span)
    out = []
    for p in people:
        rows = day_rows(p, span, logged)
        out.append({"user": {"id": p.id, "name": p.display_name}, "summary": summary(rows),
                    "last_day": rows[-1] if rows else None})
    return sorted(out, key=lambda r: (-(r["summary"]["days_under"]), r["summary"]["efficiency_pct"] or 0, r["user"]["name"]))


def under_target(people, day: date) -> list[dict]:
    """Who logged less than they should have that day (7.5 hours, or less for leave or a part day)."""
    logged = logged_by_day(people, [day])
    out = []
    for p in people:
        expected = expected_for(p, day)
        if expected <= 0:
            continue
        total = round(sum(logged.get((p.id, day), {}).values()), 2)
        if total < expected:
            out.append({"user": p, "logged": total, "expected": expected})
    return sorted(out, key=lambda r: (r["logged"], r["user"].display_name))
