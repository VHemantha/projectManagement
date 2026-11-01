"""The morning plan (AFIT, 1 Nov 2026): each item with its hours today and completion date; a team lead
sees everyone's plans, checks what was done, and the rating counts plans kept. Also: logging time for
someone else, and the nightly auto-archive of tasks completed 7 days ago."""
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.coordinator import kpi
from apps.daily_goals.models import DailyGoal
from apps.issues.archive import auto_archive
from apps.issues.models import Issue, IssueHistory
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team, TeamMembership
from apps.timesheets.models import TimeEntry, Timesheet
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    org = Organization.get_solo()
    lead = User.objects.create_user(username="pl_lead", email="pl_lead@example.com", password="x", display_name="Lee")
    amy = User.objects.create_user(username="pl_amy", email="pl_amy@example.com", password="x", display_name="Amy")
    other = User.objects.create_user(username="pl_other", email="pl_other@example.com", password="x", display_name="Oz")
    group = Team.objects.create(organization=org, name="Group 1")
    team = Team.objects.create(organization=org, name="Team 1", parent=group)
    TeamMembership.objects.create(team=group, user=lead, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=team, user=amy)
    client = Client.objects.create(organization=org, name="ABC Ltd", team=team)
    project = Project.objects.create(organization=org, key="ABC", name="ABC", lead=lead, primary_team=team, client=client)
    provision_project_defaults(project)
    task_type, _ = IssueType.objects.get_or_create(name="Task", project=None)
    sub_type, _ = IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    statuses = {s.name: s for s in project.workflow.statuses.all()}
    task = Issue.objects.create(project=project, issue_type=task_type, summary="Preparation", status=statuses["In Progress"],
                                reporter=lead, preparer=amy)
    return {"lead": lead, "amy": amy, "other": other, "task": task, "statuses": statuses, "project": project,
            "task_type": task_type, "sub_type": sub_type}


def api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_a_plan_item_from_a_task_reads_as_its_sub_workspace_and_name_with_hours_and_completion(world):
    today = date.today()
    r = api(world["amy"]).post("/api/daily-goals/", {
        "date": str(today), "linked_issue_id": world["task"].id, "planned_hours": 7, "complete_by": str(today + timedelta(days=1)),
    }, format="json")
    assert r.status_code == 201, r.data
    assert r.data["text"] == "ABC Ltd Preparation"
    assert r.data["sub_workspace"] == "ABC Ltd" and r.data["planned_hours"] == 7.0
    assert r.data["complete_by"] == str(today + timedelta(days=1)) and r.data["task_done"] is None

    bad = api(world["amy"]).post("/api/daily-goals/", {"date": str(today), "text": "x", "complete_by": str(today - timedelta(days=1))}, format="json")
    assert bad.status_code == 400 and "complete_by" in bad.data
    empty = api(world["amy"]).post("/api/daily-goals/", {"date": str(today)}, format="json")
    assert empty.status_code == 400 and "text" in empty.data


def test_the_team_lead_sees_everyones_plans_with_hours_and_checks_them(world):
    today = date.today()
    goal = DailyGoal.objects.create(user=world["amy"], date=today, text="ABC Ltd Preparation", linked_issue=world["task"],
                                    planned_hours=7, status=DailyGoal.Status.ACHIEVED)
    DailyGoal.objects.create(user=world["amy"], date=today, text="Xyz Ltd Adjustments", planned_hours=2)
    TimeEntry.objects.create(user=world["amy"], work_date=today, duration=timedelta(hours=6.5))

    r = api(world["lead"]).get(f"/api/daily-goals/team/?date={today}")
    assert r.status_code == 200
    rows = {row["person"]["display_name"]: row for row in r.data["people"]}
    assert set(rows) == {"Amy"}  # the lead leads Amy through the group; not Oz, not themselves
    amy = rows["Amy"]
    assert amy["planned_hours"] == 9 and amy["logged_hours"] == 6.5
    assert (amy["achieved"], amy["not_achieved"], amy["unchecked"]) == (1, 0, 1)

    assert api(world["amy"]).post(f"/api/daily-goals/{goal.id}/check/", {"result": "confirmed"}, format="json").status_code == 403
    assert api(world["other"]).get(f"/api/daily-goals/team/?date={today}").data["people"] == []
    r = api(world["lead"]).post(f"/api/daily-goals/{goal.id}/check/", {"result": "not_done"}, format="json")
    assert r.status_code == 200 and r.data["lead_check"] == "not_done" and r.data["checked_by"]["id"] == world["lead"].id
    amy = api(world["lead"]).get(f"/api/daily-goals/team/?date={today}").data["people"][0]
    assert (amy["achieved"], amy["not_achieved"], amy["unchecked"]) == (0, 1, 0)
    assert api(world["lead"]).post(f"/api/daily-goals/{goal.id}/check/", {"result": "maybe"}, format="json").status_code == 400


