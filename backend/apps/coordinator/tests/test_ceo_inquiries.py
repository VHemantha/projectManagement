"""AFIT, 12 Nov 2026: when the CEO asks the TASKO Coordinator to chat with someone and find out the
reasons, or to guide them, the agent really sends the questions (it never only says it will), guides
the person from what the CEO said and what it knows, and reports what it found back to the CEO."""
from datetime import timedelta

import pytest

from apps.coordinator import engine, inquiries, llm
from apps.coordinator.models import AgentCase, Inquiry
from apps.precheck.models import AssistantQuestion, PrecheckLesson

from .test_coordination import MON, at, texts_to, world  # noqa: F401  (the shared fixture)
from .test_direct_followups import say

pytestmark = pytest.mark.django_db
QUESTIONS = ["What is holding up preparation of SMITH-1?", "When do you expect to finish it?"]


def ceo_answer(world, **contact):
    c = {"person_id": world.pat.pk, "job_key": world.job.key, "purpose": "Why SMITH-1 is behind and when it will be done.",
         "questions": QUESTIONS, "note_for_person": "", "ceo_guidance": "Agree a date with the client for the bank statements.", **contact}
    return {"reply": "I'll ask Pat and report back here.", "updates": [], "contact": [c]}


def test_the_ceo_asks_and_the_questions_really_go_to_the_person(world, monkeypatch, django_capture_on_commit_callbacks):
    seen = {}

    def model(system, messages, schema, **kw):
        seen.update(system=system, context=messages[0]["content"], schema=schema)
        return ceo_answer(world), 0.01

    monkeypatch.setattr(llm, "structured", model)
    say(world.ceo, "Chat with Pat and find out why the Smith job is late.", django_capture_on_commit_callbacks)

    assert "contact" in seen["schema"]["properties"] and "contact" in seen["schema"]["required"]
    assert f"{world.pat.pk}: Pat" in seen["context"]  # the CEO's agent knows who it can message
    (to_pat,) = texts_to(world.pat)
    assert to_pat.startswith("Hi Pat. Dushan has asked me to check in with you about") and world.job.key in to_pat
    assert all(q in to_pat for q in QUESTIONS)
    (to_ceo,) = texts_to(world.ceo)
    assert "I'll ask Pat" in to_ceo and f"I've messaged Pat about {world.job.key} and asked:" in to_ceo and QUESTIONS[0] in to_ceo
    (q,) = Inquiry.objects.all()
    assert q.person == world.pat and q.issue == world.job and q.requested_by == world.ceo and q.state == Inquiry.State.ASKING
    assert q.request == "Chat with Pat and find out why the Smith job is late."


def test_it_goes_even_in_shadow_mode_because_the_ceo_asked(world, monkeypatch, django_capture_on_commit_callbacks):
    world.settings.shadow_mode = True
    world.settings.save()
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (ceo_answer(world), 0.0))
    say(world.ceo, "Ask Pat about Smith.", django_capture_on_commit_callbacks)
    assert len(texts_to(world.pat)) == 1


def test_nobody_is_claimed_messaged_without_a_real_person(world, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (ceo_answer(world, person_id=999999), 0.0))
    say(world.ceo, "Ask Sam about Smith.", django_capture_on_commit_callbacks)
    (to_ceo,) = texts_to(world.ceo)
    assert "I couldn't tell who to message" in to_ceo and "I've messaged" not in to_ceo
    assert not Inquiry.objects.exists()


def test_staff_cannot_send_the_agent_to_message_others(world, monkeypatch, django_capture_on_commit_callbacks):
    seen = {}

    def model(system, messages, schema, **kw):
        seen["schema"] = schema
        return {"reply": "I can only talk about your own jobs.", "updates": [], "contact": [{"person_id": world.lee.pk}]}, 0.0

    monkeypatch.setattr(llm, "structured", model)
    say(world.pat, "Tell Lee to do my review.", django_capture_on_commit_callbacks)
    assert "contact" not in seen["schema"]["properties"]
    assert texts_to(world.lee) == [] and not Inquiry.objects.exists()


