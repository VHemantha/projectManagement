"""The facts the coordination agent works from, worked out by code from the job records: who is
responsible, when each stage is due, whether it is done, hours used against the budget, and what
the client still owes. The AI is given these; it never computes them.

Stage completion (AFIT, 25 Oct 2026): the pre-check is done when the AI pre-check has completed on
the job; preparation is done when someone stamps "Preparation done" on it.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from . import calendar, policies
from .models import CoordinatorSettings

URGENT = ("highest", "high")


def tz() -> ZoneInfo:
    return ZoneInfo(CoordinatorSettings.get().timezone)


def local_now(now: datetime | None = None) -> datetime:
    return (now or timezone.now()).astimezone(tz())


def open_jobs():
    """Jobs the agent watches: open, not archived, top-level tasks (not sub-tasks or epics)."""
    from apps.issues.models import Issue

    return (Issue.objects.filter(is_archived=False, parent__isnull=True, issue_type__is_subtask=False)
            .exclude(status__category="done").exclude(issue_type__name__iexact="epic")
            .select_related("project__client", "status", "issue_type", "assignee", "preparer", "current_responsible", "reviewer"))


def responsible(issue):
    """The person the agent follows up: the preparer, else the assignee, else whoever holds it."""
    person = issue.preparer or issue.assignee or issue.current_responsible
    return person if person and person.is_active and not person.is_agent else None


def leads_for(issue, exclude=None) -> list:
    """The team leads of the job's workspace (its client's team, else the project's main team)."""
    from apps.teams.models import TeamMembership

    project = issue.project
    team_id = (project.client.team_id if project.client_id else None) or project.primary_team_id
    if not team_id:
        return []
    leads = [m.user for m in TeamMembership.objects.filter(team_id=team_id, role=TeamMembership.Role.LEAD).select_related("user")
             if m.user.is_active and not m.user.is_agent]
    return [u for u in leads if exclude is None or u.pk != exclude.pk]


def precheck_done(issue) -> bool:
    from apps.precheck.models import AIPrecheck, TaskMilestone

    return (TaskMilestone.objects.filter(issue=issue, kind="precheck").exists()
            or AIPrecheck.objects.filter(issue=issue, kind=AIPrecheck.Kind.PRECHECK, status__in=["complete", "partial"]).exists())


def preparation_done(issue) -> bool:
    from apps.precheck.models import TaskMilestone

    return TaskMilestone.objects.filter(issue=issue, kind="preparation").exists()


def has_activity(issue) -> bool:
    """Any sign of work: time logged, a pre-check run, a comment, a stage stamped."""
    from apps.issues.models import Comment
    from apps.precheck.models import AIPrecheck, TaskMilestone
    from apps.timesheets.models import TimeEntry

    return (TimeEntry.objects.filter(issue=issue).exists() or AIPrecheck.objects.filter(issue=issue).exists()
            or Comment.objects.filter(issue=issue).exclude(author__is_agent=True).exists()
            or TaskMilestone.objects.filter(issue=issue).exists())


def start_date(issue) -> date:
    return issue.start_date or local_now(issue.created_at).date()


def precheck_due(issue, person=None) -> date:
    days = int(policies.resolve("precheck_due_days", job=issue, person=person))
    basis = policies.resolve("day_basis", job=issue, person=person)
    return calendar.add_days(start_date(issue), days, basis=basis, user=person)


def working_days_late(due: date, today: date, person=None) -> int:
    n, day = 0, due
    while day < today:
        day += timedelta(days=1)
        if calendar.is_working_day(day, person):
            n += 1
    return n


def outstanding_client_requests(issue) -> list[str]:
    """What the latest pre-check still asks of the client (read only; the pre-check is unchanged)."""
    from apps.precheck.services import last_precheck

    last = last_precheck(issue) or {}
    return [r["item"] for r in last.get("requests") or [] if r.get("item")]


@dataclass
class JobFacts:
    key: str
    title: str
    client: str
    priority: str
    status: str
    start: date
    precheck_due: date
    precheck_done: bool
    prep_due: date | None
    prep_done: bool
    actual_hours: float
    budget_hours: float | None
    outstanding: list[str]

    @property
    def utilisation_pct(self) -> int | None:
        return round(self.actual_hours / self.budget_hours * 100) if self.budget_hours else None

    def line(self) -> str:
        """One line for the AI's context (and the CEO's briefing)."""
        hours = f"{self.actual_hours:.1f}h of {self.budget_hours:.1f}h budget ({self.utilisation_pct}%)" if self.budget_hours else f"{self.actual_hours:.1f}h logged, no budget"
        prep = "done" if self.prep_done else (f"due {self.prep_due:%a %d %b}" if self.prep_due else "no due date")
        pre = "done" if self.precheck_done else f"due {self.precheck_due:%a %d %b}"
        extra = f"; {len(self.outstanding)} items still to come from the client" if self.outstanding else ""
        return f"{self.key} {self.title} ({self.client}; {self.priority}; {self.status}) — pre-check {pre}; preparation {prep}; {hours}{extra}"


def job_facts(issue, person=None) -> JobFacts:
    from apps.timesheets.budget import issue_actual_hours

    return JobFacts(
        key=issue.key, title=issue.summary[:80], client=issue.project.client.name if issue.project.client_id else issue.project.name,
        priority=issue.priority, status=issue.status.name, start=start_date(issue), precheck_due=precheck_due(issue, person),
        precheck_done=precheck_done(issue), prep_due=issue.due_date, prep_done=preparation_done(issue),
        actual_hours=float(issue_actual_hours(issue.id) or 0), budget_hours=issue.budgeted_hours, outstanding=outstanding_client_requests(issue),
    )


def within_window(now: datetime | None = None) -> bool:
    """Messages go out only on working days, between the window's start and end (local time)."""
    t = local_now(now)
    start, end = policies.resolve("message_window_start"), policies.resolve("message_window_end")
    return calendar.is_working_day(t.date()) and start <= t.strftime("%H:%M") < end
