"""The CEO's home page (AFIT, 28 Oct 2026): the whole organisation at a glance, in place of the
"assigned to you" board. CEO only.

Tasks are top-level tasks (not sub-tasks or epics) that are not archived. A task's workspace is its
sub-workspace's workspace, else its project's own workspace.
"""
from collections import Counter, defaultdict
from datetime import timedelta

from django.db.models import Sum
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.coordinator.models import AgentCase, Commitment, LeaveRecord
from apps.issues.models import Issue
from apps.precheck.models import AIPrecheck
from apps.timesheets.models import TimeEntry, Timesheet
from apps.workflow.services import STATUS_DEFS

WEEKS = 12
STAGE_ORDER = [name for name, _, _ in STATUS_DEFS]
PRIORITIES = [value for value, _ in Issue.Priority.choices]


class IsCeo(permissions.BasePermission):
    message = "Only the CEO can see the organisation dashboard."

    def has_permission(self, request, view):
        from apps.coordinator.services import is_ceo

        return is_ceo(request.user)


def _hours(duration) -> float:
    return round(duration.total_seconds() / 3600, 1) if duration else 0.0


def _week_start(day):
    return day - timedelta(days=day.weekday())


class CeoDashboardView(APIView):
    """GET /api/reports/ceo-dashboard/"""

    permission_classes = [permissions.IsAuthenticated, IsCeo]

    def get(self, request):
        now = timezone.now()
        today = timezone.localdate()
        week_end = today + timedelta(days=7)
        first_week = _week_start(today) - timedelta(weeks=WEEKS - 1)
        weeks = [first_week + timedelta(weeks=i) for i in range(WEEKS)]

        tasks = list(
            Issue.objects.filter(parent__isnull=True, is_archived=False)
            .exclude(issue_type__name="Epic")
            .values(
                "id", "key", "summary", "status__name", "status__category", "priority", "due_date", "created_at", "resolved_at",
                "assignee_id", "assignee__display_name", "budgeted_hours", "estimated_hours",
                "project__client__name", "project__client__team__name", "project__primary_team__name",
            )
        )
        open_tasks = [t for t in tasks if t["status__category"] != "done"]
        overdue = [t for t in open_tasks if t["due_date"] and t["due_date"] < today]
        overdue_ids = {t["id"] for t in overdue}
        due_soon = [t for t in open_tasks if t["due_date"] and today <= t["due_date"] <= week_end]
        done_30 = [t for t in tasks if t["resolved_at"] and t["resolved_at"] >= now - timedelta(days=30)]

        # Stages in the board's order; any other stage name after them.
        stages = Counter(t["status__name"] for t in tasks)
        stage_rows = [{"stage": s, "tasks": stages.pop(s, 0)} for s in STAGE_ORDER] + [
            {"stage": s, "tasks": n} for s, n in sorted(stages.items())
        ]

        def workspace_of(t):
            return t["project__client__team__name"] or t["project__primary_team__name"] or "No workspace"

        by_workspace = defaultdict(lambda: {"open": 0, "overdue": 0, "completed_30": 0})
        for t in open_tasks:
            by_workspace[workspace_of(t)]["open"] += 1
        for t in overdue:
            by_workspace[workspace_of(t)]["overdue"] += 1
        for t in done_30:
            by_workspace[workspace_of(t)]["completed_30"] += 1
        workspace_rows = sorted(
            ({"workspace": w, **v, "on_time": v["open"] - v["overdue"]} for w, v in by_workspace.items()),
            key=lambda r: (-r["open"], r["workspace"]),
        )

        by_client = Counter(t["project__client__name"] or "No sub-workspace" for t in open_tasks)
        client_rows = [{"sub_workspace": c, "open": n} for c, n in by_client.most_common(10)]

        lead = defaultdict(lambda: {"open": 0, "overdue": 0})
        names = {}
        for t in open_tasks:
            key = t["assignee_id"] or 0
            names[key] = t["assignee__display_name"] or "No Team Lead"
            lead[key]["open"] += 1
            if t["id"] in overdue_ids:
                lead[key]["overdue"] += 1
        workload_rows = sorted(
            ({"person": names[k], **v, "on_time": v["open"] - v["overdue"]} for k, v in lead.items()),
            key=lambda r: (-r["open"], r["person"]),
        )[:12]

        priorities = Counter(t["priority"] for t in open_tasks)
        priority_rows = [{"priority": dict(Issue.Priority.choices)[p], "tasks": priorities.get(p, 0)} for p in PRIORITIES]

        # Created and completed per week (Monday start), last 12 weeks.
        created = Counter(_week_start(timezone.localtime(t["created_at"]).date()) for t in tasks)
        completed = Counter(_week_start(timezone.localtime(t["resolved_at"]).date()) for t in tasks if t["resolved_at"])
        flow_rows = [{"week": w, "created": created.get(w, 0), "completed": completed.get(w, 0)} for w in weeks]

        entries = TimeEntry.objects.filter(work_date__gte=first_week, duration__isnull=False)
        hours = defaultdict(lambda: {"billable": 0.0, "non_billable": 0.0})
        for row in entries.values("work_date", "is_billable").annotate(total=Sum("duration")):
            hours[_week_start(row["work_date"])]["billable" if row["is_billable"] else "non_billable"] += _hours(row["total"])
        hours_rows = [{"week": w, "billable": round(hours[w]["billable"], 1), "non_billable": round(hours[w]["non_billable"], 1)} for w in weeks]
        month_hours = _hours(TimeEntry.objects.filter(work_date__gte=today.replace(day=1), duration__isnull=False).aggregate(t=Sum("duration"))["t"])

        # Budget: open tasks whose logged time is past their budget.
        open_ids = [t["id"] for t in open_tasks if t["budgeted_hours"]]
        logged = {
            r["issue_id"]: _hours(r["total"])
            for r in TimeEntry.objects.filter(issue_id__in=open_ids, duration__isnull=False).values("issue_id").annotate(total=Sum("duration"))
        }
        over_budget = sorted(
            (
                {"key": t["key"], "summary": t["summary"], "budgeted": t["budgeted_hours"], "actual": logged.get(t["id"], 0.0),
                 "team_lead": t["assignee__display_name"] or ""}
                for t in open_tasks if t["budgeted_hours"] and logged.get(t["id"], 0.0) > t["budgeted_hours"]
            ),
            key=lambda r: r["budgeted"] - r["actual"],
        )[:8]

        runs = AIPrecheck.objects.filter(created_at__gte=now - timedelta(days=30))
        verdicts = Counter(r.get_verdict_display() if r.verdict else r.get_status_display() for r in runs.only("verdict", "status"))

        cases = Counter(AgentCase.objects.exclude(state=AgentCase.State.RESOLVED).values_list("state", flat=True))
        commitments = Counter(
            Commitment.objects.filter(status__in=[Commitment.Status.KEPT, Commitment.Status.MISSED], created_at__gte=now - timedelta(days=90))
            .values_list("status", flat=True)
        )
        on_leave = list(
            LeaveRecord.objects.filter(status=LeaveRecord.Status.APPROVED, start_date__lte=today, end_date__gte=today)
            .values_list("user__display_name", flat=True)
        )

        return Response({
            "as_of": now,
            "totals": {
                "open": len(open_tasks),
                "overdue": len(overdue),
                "due_this_week": len(due_soon),
                "completed_30_days": len(done_30),
                "hours_this_month": month_hours,
                "timesheets_to_approve": Timesheet.objects.filter(status=Timesheet.Status.SUBMITTED).count(),
            },
            "stages": stage_rows,
            "workspaces": workspace_rows,
            "sub_workspaces": client_rows,
            "workload": workload_rows,
            "priorities": priority_rows,
            "flow": flow_rows,
            "hours": hours_rows,
            "over_budget": over_budget,
            "prechecks": [{"result": k, "runs": n} for k, n in verdicts.most_common()],
            "follow_ups": {"waiting": cases.get(AgentCase.State.ASKED, 0), "answered": cases.get(AgentCase.State.ANSWERED, 0),
                           "escalated": cases.get(AgentCase.State.ESCALATED, 0)},
            "commitments_90_days": {"kept": commitments.get(Commitment.Status.KEPT, 0), "missed": commitments.get(Commitment.Status.MISSED, 0)},
            "on_leave_today": on_leave,
        })
