"""Ask knows each agent's work (AFIT, 10 Nov 2026): the pre-check's result, the preparation guide and the
WP Agent's GST reconciliation are kept in the knowledge store as their own kinds of entry, tagged to
the task; a question is put in its area and answered from that agent's work first."""
import json
import re

from precheck_agent import ask, llm, memory
from precheck_agent.knowledge import Scope, get_knowledge

from .test_ask import answering
from .test_gst_agent import gst_job, run  # noqa: F401  (the WP Agent's job)

PRECHECK = {"decision": {"state": "requests", "label": "Requests to send", "reason": "2 items are still needed before preparation."},
            "business_nature": {"type": "residential_rental", "label": "Residential rental", "summary": "One rental property.", "reasoning": "Questionnaire."},
            "requests": [{"group": "Loans", "item": "ASB loan annual summary", "priority": "blocking", "reason": "Interest must be split from principal."},
                         {"group": "Rates", "item": "Rates notice 2025/26", "priority": "normal", "reason": "Rates paid were in last year's accounts."}],
            "provided": [{"group": "Bank", "item": "Bank statements", "reason": "This year's bank export has been received."}],
            "not_needed": [], "accountant_questions": [], "preparer_notes": [{"text": "Interest is fully deductible from 1 April 2025."}],
            "key_documents": [], "checks": [], "bank": [], "email": {"subject": "Information still needed", "body": "Please send the ASB loan summary."}}
GUIDE = {"format": 2, "summary": "Start with the loan and the rates.", "decision": {"reason": "3 steps; 1 waits on the client."},
         "snapshot": {"activities": "One residential rental", "period": "Year to 31 March 2026"},
         "events": [{"id": "E1", "status": "confirmed", "event": "Refinanced with ASB in August", "why_it_matters": "Interest split", "action": "Split interest",
                     "effect": "Interest expense"}],
         "sequence": [{"step": "Record the ASB refinance and split the interest", "depends_on": "ASB loan summary", "can_start_now": False, "escalate": ""}],
         "risks": [{"area": "Interest", "what_could_be_wrong": "Principal claimed as interest", "examine": "Loan statements", "evidence": "ASB summary"}],
         "checklist": [{"check": "Interest agreed to the loan summary", "status": "open"}], "queries": {}, "prior_year": [], "judgments": [], "roll_forward": []}


def asked(env, job: dict, question: str):
    seen: dict = {}
    llm.set_fake("assistant", answering({"answer": "See the passages.", "status": "answered", "outside_job": False, "points": []}, seen))
    out = ask.answer(job, question)
    labels = re.findall(r"^K\d+ \| \[([^\]]+)\]", seen["body"], re.M)
    return out, seen["body"], labels


def test_the_wp_agents_work_is_kept_and_answers_questions_about_it(env, gst_job):
    final = run(gst_job)
    scope = Scope.of(env.pm.jobs[gst_job])
    entries = get_knowledge().get(scope, source_types=["wp_gst"])
    texts = " ".join(e["text"] for e in entries)
    assert len(entries) > 20 and all(e["task"] == gst_job for e in entries)
    assert "expected GST control balance E = A + B - C + D is 2,875.00" in texts
    assert "GST payment debited to income tax" in texts and "Alpha Ltd INV-3001" in texts

    out, body, labels = asked(env, env.pm.jobs[gst_job], "Why is the GST reconciliation only reconciled subject to corrections?")
    assert "QUESTION AREA: the WP Agent's GST reconciliation" in body
    assert labels[0] == "WP Agent (GST reconciliation)" and labels.count("WP Agent (GST reconciliation)") >= 5
    assert "Reconciled subject to corrections" in body and out["areas"] == ["the WP Agent's GST reconciliation"]

    _, body, _ = asked(env, env.pm.jobs[gst_job], "What GST is in Alpha Ltd's balance in the ageing?")
    assert re.search(r"\[WP Agent \(GST reconciliation\)\] WP Agent Receivables \(G1\) line: Alpha Ltd INV-3001 .* GST 300\.00", body)
    assert final["gst"]["receivables"]["items"][0]["contact"] == "Alpha Ltd"


def test_the_precheck_and_the_guide_are_kept_apart_and_each_question_finds_its_own(env):
    env.pm.add_job("501", "client-r", "nowhere", direction=[])
    job = {**env.pm.jobs["501"], "last_precheck_result": PRECHECK, "last_guide": GUIDE}
    _, body, labels = asked(env, job, "What is still needed from the client?")
    assert "QUESTION AREA: the pre-check" in body and labels[0] == "Pre-check result"
    assert "ASB loan annual summary" in body and "documents have not been read yet" not in body
    _, body, labels = asked(env, job, "Where should I start, and what are the next steps?")
    assert "QUESTION AREA: the preparation guide" in body and labels[0] == "Preparation guide"
    assert "Record the ASB refinance" in body
    kinds = {e["source_type"] for e in get_knowledge().get(Scope.of(job), source_types=["precheck_result", "guide"])}
    assert kinds == {"precheck_result", "guide"}


def test_a_result_is_stored_once_and_a_new_one_replaces_it(env):
    env.pm.add_job("502", "client-r", "nowhere", direction=[])
    scope = Scope.of(env.pm.jobs["502"])
    first = memory.remember_guide(scope, GUIDE)
    assert first > 5 and memory.remember_guide(scope, GUIDE) == 0  # unchanged: not stored again
    changed = {**GUIDE, "summary": "Start with the rates.", "events": []}
    memory.remember_guide(scope, changed)
    texts = [e["text"] for e in get_knowledge().get(scope, source_types=["guide"])]
    assert any("Start with the rates." in t for t in texts) and not any("Refinanced with ASB" in t for t in texts)


def test_another_clients_results_never_answer(env, gst_job):
    run(gst_job)
    env.pm.add_job("503", "client-other", "nowhere", direction=[])
    _, body, labels = asked(env, env.pm.jobs["503"], "How much GST was outstanding at balance date?")
    assert "WP Agent (GST reconciliation)" not in labels and "2,575.00" not in body


def test_questions_are_put_in_their_area():
    cases = {
        "Why is the GST reconciliation unreconciled?": ["wp_gst"],
        "How much GST was outstanding at the balance date?": ["wp_gst"],
        "What did the WP Agent propose for the income tax payment?": ["wp_gst"],
        "What is still needed from the client?": ["precheck_result"],
        "Where should I start preparing?": ["guide"],
        "What did the reviewer say about depreciation?": ["review"],
        "How much was 43 Te Wharo Drive sold for?": [],
    }
    for question, areas in cases.items():
        assert ask.areas_of(question) == areas, question
    assert json.dumps(ask.AREA_LABEL)
