"""Cards show the deadline, stage and priority on every board; time logged and story points are gone
(AFIT, 28 Oct 2026)."""
from importlib import import_module

import pytest
from django.apps import apps as django_apps

from apps.accounts.models import User
from apps.orgs.models import Organization
from apps.projects.models import Project
from apps.workflow.models import Board
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db
migration = import_module("apps.workflow.migrations.0009_cards_deadline_stage_priority")


def test_existing_boards_lose_the_removed_and_now_built_in_fields():
    lead = User.objects.create_user(username="lead", email="lead@example.com", password="x")
    project = Project.objects.create(organization=Organization.get_solo(), key="RWCA", name="RWCA", lead=lead)
    provision_project_defaults(project)
    board = project.boards.first()
    board.card_fields = ["epic_tag", "story_points", "priority", "assignee", "due_date", "labels", "job_value", "time_logged"]
    board.save()
    migration.tidy_card_fields(django_apps, None)
    board.refresh_from_db()
    assert board.card_fields == ["epic_tag", "assignee", "labels", "job_value"]


def test_the_value_comes_off_every_card():
    """AFIT, 28 Oct 2026: the task's value is no longer shown on cards."""
    lead = User.objects.create_user(username="lead", email="lead@example.com", password="x")
    project = Project.objects.create(organization=Organization.get_solo(), key="RWCA", name="RWCA", lead=lead)
    provision_project_defaults(project)
    board = project.boards.first()
    board.card_fields = ["epic_tag", "job_value", "assignee"]
    board.save()
    import_module("apps.workflow.migrations.0010_cards_without_value").remove_value(django_apps, None)
    board.refresh_from_db()
    assert board.card_fields == ["epic_tag", "assignee"]


def test_new_boards_have_no_story_points_or_time():
    assert Board._meta.get_field("card_fields").default() == ["epic_tag", "assignee"]


def test_boards_lose_their_swimlanes():
    lead = User.objects.create_user(username="lead", email="lead@example.com", password="x")
    project = Project.objects.create(organization=Organization.get_solo(), key="RWCA", name="RWCA", lead=lead)
    provision_project_defaults(project)
    project.boards.update(swimlane_mode="epic")
    import_module("apps.workflow.migrations.0011_boards_without_swimlanes").no_swimlanes(django_apps, None)
    assert set(Board.objects.values_list("swimlane_mode", flat=True)) == {"none"}
