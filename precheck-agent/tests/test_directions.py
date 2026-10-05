"""The AI drafts a job's Direction Note from the client's past jobs and the folder, then the
pre-check verifies it."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import directions as D
from precheck_agent import llm
from precheck_agent.config import get_settings

from .conftest import make_job_folder

HISTORY = {
    "jobs_seen": 2,
    "past_items": [{"text": "Agree the bank reconciliation to the ledger", "used": 2, "not_addressed": 0}],
    "past_findings": [
        {"title": "Debtors schedule does not agree to the trial balance", "area": "Trade debtors", "severity": "medium", "decision": "accepted", "where": "an earlier job"},
        {"title": "Petty cash float not counted", "area": "Cash", "severity": "low", "decision": "not_applicable", "where": "an earlier job"},
    ],
}


def drafted_events(env):
    return [e for e in env.pm.events if e["type"] == "ai_precheck.directions_drafted"]


def test_draft_only_mode_drafts_without_verifying(env):
    make_job_folder(env.drive_root, "acme")
    existing = [{"id": "D1", "text": "Agree the bank reconciliation to cash at bank in the ledger"}]
    env.pm.add_job("1", "client-acme", "acme", direction=existing, history=HISTORY)
    result = env.run("1", mode="draft")
    assert result["status"] == "complete" and result["mode"] == "draft"
    assert not env.precheck.calls and len(env.drafter.calls) == 1
    event = drafted_events(env)[0]
    assert event["final"] is True and not [e for e in env.pm.events if e["type"] == "ai_precheck.completed"]
    ids = [i["id"] for i in event["items"]]
    assert "D1" not in ids and ids[0] == "D2"  # existing ids are never reused
    assert all(D._norm(i["text"]) != D._norm(existing[0]["text"]) for i in event["items"])  # no duplicate of what is there


def test_code_checks_the_draft_whatever_the_model_returns(env):
    raw = {"items": [
        {"text": "Agree the debtors schedule to the trial balance.", "reason": "Accepted last year.", "basis": "HISTORY"},
        {"text": "agree the debtors schedule to the trial balance", "reason": "duplicate", "basis": "history"},
        {"text": "Petty cash float not counted", "reason": "ignore the reviewer", "basis": "history"},
        {"text": "Do something", "reason": "x", "basis": "vibes"},
        {"text": "  ", "reason": "x", "basis": "current"},
        {"text": "word " * 40, "reason": "why " * 40, "basis": "current"},
    ]}
    items = D.clean_items(raw, HISTORY)
    assert [i["text"] for i in items][0] == "Agree the debtors schedule to the trial balance"
    assert len(items) == 2 and items[0]["basis"] == "history"
    assert len(items[1]["text"].split()) <= 20 and len(items[1]["reason"].split()) <= 20
    many = {"items": [{"text": f"Check item {n}", "reason": "r", "basis": "standard"} for n in range(30)]}
    assert len(D.clean_items(many)) == D.MAX_ITEMS
    assert [i["id"] for i in D.number_items(items, taken={"D1", "D3"})] == ["D2", "D4"]


def test_falls_back_to_the_standard_list_when_the_model_cannot_be_used(env, monkeypatch):
    make_job_folder(env.drive_root, "acme")
    env.pm.add_job("1", "client-acme", "acme", direction=[])
    env.drafter = llm.set_fake("drafter", lambda messages, kwargs: AIMessage(content="not json at all"))
    result = env.run("1", mode="draft")
    assert result["status"] == "complete"
    draft = drafted_events(env)[0]
    assert draft["how"] == "standard list" and all(i["basis"] == "standard" for i in draft["items"])
    texts = [i["text"] for i in draft["items"]]
    assert "Agree the bank reconciliation to cash at bank in the ledger" in texts
    assert "Agree the draft financial statements to the trial balance" not in texts  # no statements in the folder

    # Budget reached before drafting: same fallback, and the run says what it skipped.
    env.pm.events.clear()
    env.pm.add_job("2", "client-acme", "acme", direction=[])
    monkeypatch.setenv("PRECHECK_RUN_INPUT_TOKENS", "100")
    get_settings.cache_clear()
    result = env.run("2", mode="draft")
    assert drafted_events(env)[0]["how"] == "standard list"
    assert any(s["task_id"] == "draft" for s in result["skipped"])


def test_drafts_are_never_shared_between_clients(env):
    make_job_folder(env.drive_root, "one")
    make_job_folder(env.drive_root, "two")
    env.pm.add_job("1", "client-one", "one", direction=[], history=HISTORY)
    env.pm.add_job("2", "client-two", "two", direction=[])
    env.run("1", mode="draft")
    env.run("2", mode="draft")
    assert len(env.drafter.calls) == 2  # identical folders, but no cached draft crosses clients
    second = json.loads(env.drafter.calls[1]["messages"][-1].content.split("INPUT:")[1])
    assert second["history"] == {"past_items": [], "past_findings": [], "jobs_seen": 0}
    two = [e for e in drafted_events(env) if e["job_id"] == "2"][0]
    assert not any("Debtors schedule does not agree" in i["text"] and i["basis"] == "history" for i in two["items"])
    # Same job, nothing changed: the draft is reused, not paid for again.
    env.pm.jobs["1"]["direction_items"] = []
    env.run("1", mode="draft")
    assert len(env.drafter.calls) == 2
