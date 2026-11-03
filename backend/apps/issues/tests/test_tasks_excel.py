"""Tasks to Excel from the task table (AFIT, 2 Nov 2026): the keys listed, in their order, every column."""
import io
from datetime import timedelta

import pytest
from django.utils import timezone
from openpyxl import load_workbook
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.teams.models import Team
from apps.timesheets.models import TimeEntry
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db


def test_the_listed_tasks_download_as_a_workbook_in_the_tables_order():
    org = Organization.get_solo()
    amy = User.objects.create_user(username="xa", email="xa@example.com", password="x", display_name="Amy")
    team = Team.objects.create(organization=org, name="Team 1")
    client = Client.objects.create(organization=org, name="ABC Ltd", team=team)
    project = Project.objects.create(organization=org, key="ABC", name="ABC", lead=amy, primary_team=team, client=client)
    provision_project_defaults(project)
    kind, _ = IssueType.objects.get_or_create(name="Task", project=None)
    s = {x.name: x for x in project.workflow.statuses.all()}
    late = Issue.objects.create(project=project, issue_type=kind, summary="Preparation", status=s["In Progress"], reporter=amy,
                                preparer=amy, due_date=timezone.localdate() - timedelta(days=3), budgeted_hours=10)
    done = Issue.objects.create(project=project, issue_type=kind, summary="Adjustments", status=s["Complete"], reporter=amy)
    Issue.objects.create(project=project, issue_type=kind, summary="Not listed", status=s["To Start"], reporter=amy)
    TimeEntry.objects.create(user=amy, issue=late, project=project, work_date=timezone.localdate(), duration=timedelta(hours=4))

    api = APIClient()
    api.force_authenticate(amy)
    r = api.post("/api/issues/export-xlsx/", {"keys": [done.key, late.key]}, format="json")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/vnd.openxmlformats")
    wb = load_workbook(io.BytesIO(r.content))
    ws = wb["Tasks"]
    head = [c.value for c in ws[1]]
    assert head[:7] == ["Key", "Task", "Sub-workspace", "Workspace", "Project", "Status", "Priority"]
    assert ws.max_row == 3 and ws["A2"].value == done.key and ws["A3"].value == late.key
    row = dict(zip(head, [c.value for c in ws[3]]))
    assert (row["Sub-workspace"], row["Workspace"], row["Status"], row["Accountant"]) == ("ABC Ltd", "Team 1", "In Progress", "Amy")
    assert row["Days overdue"] == 3 and row["Actual (h)"] == 4 and row["Remaining (h)"] == 6
    assert ws.cell(row=3, column=13).number_format == "DD-MM-YY"
    stages = [[c.value for c in r] for r in wb["By stage"].iter_rows(min_row=4)]
    assert stages == [["In Progress", 1], ["Complete", 1], ["Total", 2]]

    assert api.post("/api/issues/export-xlsx/", {"keys": []}, format="json").status_code == 400
