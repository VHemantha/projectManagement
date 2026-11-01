"""AFIT, 31 Oct 2026: the agent advises the accountant from what it knows of the job when a task is due,
nearly due or overdue, and when they give a reason; the reasons reach the CEO's briefing; and the
agent keeps each person's KPIs and rates them by a formula, reported to the CEO only."""
from datetime import date, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.coordinator import advice, briefing, engine, kpi, llm, policies, ratings_report
from apps.coordinator.models import AgentAction, AgentCase, Commitment, KpiSnapshot
from apps.issues.models import Issue, IssueHistory
from apps.precheck.models import AIPrecheck, DirectionItem, TaskMilestone
from apps.timesheets.models import TimeEntry

from .test_coordination import MON, at, texts_to, world  # noqa: F401  (the shared fixture)

pytestmark = pytest.mark.django_db


def precheck_with_requests(job):
    AIPrecheck.objects.create(issue=job, run_id=f"run-{job.pk}", kind="precheck", status="complete", precheck={
        "decision": {"label": "Requests to send"}, "business_nature": {"label": "Residential rental"},
        "requests": [{"item": "Bank statements March", "priority": "blocking"}, {"item": "Rates invoice", "priority": "normal"}],
        "preparer_notes": [{"text": "Interest is fully deductible from 1 April 2025."}]})


def test_the_job_knowledge_is_read_from_its_records(world):
    precheck_with_requests(world.job)
    DirectionItem.objects.create(issue=world.job, text="Check the mortgage split with the client.")
    lines = "\n".join(advice.job_knowledge(world.job))
    assert "Still to come from the client: Bank statements March (blocks preparation); Rates invoice" in lines
    assert "Interest is fully deductible" in lines and "Check the mortgage split" in lines


def test_a_due_task_message_carries_advice_from_the_job(world, monkeypatch):
    precheck_with_requests(world.job)
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON + timedelta(days=4)  # Friday: preparation due
    world.job.save()
    seen = {}

    def fake(system, messages, schema, **kw):
        if "Why the agent is asking" not in messages[-1]["content"]:
            return {"summary": ""}, 0.0  # the CEO's briefing, in the same round
        seen["facts"] = messages[-1]["content"]
        return {"steps":["Chase the client for the March bank statements: they block preparation."]}, 0.001
    monkeypatch.setattr(llm, "structured", fake)
    engine.tick(at(MON + timedelta(days=2)))
    (msg,) = texts_to(world.pat)
    assert "preparation is due Fri 06 Nov" in msg
    assert "Suggested next steps: – Chase the client for the March bank statements: they block preparation." in msg
    assert "Bank statements March (blocks preparation)" in seen["facts"]
    assert AgentAction.objects.get(trigger="prep_due").cost_usd == 0.001


def test_without_the_model_the_advice_is_written_by_code(world, monkeypatch):
    precheck_with_requests(world.job)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (_ for _ in ()).throw(llm.Unavailable("no key")))
    steps, cost = advice.steps_for(world.job, "Preparation overdue")
    assert cost == 0 and steps[0] == "Chase the client for Bank statements March: these block preparation."
    Issue.objects.filter(pk=world.job.pk).update(budgeted_hours=1)
    TimeEntry.objects.create(user=world.pat, issue=world.job, project=world.job.project, work_date=MON, duration=timedelta(hours=3))
    assert any("past the budget" in s for s in advice.steps_for(Issue.objects.get(pk=world.job.pk), "")[0])


def test_the_reasons_given_reach_the_ceos_briefing(world):
    c = Commitment.objects.create(person=world.pat, issue=world.job, cause="client_documents", blockers="March statements", eta_date=MON + timedelta(days=7))
    Commitment.objects.filter(pk=c.pk).update(created_at=at(MON, 15))  # given on Monday afternoon
    text, _ = briefing.compose(briefing.facts(MON + timedelta(days=1)))
    assert "Reasons given since the last working day (1):" in text
    assert "SmithRent-1 — Pat: waiting for client documents — March statements; new date 09 Nov" in text


# --- ratings -------------------------------------------------------------------------------------

def finished_task(world, summary, due, done_on, budget=None, hours=0.0, reworked=False):
    t = Issue.objects.create(project=world.job.project, issue_type=world.job.issue_type, summary=summary, reporter=world.pat,
                             preparer=world.pat, status=world.job.project.workflow.statuses.get(name="Complete"), due_date=due,
                             budgeted_hours=budget, start_date=done_on - timedelta(days=10))
    Issue.objects.filter(pk=t.pk).update(resolved_at=at(done_on, 12))  # noon, New Zealand time
    if hours:
        TimeEntry.objects.create(user=world.pat, issue=t, project=t.project, work_date=done_on, duration=timedelta(hours=hours))
    if reworked:
        IssueHistory.objects.create(issue=t, user=world.lee, field_changed="status", old_value="In Progress", new_value="Internal Adjustments")
    return Issue.objects.get(pk=t.pk)


