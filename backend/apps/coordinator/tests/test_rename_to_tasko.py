"""AFIT, 3 Nov 2026: the app is called TASKO; the live organisation and the coordinator's account follow."""
from importlib import import_module

import pytest
from django.apps import apps

from apps.accounts.models import User
from apps.coordinator import services
from apps.orgs.models import Organization

pytestmark = pytest.mark.django_db
rename = import_module("apps.coordinator.migrations.0006_rename_to_tasko").rename_to_tasko


def test_the_live_organisation_and_the_coordinator_take_the_new_name():
    Organization.objects.update_or_create(slug="default", defaults={"name": "Loca"})
    old = User.objects.create(email="coordinator@loca.internal", username="loca-coordinator", display_name="Loca Coordinator", is_agent=True)
    rename(apps, None)
    old.refresh_from_db()
    assert Organization.get_solo().name == "TASKO"
    assert (old.email, old.username, old.display_name) == ("coordinator@tasko.internal", "tasko-coordinator", "TASKO Coordinator")
    assert services.agent_user() == old  # the same account, so every conversation with it is kept


def test_an_organisation_renamed_by_the_firm_keeps_its_name():
    Organization.objects.update_or_create(slug="default", defaults={"name": "AFIT Connect"})
    rename(apps, None)
    assert Organization.get_solo().name == "AFIT Connect"
