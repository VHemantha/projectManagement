"""AFIT, 2 Nov 2026: the agent's follow-ups on overdue tasks go to the task's accountant, one to one in
their private conversation with the agent (not a shared channel, and not to the CEO for review); the
CEO sees what was sent, the reason given and the agent's guidance, in the console and the briefing."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.chat.models import Channel, Message
from apps.coordinator import briefing, engine, llm, services
from apps.coordinator.models import AgentCase, CoordinatorSettings
from apps.precheck.models import TaskMilestone

from .test_coordination import MON, NZ, at, texts_to, world  # noqa: F401  (the shared fixture)

pytestmark = pytest.mark.django_db
STEP = "Chase the client for the March bank statements: they block preparation."


def overdue(job):
    TaskMilestone.objects.create(issue=job, kind="precheck", on=MON, auto=True)
    job.due_date = MON - timedelta(days=1)
    job.save()


def say(person, text, capture):
    with capture(execute=True):
        Message.objects.create(channel=services.conversation_for(person), author=person,
                               body={"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]})


def test_new_installs_send_follow_ups_to_the_team_not_the_ceo():
    CoordinatorSettings.objects.all().delete()
    assert CoordinatorSettings.get().shadow_mode is False


def test_an_overdue_task_is_followed_up_with_its_accountant_one_to_one(world, monkeypatch):
    overdue(world.job)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: ({"steps": [STEP], "summary": ""}, 0.0))
    engine.tick(at(MON))
    (msg,) = texts_to(world.pat)
    assert "preparation was due Sun 01 Nov" in msg and STEP in msg
    channel = services.conversation_for(world.pat)
    assert channel.channel_type == Channel.ChannelType.DIRECT_MESSAGE
    assert set(channel.memberships.values_list("user_id", flat=True)) == {world.pat.id, services.agent_user().id}
    bot = services.agent_user()
    assert not Message.objects.filter(author=bot).exclude(channel__channel_type=Channel.ChannelType.DIRECT_MESSAGE).exists()
    assert not any("Shadow mode" in t or "preparation was due" in t for t in texts_to(world.ceo))  # not sent to the CEO instead


def test_the_ceo_sees_what_was_sent_the_reason_and_the_guidance(world, monkeypatch, django_capture_on_commit_callbacks):
    overdue(world.job)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: ({"steps": [STEP], "summary": ""}, 0.0))
    engine.tick(at(MON))
    today = timezone.localtime(timezone.now(), NZ).date()
    eta = today + timedelta(days=3)

    def reply(system, messages, schema, **kw):
        return {"reply": "Thanks Pat. Send the client the request list from the pre-check today and log the time you spend chasing.",
                "updates": [{"job_key": world.job.key, "remaining_hours": 4, "eta_date": eta.isoformat(), "percent_complete": -1,
                             "cause": "client_documents", "blockers": "March bank statements not received", "needs_help": False}]}, 0.0

    monkeypatch.setattr(llm, "structured", reply)
    say(world.pat, "Still waiting on the March bank statements from the client.", django_capture_on_commit_callbacks)

    client = APIClient()
    client.force_authenticate(world.ceo)
    (case,) = client.get("/api/coordinator/cases/").data["cases"]
    kinds = [h["kind"] for h in case["history"]]
    assert kinds == ["asked", "reason", "guidance"]
    asked, reason, guidance = case["history"]
    assert asked["to"] == "Pat" and asked["delivered"] and not asked["shadow"] and asked["advice"] == [STEP]
    assert "preparation was due" in asked["text"]
    assert reason["text"] == "Still waiting on the March bank statements from the client."
    assert reason["cause"] == "Waiting for client documents" and reason["blockers"] == "March bank statements not received"
    assert guidance["text"].startswith("Thanks Pat. Send the client the request list") and "Noted for" not in guidance["text"]
    assert case["commitment"]["blockers"] == "March bank statements not received"

    monkeypatch.setattr(llm, "structured", lambda *a, **k: ({"summary": "Pat is waiting on the client."}, 0.0))
    text, _ = briefing.compose(briefing.facts(today))
    assert "My guidance: Thanks Pat. Send the client the request list" in text


def test_turning_shadow_mode_off_starts_the_follow_ups_with_the_accountant(world):
    world.settings.shadow_mode = True
    world.settings.save()
    overdue(world.job)
    day = MON
    engine.tick(at(day))
    for _ in range(3):  # in shadow: counted as asked twice more, then "escalated", but nobody was told
        day += timedelta(days=1)
        engine.tick(at(day, 10, 30))
    case = AgentCase.objects.get(issue=world.job, kind="prep_overdue")
    assert case.state == "escalated" and texts_to(world.pat) == [] and texts_to(world.lee) == []

    client = APIClient()
    client.force_authenticate(world.ceo)
    assert client.patch("/api/coordinator/settings/", {"shadow_mode": False}, format="json").status_code == 200
    case.refresh_from_db()
    assert (case.state, case.asked, case.escalated_to) == ("asked", 0, None)
    engine.tick(at(day + timedelta(days=1), 10, 45))
    (msg,) = texts_to(world.pat)
    assert msg.startswith("Hi Pat.") and "Following up" not in msg
    assert texts_to(world.lee) == []