def test_the_rating_formula(world):
    end = MON + timedelta(days=30)
    d = MON + timedelta(days=10)
    finished_task(world, "A", due=d, done_on=d, budget=10, hours=8)  # on time, within budget
    finished_task(world, "B", due=d, done_on=d + timedelta(days=2), budget=10, hours=14, reworked=True)  # late, over 125%, reworked
    finished_task(world, "C", due=d, done_on=d - timedelta(days=1), budget=10, hours=12.5)  # on time, exactly the tolerance
    finished_task(world, "D", due=d, done_on=d)
    for i, status in enumerate(["kept", "kept", "missed"]):
        c = Commitment.objects.create(person=world.pat, issue=world.job, eta_date=d + timedelta(days=i), status=status, cause="workload")
        Commitment.objects.filter(pk=c.pk).update(created_at=at(d))
    r = kpi.rate(world.pat, MON, end)
    m = {x["key"]: x for x in r["metrics"]}
    assert (m["on_time"]["score"], m["on_time"]["detail"]) == (75.0, "3 of 4 finished tasks by their due date")
    assert (m["budget"]["score"], m["budget"]["n"]) == (round(2 / 3 * 100, 1), 3)
    assert m["quality"]["score"] == 75.0 and m["promises"]["score"] == round(2 / 3 * 100, 1)
    assert not m["response"]["counted"] and m["response"]["note"] == "Not counted: fewer than 3 to go on"
    counted = [x for x in r["metrics"] if x["counted"]]
    expected = round(sum(x["weight"] * x["score"] for x in counted) / sum(x["weight"] for x in counted), 1)
    assert r["score"] == expected and r["rating"] == kpi.band(expected)
    assert r["reasons"] == {"Other work": 3}


def test_the_weights_are_the_ceos_rules(world):
    d = MON + timedelta(days=10)
    for name in "ABC":
        finished_task(world, name, due=d, done_on=d)
    for key in ("precheck", "promises", "response", "budget", "quality", "timesheet"):
        policies.set_rule(f"kpi_weight_{key}", 0, user=world.ceo)
    r = kpi.rate(world.pat, MON, MON + timedelta(days=30))
    assert r["score"] == 100.0 and r["rating"] == "Excellent"  # only "on time" counts now
    assert kpi.band(84.9) == "Good" and kpi.band(55) == "Needs improvement" and kpi.band(54.9) == "At risk" and kpi.band(None) == "Not enough data"


def test_too_little_data_is_said_plainly(world):
    r = kpi.rate(world.pat, MON, MON + timedelta(days=5))
    assert r["rating"] == "Not enough data"


def test_the_ceo_alone_sees_the_ratings(world):
    d = MON + timedelta(days=10)
    for name in "ABC":
        finished_task(world, name, due=d, done_on=d)
    ceo, staff = APIClient(), APIClient()
    ceo.force_authenticate(world.ceo)
    staff.force_authenticate(world.lee)
    assert staff.get("/api/coordinator/ratings/").status_code == 403
    r = ceo.get("/api/coordinator/ratings/?days=365")
    assert r.status_code == 200
    assert [p["person"]["display_name"] for p in r.data["people"]] == ["Pat"]  # the CEO is not rated
    assert [w["key"] for w in r.data["formula"]["weights"]] == ["on_time", "precheck", "promises", "response", "budget", "quality", "timesheet"]
    assert ceo.get("/api/coordinator/ratings/?days=5").status_code == 400


def test_the_weekly_ratings_go_to_the_ceo_only_and_are_kept(world, monkeypatch):
    monkeypatch.setattr(llm, "structured", lambda *a, **k: ({"summary": "Pat is steady."}, 0.002))
    KpiSnapshot.objects.create(person=world.pat, period_start=MON - timedelta(days=97), period_end=MON - timedelta(days=7), score=60, rating="Needs improvement")
    for name in "ABC":
        finished_task(world, name, due=MON - timedelta(days=3), done_on=MON - timedelta(days=4))
    assert not ratings_report.send_if_due(at(MON, 8, 0))  # before the report time
    assert ratings_report.send_if_due(at(MON, 9, 0))
    assert not ratings_report.send_if_due(at(MON, 11, 0))  # once a week
    assert not ratings_report.send_if_due(at(MON + timedelta(days=1), 9, 0))  # Monday only
    (note,) = [t for t in texts_to(world.ceo) if t.startswith("Your weekly ratings")]
    assert "(only you see these)" in note and "Pat is steady." in note and "1. Pat — " in note and "since last week" in note
    assert not [t for t in texts_to(world.pat) + texts_to(world.lee) if "ratings" in t.lower()]
    assert KpiSnapshot.objects.filter(person=world.pat, period_end=MON).exists()


def test_a_reason_given_in_reply_is_answered_with_advice_from_the_job(world, monkeypatch, django_capture_on_commit_callbacks):
    from apps.chat.models import Message
    from apps.coordinator import services

    precheck_with_requests(world.job)
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON + timedelta(days=3)
    world.job.save()
    monkeypatch.setattr(llm, "structured", lambda *a, **k: (_ for _ in ()).throw(llm.Unavailable("no key")))
    engine.tick(at(MON + timedelta(days=2)))  # the agent asks about the job (opens the case)
    seen = {}

    def fake(system, messages, schema, **kw):
        seen["system"], seen["context"] = system, messages[0]["content"]
        return {"reply": "Thanks Pat. Chase the client for the March bank statements first: they block preparation.", "updates": []}, 0.003

    monkeypatch.setattr(llm, "structured", fake)
    with django_capture_on_commit_callbacks(execute=True):
        Message.objects.create(channel=services.conversation_for(world.pat), author=world.pat, body={"type": "doc", "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "I'm waiting on the client's documents."}]}]})
    assert "advise them" in seen["system"]
    assert "WHAT THE AGENT KNOWS ABOUT THE JOBS" in seen["context"] and "Bank statements March (blocks preparation)" in seen["context"]
    assert texts_to(world.pat)[-1].startswith("Thanks Pat. Chase the client")
