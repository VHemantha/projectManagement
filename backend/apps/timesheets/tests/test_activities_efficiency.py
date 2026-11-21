"""AFIT, 21 Nov 2026: time not on a job is logged to hidden cards - Idle, Administration and Training - which
never show on a Kanban view; and the efficiency tracker shows each working day's hours against the 7.5 expected."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.teams.models import Team, TeamMembership
from apps.timesheets.activities import ACTIVITY_PROJECT_KEY
from apps.timesheets.efficiency import working_days
from apps.timesheets.models import TimeEntry

pytestmark = pytest.mark.django_db


def person(name):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title())


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def test_idle_administration_and_training_cards_are_hidden_and_time_can_be_logged_to_them():
    pat = person("pat")
    cards = api(pat).get("/api/timesheets/activities/").data
    assert [c["label"] for c in cards] == ["Idle", "Administration", "Training"]
    assert [c["activity"] for c in cards] == ["idle", "administration", "training"]
    assert api(pat).get("/api/timesheets/activities/").data == cards  # made once
    issues = Issue.objects.filter(activity__in=["idle", "administration", "training"])
    assert issues.count() == 3 and all(i.is_archived and i.project.key == ACTIVITY_PROJECT_KEY and i.project.is_archived for i in issues)
    # Never on a board or a task list ...
    listed = api(pat).get("/api/issues/", {"page_size": 100}).data
    assert not any(i["key"] in {c["key"] for c in cards} for i in listed.get("results", listed))
    # ... nor in the projects tree.
    for mode in ("", "client", "team"):
        tree = api(pat).get("/api/reports/nav-tree/", {"mode": mode} if mode else {})
        assert tree.status_code == 200 and ACTIVITY_PROJECT_KEY not in str(tree.data) and "Non-job time" not in str(tree.data)
    # Time goes to them like to any task.
    made = api(pat).post("/api/time-entries/", {"issue_id": cards[1]["id"], "work_date": timezone.localdate().isoformat(),
                                                 "duration_seconds_input": 3600, "description": "Team meeting"}, format="json")
    assert made.status_code == 201 and TimeEntry.objects.get().issue.activity == "administration"


def test_the_efficiency_tracker_shows_each_day_against_seven_and_a_half_hours():
    pat, lee, eve = person("pat"), person("lee"), person("eve")
    team = Team.objects.create(name="Rentals", organization=Organization.get_solo())
    TeamMembership.objects.create(team=team, user=lee, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=team, user=pat, role=TeamMembership.Role.MEMBER)
    cards = api(pat).get("/api/timesheets/activities/").data
    days = working_days(timezone.localdate(), 5)
    TimeEntry.objects.create(user=pat, issue_id=cards[2]["id"], work_date=days[-1], duration=timedelta(hours=2))
    TimeEntry.objects.create(user=pat, work_date=days[-1], duration=timedelta(hours=4))
    TimeEntry.objects.create(user=pat, work_date=days[-2], duration=timedelta(hours=8))
    mine = api(pat).get("/api/timesheets/efficiency/", {"days": 5}).data
    assert mine["target"] == 7.5 and [d["date"] for d in mine["days"]] == [d.isoformat() for d in days]
    last = mine["days"][-1]
    assert (last["logged"], last["jobs"], last["training"], last["expected"], last["under"]) == (6.0, 4.0, 2.0, 7.5, True)
    assert mine["days"][-2]["under"] is False
    s = mine["summary"]
    assert (s["logged"], s["expected"], s["jobs"], s["non_job"], s["days_under"]) == (14.0, 37.5, 12.0, 2.0, 4)
    assert s["efficiency_pct"] == 37 and s["on_jobs_pct"] == 86
    # A lead sees the people they lead; nobody else's.
    assert api(lee).get("/api/timesheets/efficiency/", {"user": pat.id}).status_code == 200
    assert api(eve).get("/api/timesheets/efficiency/", {"user": pat.id}).status_code == 403
    team_view = api(lee).get("/api/timesheets/efficiency/", {"team": 1, "days": 5}).data
    assert [p["user"]["name"] for p in team_view["people"]] == ["Pat"]
