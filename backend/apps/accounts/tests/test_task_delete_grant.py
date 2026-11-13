"""AFIT, 13 Nov 2026: a named person may delete tasks without being a team lead or admin."""
import pytest
from django.core.management import call_command

from apps.accounts.models import User
from apps.projects.permissions import can_delete_task

pytestmark = pytest.mark.django_db


def test_a_granted_person_may_delete_tasks_and_a_revoked_one_may_not():
    from apps.orgs.models import Organization
    from apps.projects.models import Project

    user = User.objects.create_user(username="sachini", email="sachini.n@afitconnect.com", password="pw-12345678")
    project = Project.objects.create(organization=Organization.get_solo(), name="Smith", key="SMITH", lead=User.objects.create_user(username="lead", email="lead@x.com", password="pw-12345678"))
    assert not can_delete_task(user, project)
    call_command("grant_task_delete", "Sachini.N@afitconnect.com")
    user.refresh_from_db()
    assert user.can_delete_tasks and can_delete_task(user, project)
    call_command("grant_task_delete", "sachini.n@afitconnect.com", "--revoke")
    user.refresh_from_db()
    assert not can_delete_task(user, project)
