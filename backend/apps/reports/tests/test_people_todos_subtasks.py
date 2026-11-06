"""AFIT, 5 Nov 2026: a private to-do list on the dashboard; closing a sub-task leaves its main task as it
is; the CEO's snapshot of each person's work."""
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.daily_goals.models import DailyGoal, TodoItem
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


def api(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def world():
    org = Organization.get_solo()
    amy = User.objects.create_user(username="pt_amy", email="pt_amy@example.com", password="x", display_name="Amy")
    ben = User.objects.create_user(username="pt_ben", email="pt_ben@example.com", password="x", display_name="Ben")
    User.objects.create_user(username="pt_ceo", email="pt_ceo@example.com", password="x", display_name="Dushan")
    call_command("set_ceo", "pt_ceo@example.com")
    team = Team.objects.create(organization=org, name="Team 1")
    client = Client.objects.create(organization=org, name="ABC Ltd", team=team)
    project = Project.objects.create(organization=org, key="PT", name="PT", lead=amy, primary_team=team, client=client)
    provision_project_defaults(project)
    kind, _ = IssueType.objects.get_or_create(name="Task", project=None)
    IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    s = {x.name: x for x in project.workflow.statuses.all()}

    class W:
        pass

    w = W()
    w.amy, w.ben, w.ceo, w.project, w.kind, w.s = amy, ben, User.objects.get(email="pt_ceo@example.com"), project, kind, s
    return w


def task(w, summary, status, **extra):
    return Issue.objects.create(project=w.project, issue_type=w.kind, summary=summary, status=w.s[status], reporter=w.amy, **extra)


# --- the to-do list --------------------------------------------------------------------------------

def test_a_person_keeps_a_private_to_do_list_of_work_and_personal_things(world):
    me = api(world.amy)
    r = me.post("/api/todos/", {"text": "Book the dentist", "kind": "personal", "due_date": "2026-11-09"}, format="json")
    assert r.status_code == 201 and r.data["kind"] == "personal"
    me.post("/api/todos/", {"text": "Call ABC Ltd about the rates notice"}, format="json")
    assert [t["text"] for t in me.get("/api/todos/").data] == ["Book the dentist", "Call ABC Ltd about the rates notice"]  # dated first

    item = r.data["id"]
    done = me.patch(f"/api/todos/{item}/", {"done": True}, format="json").data
    assert done["done"] and done["done_at"]
    assert [t["text"] for t in me.get("/api/todos/?done=0").data] == ["Call ABC Ltd about the rates notice"]

    other = api(world.ben)
    assert other.get("/api/todos/").data == []
    assert other.patch(f"/api/todos/{item}/", {"text": "x"}, format="json").status_code == 404
    assert api(world.ceo).delete(f"/api/todos/{item}/").status_code == 404  # not even the CEO

    assert me.post("/api/todos/clear-done/").data == {"removed": 1}
    assert TodoItem.objects.filter(user=world.amy).count() == 1
    assert me.post("/api/todos/", {"text": "   "}, format="json").status_code == 400


# --- sub-tasks ------------------------------------------------------------------------------------

def test_closing_a_sub_task_leaves_its_main_task_open(world):
    main = task(world, "ABC Ltd Preparation", "In Progress", preparer=world.amy)
    me = api(world.amy)
    sub = me.post(f"/api/issues/{main.key}/subtasks/", {"summary": "Bank reconciliation"}, format="json")
    assert sub.status_code == 201
    sub_key = sub.data["key"]
    done = world.s["Complete"]
    assert me.patch(f"/api/issues/{sub_key}/", {"status_id": done.id}, format="json").status_code == 200
    main.refresh_from_db()
    assert Issue.objects.get(key=sub_key).status == done
    assert main.status == world.s["In Progress"] and main.resolved_at is None and not main.is_archived


# --- the CEO's snapshot of each person ------------------------------------------------------------

def test_the_ceo_sees_each_persons_work(world):
    today = timezone.localdate()
    late = task(world, "Preparation", "In Progress", preparer=world.amy, due_date=today - timedelta(days=2), budgeted_hours=10)
    task(world, "Adjustments", "To Start", preparer=world.amy, assignee=world.ben, due_date=today + timedelta(days=3))
    finished = task(world, "Year end", "Complete", preparer=world.amy)
    finished.resolved_at = timezone.now()
    finished.save()
    task(world, "Ben's job", "In Progress", preparer=world.ben)
    TimeEntry.objects.create(user=world.amy, issue=late, project=world.project, work_date=today, duration=timedelta(hours=3))
    TimeEntry.objects.create(user=world.amy, issue=late, project=world.project, work_date=today, started_at=timezone.now(), is_running=True)
    DailyGoal.objects.create(user=world.amy, date=today, text="ABC Ltd Preparation", linked_issue=late, planned_hours=7)
    TodoItem.objects.create(user=world.amy, text="Book the dentist", kind="personal")

    ceo = api(world.ceo)
    rows = {r["person"]["display_name"]: r for r in ceo.get("/api/reports/people/").data["people"]}
    amy = rows["Amy"]
    assert (amy["open"], amy["in_progress"], amy["to_start"], amy["overdue"], amy["due_this_week"], amy["completed_30_days"]) == (2, 1, 1, 1, 1, 1)
    assert amy["hours_today"] == 3 and amy["doing_now"]["key"] == late.key
    assert rows["Ben"]["open"] == 2  # his own job, and the one he is Team Lead on
    assert "Dushan" in rows and all(not r["person"].get("is_agent") for r in rows.values())

    d = ceo.get(f"/api/reports/people/{world.amy.id}/").data
    assert d["doing_now"]["summary"] == "Preparation"
    first = d["open_jobs"][0]
    assert (first["key"], first["days_overdue"], first["actual_hours"], first["roles"], first["sub_workspace"]) == (late.key, 2, 3, ["Accountant"], "ABC Ltd")
    assert [j["summary"] for j in d["completed"]] == ["Year end"]
    assert {r["stage"]: r["tasks"] for r in d["stages"]} == {"To Start": 1, "In Progress": 1}
    assert d["morning_plan"][0]["planned_hours"] == 7
    assert d["hours"]["today"] == 3 and len(d["hours"]["by_day"]) == 14
    assert "Book the dentist" not in str(d)  # the to-do list stays private

    assert api(world.amy).get("/api/reports/people/").status_code == 403
    assert api(world.amy).get(f"/api/reports/people/{world.ben.id}/").status_code == 403
