"""A task's standard sub-tasks (AFIT, 27 Oct 2026), added when the task is created:

    Pre-check        due 3 days after the task's start (or the day it is added)
    Preparation      due 5 working days after the pre-check
    Internal Review  due 1 working day after preparation
    Client Review    no date: once the client has advised

The pre-check's days and how they are counted (working days by default) are the coordination
agent's rule, so the task and the agent's follow-ups agree. Working days skip weekends and public
holidays. The task's due date may not be before its internal review.
"""
from datetime import date

from django.utils import timezone

PRECHECK, PREPARATION, INTERNAL_REVIEW, CLIENT_REVIEW = "Pre-check", "Preparation", "Internal Review", "Client Review"
SUBTASKS = [PRECHECK, PREPARATION, INTERNAL_REVIEW, CLIENT_REVIEW]
PREPARATION_WORKING_DAYS = 5
REVIEW_WORKING_DAYS = 1


def today() -> date:
    from apps.coordinator.facts import local_now

    return local_now().date()


def stage_dates(start: date | None, job=None) -> dict[str, date | None]:
    from apps.coordinator import calendar, policies

    start = start or today()
    days = int(policies.resolve("precheck_due_days", job=job))
    basis = policies.resolve("day_basis", job=job)
    precheck = calendar.add_days(start, days, basis=basis)
    preparation = calendar.add_days(precheck, PREPARATION_WORKING_DAYS)
    review = calendar.add_days(preparation, REVIEW_WORKING_DAYS)
    return {PRECHECK: precheck, PREPARATION: preparation, INTERNAL_REVIEW: review, CLIENT_REVIEW: None}


def internal_review_of(issue):
    return issue.subtasks.filter(summary__iexact=INTERNAL_REVIEW).first() if issue.pk else None


def create_default_subtasks(issue) -> list:
    """The four sub-tasks, with the task's people and status, each due on its stage's date."""
    from apps.workflow.models import IssueType

    from .models import Issue
    from .rank import rank_after

    subtask_type = IssueType.objects.filter(is_subtask=True, project__isnull=True).first() or IssueType.objects.filter(is_subtask=True).first()
    if subtask_type is None:
        subtask_type, _ = IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    dates = stage_dates(issue.start_date or timezone.localdate(), job=issue)
    created = []
    for name in SUBTASKS:
        last = Issue.objects.filter(project=issue.project).order_by("-rank").first()
        created.append(Issue.objects.create(
            project=issue.project, issue_type=subtask_type, summary=name, parent=issue, status=issue.status, priority=issue.priority,
            reporter=issue.reporter, assignee=issue.assignee, preparer=issue.preparer, reviewer=issue.reviewer,
            current_responsible=issue.current_responsible, due_date=dates[name], rank=rank_after(last.rank) if last else "000000",
        ))
    return created