def test_the_reply_is_guided_from_the_ceo_and_the_knowledge_base_and_reported_back(world, monkeypatch, django_capture_on_commit_callbacks):
    AssistantQuestion.objects.create(question_id="q1", issue=world.job, question="Is interest deductible?", status="answered",
                                     answer="Yes, from 1 April 2025.")
    PrecheckLesson.objects.create(client_scope="Smith", issue=world.job, note="Smith always sends statements late: chase in week one.")
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (ceo_answer(world), 0.0))
    say(world.ceo, "Find out from Pat why Smith is late, and guide them.", django_capture_on_commit_callbacks)
    q = Inquiry.objects.get()
    seen = {}

    def model(system, messages, schema, **kw):
        seen.update(system=system, context=messages[0]["content"], schema=schema)
        return {"reply": "Thanks Pat. Dushan would like you to agree a date with the client for the statements; chase them today.",
                "updates": [], "inquiries": [{"inquiry_id": q.pk, "findings": "Waiting on the March bank statements; can finish 2 days after.",
                                              "complete": True,
                                              "report_to_ceo": "The delay is the client's missing March statements. I advised Pat to agree a date. "
                                                               "Recommendation: a call from you to the client may speed it up."}]}, 0.0

    monkeypatch.setattr(llm, "structured", model)
    say(world.pat, "I'm still waiting for the March bank statements; I'll be done two days after they arrive.", django_capture_on_commit_callbacks)

    assert "THE CEO ASKED YOU TO FIND OUT" in seen["context"] and "Agree a date with the client" in seen["context"]
    assert "Yes, from 1 April 2025." in seen["context"] and "chase in week one" in seen["context"]  # the knowledge base
    assert "inquiries" in seen["schema"]["required"] and "guide them" in seen["system"]
    assert texts_to(world.pat)[-1].startswith("Thanks Pat. Dushan would like you to agree a date")
    report = texts_to(world.ceo)[-1]
    assert report.startswith(f"Pat replied on {world.job.key}. You asked: Why SMITH-1 is behind")
    assert "– Waiting on the March bank statements" in report and "Recommendation: a call from you" in report
    assert "What I told Pat: Thanks Pat. Dushan would like you" in report
    q.refresh_from_db()
    assert q.state == Inquiry.State.REPORTED and q.rounds == 1 and " ".join(q.report.split()) == report

    # Asked later, the CEO's agent knows what came of it.
    monkeypatch.setattr(llm, "structured", lambda s, m, sc, **k: (seen.update(ceo=m[0]["content"]) or {"reply": "ok", "updates": [], "contact": []}, 0.0))
    say(world.ceo, "What did Pat say?", django_capture_on_commit_callbacks)
    assert "They said: Waiting on the March bank statements" in seen["ceo"]


def test_an_unanswered_question_is_asked_again_before_reporting(world, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (ceo_answer(world), 0.0))
    say(world.ceo, "Ask Pat about Smith.", django_capture_on_commit_callbacks)
    q = Inquiry.objects.get()
    partial = {"reply": "Thanks. And when do you expect to finish it?", "updates": [],
               "inquiries": [{"inquiry_id": q.pk, "findings": "Waiting on the client.", "complete": False, "report_to_ceo": ""}]}
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (partial, 0.0))
    say(world.pat, "Waiting on the client.", django_capture_on_commit_callbacks)
    q.refresh_from_db()
    assert q.state == Inquiry.State.ASKING and q.findings[0]["text"] == "Waiting on the client."
    assert not any("replied" in t for t in texts_to(world.ceo))


def test_without_the_model_their_own_words_are_reported(world, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (ceo_answer(world), 0.0))
    say(world.ceo, "Ask Pat about Smith.", django_capture_on_commit_callbacks)

    def down(*a, **k):
        raise llm.Unavailable("no key")

    monkeypatch.setattr(llm, "structured", down)
    say(world.pat, "The client hasn't sent the statements.", django_capture_on_commit_callbacks)
    assert "– The client hasn't sent the statements." in texts_to(world.ceo)[-1]
    assert Inquiry.objects.get().state == Inquiry.State.REPORTED


def test_no_reply_gets_one_reminder_then_the_ceo_is_told(world, monkeypatch, django_capture_on_commit_callbacks):
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (ceo_answer(world), 0.0))
    say(world.ceo, "Ask Pat about Smith.", django_capture_on_commit_callbacks)
    q = Inquiry.objects.get()
    q.last_asked_at = at(MON, 9)
    q.save()
    AgentCase.objects.all().delete()
    later = at(MON + timedelta(days=2), 10)
    assert inquiries.chase(later) == {"reminded": 1, "no_reply": 0}
    assert texts_to(world.pat)[-1].startswith("Hi Pat, just following up on Dushan's questions about")
    assert inquiries.chase(later + timedelta(hours=1)) == {"reminded": 0, "no_reply": 0}  # within the window
    assert inquiries.chase(later + timedelta(days=2)) == {"reminded": 0, "no_reply": 1}
    assert "Pat hasn't replied to your questions" in texts_to(world.ceo)[-1]
    assert Inquiry.objects.get().state == Inquiry.State.NO_REPLY
    engine.tick(at(MON + timedelta(days=6), 10))  # the tick runs the chase without error
