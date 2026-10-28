"""Deleting a task from its card (AFIT, 28 Oct 2026): permanent, with its sub-tasks; team lead and above."""
from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team, TeamMembership
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    org = Organization.get_solo()
    owner = User.objects.create_user(username="owner", email="owner@example.com", password="x")
    lead = User.objects.create_user(username="lead", email="lead@example.com", password="x")
    staff = User.objects.create_user(username="staff", email="staff@example.com", password="x")
    team = Team.objects.create(organization=org, name="Team 1")
    TeamMembership.objects.create(team=team, user=lead, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=team, user=staff)
    project = Project.objects.create(organization=org, key="RWCA", name="RWCA", lead=owner, primary_team=team)
    provision_project_defaults(project)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    sub, _ = IssueType.objects.get_or_create(name="Sub-task", project=None, defaults={"is_subtask": True})
    status = project.workflow.statuses.order_by("order").first()
    parent = Issue.objects.create(project=project, issue_type=task, summary="Smith FY26", status=status, reporter=owner)
    Issue.objects.create(project=project, issue_type=sub, summary="Pre-check", status=status, reporter=owner, parent=parent)
    TimeEntry.objects.create(user=staff, issue=parent, project=project, work_date="2026-10-27", duration=timedelta(hours=2))
    return {"lead": lead, "staff": staff, "parent": parent}


def client(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


def test_a_team_lead_deletes_a_task_and_its_sub_tasks_but_logged_hours_stay(world):
    r = client(world["lead"]).delete(f"/api/issues/{world['parent'].key}/")
    assert r.status_code == 204
    assert not Issue.objects.exists()
    entry = TimeEntry.objects.get()
    assert entry.issue_id is None and entry.duration == timedelta(hours=2)


def test_others_cannot_delete(world):
    r = client(world["staff"]).delete(f"/api/issues/{world['parent'].key}/")
    assert r.status_code == 403 and "team lead or above" in r.data["detail"]
    assert Issue.objects.filter(pk=world["parent"].pk).exists()


def test_cards_know_whether_the_viewer_may_delete(world):
    for user, expected in ((world["lead"], True), (world["staff"], False)):
        rows = client(user).get("/api/issues/?project=RWCA&no_parent=true").data["results"]
        assert [r["can_delete"] for r in rows] == [expected]