def test_morning_plans_kept_is_a_kpi_and_the_leads_check_overrules(world):
    today = kpi._local(timezone.now())  # the agent's (New Zealand) today
    for i, (status, check) in enumerate([("achieved", ""), ("achieved", "confirmed"), ("achieved", "not_done"),
                                         ("not_achieved", ""), ("carried_over", "")]):
        DailyGoal.objects.create(user=world["amy"], date=today - timedelta(days=i + 1), text=f"Item {i}", status=status,
                                 note="x", lead_check=check)
    DailyGoal.objects.create(user=world["amy"], date=today, text="Today does not count yet")
    m = kpi.plans(world["amy"], today - timedelta(days=30), today)
    assert (m.good, m.total) == (2, 5) and m.score == 40.0
    rated = kpi.rate(world["amy"], today - timedelta(days=30), today)
    assert any(row["key"] == "plans" and row["counted"] for row in rated["metrics"])


def test_a_lead_logs_time_for_someone_away_and_they_are_told(world):
    today = date.today()
    r = api(world["lead"]).post("/api/time-entries/", {
        "user_id": world["amy"].id, "issue_id": world["task"].id, "work_date": str(today), "duration_seconds_input": 7200,
    }, format="json")
    assert r.status_code == 201, r.data
    entry = TimeEntry.objects.get()
    assert entry.user == world["amy"] and entry.logged_by == world["lead"]
    assert r.data["logged_by"]["id"] == world["lead"].id
    assert world["amy"].notifications.exists()

    people = api(world["lead"]).get("/api/time-entries/on-behalf-people/").data
    assert [p["display_name"] for p in people] == ["Amy"]
    # The one who logged it may correct it; someone who doesn't lead Amy may not log for her.
    assert api(world["lead"]).patch(f"/api/time-entries/{entry.id}/", {"duration_seconds_input": 3600}, format="json").status_code == 200
    denied = api(world["other"]).post("/api/time-entries/", {"user_id": world["amy"].id, "work_date": str(today),
                                                            "duration_seconds_input": 60}, format="json")
    assert denied.status_code == 403
    # Not into a week Amy has already submitted.
    Timesheet.objects.create(user=world["amy"], period_start=today - timedelta(days=today.weekday()),
                             period_end=today - timedelta(days=today.weekday()) + timedelta(days=6), status="submitted")
    closed = api(world["lead"]).post("/api/time-entries/", {"user_id": world["amy"].id, "work_date": str(today),
                                                           "duration_seconds_input": 60}, format="json")
    assert closed.status_code == 400 and "work_date" in closed.data
    # Logging for yourself is as before.
    own = api(world["amy"]).post("/api/time-entries/", {"work_date": str(today), "duration_seconds_input": 60}, format="json")
    assert own.status_code == 201 and own.data["logged_by"] is None


def test_tasks_completed_seven_days_ago_are_archived_with_their_sub_tasks(world):
    s = world["statuses"]
    now = timezone.now()

    def task(summary, status, resolved_days=None, moved_days=None):
        t = Issue.objects.create(project=world["project"], issue_type=world["task_type"], summary=summary, status=status,
                                 reporter=world["lead"], resolved_at=now - timedelta(days=resolved_days) if resolved_days else None)
        if moved_days is not None:
            h = IssueHistory.objects.create(issue=t, field_changed="status", old_value="x", new_value=status.name)
            IssueHistory.objects.filter(pk=h.pk).update(timestamp=now - timedelta(days=moved_days))
        return t

    old_done = task("Done 8 days ago", s["Complete"], resolved_days=8, moved_days=1)  # moved on to Complete later: still 8
    sub = Issue.objects.create(project=world["project"], issue_type=world["sub_type"], summary="Sub", status=s["To Start"],
                               reporter=world["lead"], parent=old_done)
    to_archive = task("In the last column 10 days", s["To be Archived"], resolved_days=10)
    recent = task("Done 3 days ago", s["Complete"], resolved_days=3)
    open_old = task("Open, old", s["In Progress"], moved_days=30)

    call_command("auto_archive_tasks")
    archived = set(Issue.objects.filter(is_archived=True).values_list("id", flat=True))
    assert archived == {old_done.id, sub.id, to_archive.id}
    assert recent.id not in archived and open_old.id not in archived
    assert auto_archive() == 0  # nothing left to do
