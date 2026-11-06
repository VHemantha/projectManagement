"""The CEO's view of each person (AFIT, 5 Nov 2026): a snapshot of everyone, and one person's own
dashboard: what they are doing now, their open and in-progress jobs by stage, what is overdue,
what they finished, their hours against their working week, today's morning plan, their rating and
the follow-ups open with them. CEO only; worked out by code from the records.

A person's jobs are the top-level tasks (not sub-tasks or epics, not archived) on which they are the
Accountant, the Team Lead or the one currently responsible; each job says which.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.issues.models import Issue
from apps.timesheets.models import TimeEntry

from .ceo import STAGE_ORDER, IsCeo, _hours, _week_start

ROLES = (("preparer", "Accountant"), ("assignee", "Team Lead"), ("current_responsible", "Currently responsible"))
HISTORY_DAYS = 14


def people():
    return get_user_model().objects.filter(is_active=True, is_agent=False).order_by("display_name", "id")


def _tasks(person_ids):
    """Every job of these people (open, and finished in the last 30 days), with who holds which role."""
    since = timezone.now() - timedelta(days=30)
    roles = Q()
    for field, _ in ROLES:
        roles |= Q(**{f"{field}_id__in": person_ids})
    return list(
        Issue.objects.filter(roles, parent__isnull=True, is_archived=False).exclude(issue_type__name__iexact="epic")
        .filter(Q(status__category__in=["todo", "in_progress"]) | Q(resolved_at__gte=since))
        .select_related("status", "project__client")
        .order_by("due_date", "id")
    )


def _roles_of(issue, person_id) -> list[str]:
    return [label for field, label in ROLES if getattr(issue, f"{field}_id") == person_id]


def _doing_now(person_ids) -> dict:
    """What each person has a timer running on."""
    out = {}
    for e in TimeEntry.objects.filter(user_id__in=person_ids, is_running=True).select_related("issue__project__client").order_by("-started_at"):
        if e.user_id in out:
            continue
        issue = e.issue
        out[e.user_id] = {"key": issue.key if issue else "", "summary": issue.summary if issue else (e.description or "Time not on a task"),
                          "sub_workspace": issue.project.client.name if issue and issue.project.client_id else "",
                          "since": e.started_at}
    return out


def _hours_by_person(person_ids, since) -> dict:
    rows = (TimeEntry.objects.filter(user_id__in=person_ids, work_date__gte=since, duration__isnull=False)
            .values("user_id").annotate(total=Sum("duration")))
    return {r["user_id"]: _hours(r["total"]) for r in rows}


def _on_leave(today) -> set:
    from apps.coordinator.models import LeaveRecord

    return set(LeaveRecord.objects.filter(status=LeaveRecord.Status.APPROVED, start_date__lte=today, end_date__gte=today)
               .values_list("user_id", flat=True))


def _latest_ratings(person_ids) -> dict:
    from apps.coordinator.models import KpiSnapshot

    out = {}
    for s in KpiSnapshot.objects.filter(person_id__in=person_ids).order_by("person_id", "-period_end"):
        out.setdefault(s.person_id, s)
    return out


def _person(u) -> dict:
    return {"id": u.id, "display_name": u.display_name or u.username, "job_title": u.job_title, "avatar": u.avatar.url if u.avatar else None,
            "role": u.role}


def _figures(person_id, tasks, today, week_end) -> dict:
    mine = [t for t in tasks if _roles_of(t, person_id)]
    open_ = [t for t in mine if t.status.category != "done"]
    since_week = _week_start(today)
    done = [t for t in mine if t.status.category == "done" and t.resolved_at]
    return {
        "open": len(open_),
        "in_progress": sum(1 for t in open_ if t.status.category == "in_progress"),
        "to_start": sum(1 for t in open_ if t.status.category == "todo"),
        "overdue": sum(1 for t in open_ if t.due_date and t.due_date < today),
        "due_this_week": sum(1 for t in open_ if t.due_date and today <= t.due_date <= week_end),
        "completed_week": sum(1 for t in done if timezone.localtime(t.resolved_at).date() >= since_week),
        "completed_30_days": len(done),
    }


def snapshot(now=None) -> dict:
    """Everyone at a glance."""
    now = now or timezone.now()
    today = timezone.localdate()
    everyone = list(people())
    ids = [p.id for p in everyone]
    tasks = _tasks(ids)
    doing = _doing_now(ids)
    week_hours = _hours_by_person(ids, _week_start(today))
    today_hours = _hours_by_person(ids, today)
    leave = _on_leave(today)
    ratings = _latest_ratings(ids)
    rows = []
    for p in everyone:
        r = ratings.get(p.id)
        rows.append({"person": _person(p), **_figures(p.id, tasks, today, today + timedelta(days=7)),
                     "hours_today": today_hours.get(p.id, 0.0), "hours_week": week_hours.get(p.id, 0.0),
                     "doing_now": doing.get(p.id), "on_leave": p.id in leave,
                     "rating": {"score": r.score, "rating": r.rating, "period_end": r.period_end} if r else None})
    return {"as_of": now, "people": rows}


def _job(t, person_id, today, actual) -> dict:
    return {"key": t.key, "summary": t.summary, "sub_workspace": t.project.client.name if t.project.client_id else "",
            "stage": t.status.name, "category": t.status.category, "priority": t.priority, "start_date": t.start_date,
            "due_date": t.due_date, "days_overdue": (today - t.due_date).days if t.due_date and t.due_date < today and t.status.category != "done" else None,
            "budget_hours": t.budgeted_hours, "actual_hours": actual.get(t.id, 0.0), "roles": _roles_of(t, person_id),
            "completed_at": t.resolved_at if t.status.category == "done" else None}


def person_dashboard(person, now=None) -> dict:
    """One person's work, in detail."""
    from apps.coordinator import calendar
    from apps.coordinator.models import AgentCase
    from apps.daily_goals.models import DailyGoal

    now = now or timezone.now()
    today = timezone.localdate()
    week_start = _week_start(today)
    tasks = [t for t in _tasks([person.id]) if _roles_of(t, person.id)]
    actual = {r["issue_id"]: _hours(r["total"]) for r in TimeEntry.objects.filter(issue_id__in=[t.id for t in tasks], duration__isnull=False)
              .values("issue_id").annotate(total=Sum("duration"))}
    jobs = [_job(t, person.id, today, actual) for t in tasks]
    open_jobs = [j for j in jobs if j["category"] != "done"]
    open_jobs.sort(key=lambda j: (j["days_overdue"] is None, -(j["days_overdue"] or 0), j["due_date"] is None, j["due_date"] or today))
    finished = sorted((j for j in jobs if j["category"] == "done"), key=lambda j: j["completed_at"] or now, reverse=True)

    stages = Counter(j["stage"] for j in open_jobs)
    stage_rows = [{"stage": s, "tasks": stages.pop(s)} for s in STAGE_ORDER if s in stages] + [
        {"stage": s, "tasks": n} for s, n in sorted(stages.items())]

    first_day = today - timedelta(days=HISTORY_DAYS - 1)
    by_day = defaultdict(float)
    for r in (TimeEntry.objects.filter(user=person, work_date__gte=first_day, duration__isnull=False)
              .values("work_date").annotate(total=Sum("duration"))):
        by_day[r["work_date"]] += _hours(r["total"])
    days = [first_day + timedelta(days=i) for i in range(HISTORY_DAYS)]
    hours_rows = [{"day": d, "hours": round(by_day.get(d, 0.0), 1), "expected": calendar.expected_hours(person, d)} for d in days]
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    week = {"logged": _hours_by_person([person.id], week_start).get(person.id, 0.0),
            "expected": round(sum(calendar.expected_hours(person, d) for d in week_days), 1),
            "month": _hours_by_person([person.id], today.replace(day=1)).get(person.id, 0.0)}

    recent = [{"work_date": e.work_date, "hours": _hours(e.duration), "key": e.issue.key if e.issue else "",
               "summary": e.issue.summary if e.issue else "", "description": e.description}
              for e in TimeEntry.objects.filter(user=person, duration__isnull=False).select_related("issue").order_by("-work_date", "-id")[:10]]

    plan = [{"text": g.text, "key": g.linked_issue.key if g.linked_issue else "", "planned_hours": g.planned_hours, "complete_by": g.complete_by,
             "status": g.status, "status_label": g.get_status_display(), "lead_check": g.lead_check, "note": g.note}
            for g in DailyGoal.objects.filter(user=person, date=today).select_related("linked_issue")]

    cases = [{"key": c.issue.key, "summary": c.issue.summary, "matter": c.get_kind_display(), "state": c.state,
              "state_label": c.get_state_display(), "due_date": c.due_date, "revised_due": c.revised_due, "asked": c.asked}
             for c in AgentCase.objects.filter(person=person).exclude(state=AgentCase.State.RESOLVED).select_related("issue")]

    r = _latest_ratings([person.id]).get(person.id)
    return {
        "as_of": now,
        "person": _person(person),
        "on_leave": person.id in _on_leave(today),
        "doing_now": _doing_now([person.id]).get(person.id),
        "figures": _figures(person.id, tasks, today, today + timedelta(days=7)),
        "hours": {"today": by_day.get(today, 0.0), **week, "by_day": hours_rows},
        "stages": stage_rows,
        "open_jobs": open_jobs,
        "completed": finished[:15],
        "morning_plan": plan,
        "recent_time": recent,
        "follow_ups": cases,
        "rating": ({"score": r.score, "rating": r.rating, "period_start": r.period_start, "period_end": r.period_end,
                    "metrics": r.metrics} if r else None),
    }


class PeopleSnapshotView(APIView):
    """GET /api/reports/people/ — everyone's work at a glance (CEO only)."""

    permission_classes = [permissions.IsAuthenticated, IsCeo]

    def get(self, request):
        return Response(snapshot())


class PersonDashboardView(APIView):
    """GET /api/reports/people/<id>/ — one person's work in detail (CEO only)."""

    permission_classes = [permissions.IsAuthenticated, IsCeo]

    def get(self, request, pk):
        return Response(person_dashboard(get_object_or_404(people(), pk=pk)))
