"""Every board becomes AFIT's eight stages (migration 0007): old statuses are renamed or merged with
their tasks moved, missing stages added, the board's columns rewritten, the reassignment rules
replaced, and new projects start with the eight."""
import importlib

import pytest
from django.apps import apps as django_apps

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import Board, IssueType, Workflow, WorkflowStatus, WorkflowTransition
from apps.workflow.services import STATUS_DEFS, provision_project_defaults

pytestmark = pytest.mark.django_db
STAGES = ["To Start", "In Progress", "Waiting for Info", "Sent to Client", "Internal Adjustments", "Client Adjustments", "Complete", "To be Archived"]
migration = importlib.import_module("apps.workflow.migrations.0007_afit_stage_columns")


def old_project(key, lead, names_categories, columns=None):
    project = Project.objects.create(organization=Organization.get_solo(), key=key, name=key, lead=lead)
    wf = Workflow.objects.create(project=project)
    statuses = {n: WorkflowStatus.objects.create(workflow=wf, name=n, category=c, order=i) for i, (n, c) in enumerate(names_categories)}
    Board.objects.create(project=project, name=f"{key} Board", board_type="kanban",
                         column_config=[{"name": n, "status_ids": [s.id], "wip_limit": 5 if n == "In progress" else None,
                                         **({"color": "#aa0000"} if n == "Blocked" else {})} for n, s in statuses.items()]
                         if columns is None else columns(statuses))
    return project, wf, statuses


def task(project, status, user, summary):
    t, _ = IssueType.objects.get_or_create(name="Task", project=None, defaults={"is_subtask": False})
    return Issue.objects.create(project=project, issue_type=t, summary=summary, status=status, reporter=user)


def test_the_standard_board_becomes_the_eight_stages_and_no_task_is_lost():
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    project, wf, s = old_project("STD", user, [("Backlog", "todo"), ("To do", "todo"), ("In progress", "in_progress"),
                                               ("In review", "in_progress"), ("Blocked", "in_progress"), ("Done", "done")])
    a, b, c, d = (task(project, s["Backlog"], user, "A"), task(project, s["To do"], user, "B"), task(project, s["In progress"], user, "C"),
                  task(project, s["Done"], user, "D"))
    WorkflowTransition.objects.create(workflow=wf, name="Send for review", from_status=s["In progress"], to_status=s["In review"],
                                      set_current_responsible_to="reviewer")
    custom = WorkflowTransition.objects.create(workflow=wf, name="Escalate", from_status=s["Blocked"], to_status=s["In review"],
                                               set_current_responsible_to="reviewer")

    migration.convert(django_apps, None)
    migration.convert(django_apps, None)  # safe to run again

    statuses = list(WorkflowStatus.objects.filter(workflow=wf).order_by("order"))
    assert [(x.name, x.category) for x in statuses] == [(n, c) for n, c in migration.STAGES]
    by_name = {x.name: x for x in statuses}
    for t, stage in ((a, "To Start"), (b, "To Start"), (c, "In Progress"), (d, "Complete")):
        t.refresh_from_db()
        assert t.status_id == by_name[stage].id
    d.refresh_from_db()
    assert d.resolved_at is not None
    board = Board.objects.get(project=project)
    assert [col["name"] for col in board.column_config] == STAGES
    assert [col["status_ids"] for col in board.column_config] == [[by_name[n].id] for n in STAGES]
    assert board.column_config[1]["wip_limit"] == 5
    rules = {(r.name, r.from_status.name if r.from_status else None, r.to_status.name, r.set_current_responsible_to)
             for r in WorkflowTransition.objects.filter(workflow=wf)}
    assert ("Escalate", "Waiting for Info", "Internal Adjustments", "reviewer") in rules  # a custom rule follows its stages
    assert not any(r[0] == "Send for review" for r in rules)  # the old defaults are gone
    assert ("Internal adjustments", None, "Internal Adjustments", "preparer") in rules
    custom.refresh_from_db()
    assert Issue.objects.filter(project=project).count() == 4


def test_a_custom_afit_board_is_mapped_stage_by_stage():
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    names = [("Not Scheduled", "todo"), ("To Start", "todo"), ("Prep in Progress", "in_progress"), ("Waiting for Info", "in_progress"),
             ("Finalising - Internal Review", "in_progress"), ("Sent to Client", "in_progress"), ("Adjustments in Progress", "in_progress"),
             ("Complete", "in_progress"), ("To be Archived", "in_progress")]
    project, wf, s = old_project("AFIT", user, names)
    adj = task(project, s["Adjustments in Progress"], user, "Adjusting")
    waiting_id = s["Waiting for Info"].id
    migration.convert(django_apps, None)
    by_name = {x.name: x for x in WorkflowStatus.objects.filter(workflow=wf)}
    assert sorted(by_name) == sorted(STAGES)
    assert by_name["Waiting for Info"].id == waiting_id  # an exact match is kept as it is
    assert by_name["Complete"].category == by_name["To be Archived"].category == "done"
    adj.refresh_from_db()
    assert adj.status.name == "Internal Adjustments"


def test_new_projects_start_with_the_eight_stages():
    user = User.objects.create_user(username="u", email="u@example.com", password="x")
    project = Project.objects.create(organization=Organization.get_solo(), key="NEW", name="New", lead=user)
    board = provision_project_defaults(project)
    assert [c["name"] for c in board.column_config] == STAGES == [n for n, _c, _w in STATUS_DEFS]
    assert WorkflowTransition.objects.filter(workflow=project.workflow, to_status__name="Client Adjustments",
                                             set_current_responsible_to="preparer").exists()
