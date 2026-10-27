"""A task's standard sub-tasks (AFIT, 27 Oct 2026): Pre-check 3 days from the start, Preparation 5
working days later, Internal Review 1 working day after that, Client Review once the client advises;
and the task's due date may not be before its internal review."""
from datetime import date

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db
MON = "2026-11-02"  # a week with no public holiday


@pytest.fixture
def api():
    user = User.objects.create_user(username="lead", email="lead@example.com", password="x", is_staff=True)
    project = Project.objects.create(organization=Organization.get_solo(), key="RWCA", name="RWCA", lead=user)
    provision_project_defaults(project)
    IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    c = APIClient()
    c.force_authenticate(user)
    return c


def create(api, **extra):
    task = IssueType.objects.get(name="Task")
    return api.post("/api/issues/", {"project": "RWCA", "summary": "Smith FY26", "issue_type_id": task.id, **extra}, format="json")


def test_the_standard_sub_tasks_are_added_with_their_dates(api):
    r = create(api, start_date=MON, default_subtasks=True)
    assert r.status_code == 201, r.data
    subs = {s.summary: s for s in Issue.objects.get(key=r.data["key"]).subtasks.all()}
    assert list(subs) == ["Pre-check", "Preparation", "Internal Review", "Client Review"]
    assert subs["Pre-check"].due_date == date(2026, 11, 5)  # 3 working days from Monday
    assert subs["Preparation"].due_date == date(2026, 11, 12)  # 5 working days later
    assert subs["Internal Review"].due_date == date(2026, 11, 13)  # the next working day
    assert subs["Client Review"].due_date is None  # once the client has advised
    assert all(s.issue_type.is_subtask and s.status_id == subs["Pre-check"].status_id for s in subs.values())
    assert r.data["due_date"] == "2026-11-13"  # no due date given: the internal review's


def test_working_days_skip_the_weekend_and_public_holidays(api):
    r = create(api, start_date="2026-10-21", default_subtasks=True)  # Wednesday; Labour Day is Monday 26 Oct
    subs = {s.summary: s.due_date for s in Issue.objects.get(key=r.data["key"]).subtasks.all()}
    assert subs["Pre-check"] == date(2026, 10, 27)  # Thu, Fri, (weekend, Labour Day), Tue


def test_without_asking_no_sub_tasks_are_added(api):
    r = create(api)
    assert r.status_code == 201 and Issue.objects.get(key=r.data["key"]).subtasks.count() == 0


def test_the_due_date_cannot_be_before_the_internal_review(api):
    early = create(api, start_date=MON, default_subtasks=True, due_date="2026-11-10")
    assert early.status_code == 400 and "before the internal review (Fri 13 Nov 2026)" in str(early.data["due_date"])
    ok = create(api, start_date=MON, default_subtasks=True, due_date="2026-11-20")
    assert ok.status_code == 201 and ok.data["due_date"] == "2026-11-20"
    key = ok.data["key"]
    assert api.patch(f"/api/issues/{key}/", {"due_date": "2026-11-12"}, format="json").status_code == 400
    assert api.patch(f"/api/issues/{key}/", {"due_date": "2026-11-13"}, format="json").status_code == 200  # the same day is fine
    review = Issue.objects.get(key=key).subtasks.get(summary="Internal Review")
    moved = api.patch(f"/api/issues/{review.key}/", {"due_date": "2026-11-16"}, format="json")
    assert moved.status_code == 400 and "can't be after the task's due date (Fri 13 Nov 2026)" in str(moved.data["due_date"])


def test_the_form_can_preview_the_dates(api):
    r = api.get(f"/api/issues/stage-dates/?start={MON}")
    assert r.status_code == 200
    assert [(s["name"], str(s["due_date"])) for s in r.data["stages"]] == [
        ("Pre-check", "2026-11-05"), ("Preparation", "2026-11-12"), ("Internal Review", "2026-11-13"), ("Client Review", "None")]
