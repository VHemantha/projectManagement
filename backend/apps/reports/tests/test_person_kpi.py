"""A person's budget KPI: tasks assigned to them with budgeted time, the hours they logged, and
whether each came in within budget."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType, Workflow, WorkflowStatus

pytestmark = pytest.mark.django_db


def test_budget_vs_actual_for_the_person():
    pat = User.objects.create_user(username="pat", email="pat@example.com", password="x", display_name="Pat")
    org = Organization.get_solo()
    project = Project.objects.create(organization=org, key="KP", name="KPI", lead=pat)
    wf = Workflow.objects.create(project=project)
    todo = WorkflowStatus.objects.create(workflow=wf, name="To do", category="todo", order=0)
    done = WorkflowStatus.objects.create(workflow=wf, name="Done", category="done", order=1)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    now = timezone.now()

    def job(key, budget, hours, status, resolved=None):
        issue = Issue.objects.create(project=project, issue_type=task, summary=key, status=status, reporter=pat, assignee=pat,
                                     budgeted_hours=budget, resolved_at=resolved)
        TimeEntry.objects.create(user=pat, issue=issue, project=project, work_date=now.date(), duration=timedelta(hours=hours))
        return issue

    job("within", 10, 8, done, now - timedelta(days=5))
    job("over", 4, 6, done, now - timedelta(days=10))
    job("long ago", 5, 1, done, now - timedelta(days=400))  # outside the period
    job("open", 3, 4, todo)
    Issue.objects.create(project=project, issue_type=task, summary="no budget", status=done, reporter=pat, assignee=pat, resolved_at=now)

    c = APIClient()
    c.force_authenticate(user=pat)
    kpi = c.get(f"/api/reports/people/{pat.id}/kpi/").data
    f = kpi["finished"]
    assert (f["tasks"], f["within_budget"], f["over_budget"], f["pct_within_budget"]) == (2, 1, 1, 50.0)
    assert (f["budgeted_hours"], f["actual_hours"], f["efficiency_pct"]) == (14, 14, 100.0)
    assert kpi["open"] == {"tasks": 1, "over_budget_already": 1}
    assert {r["summary"] for r in kpi["tasks"]} == {"within", "over", "open"}
    assert c.get(f"/api/reports/people/{pat.id}/kpi/?from=bad").status_code == 400
