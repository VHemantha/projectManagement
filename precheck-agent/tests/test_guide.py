"""The preparation guide (AFIT's agreed structure, 21 Oct 2026): eight sections, from the job snapshot
to the completion checklist. Code checks every figure and source, keeps "confirmed" for events a
document shows, follows every event through, and keeps queries from repeating each other."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import llm

from .test_precheck import ACCOUNT, ready_folder

SECTIONS = ["snapshot", "events", "prior_year", "risks", "sequence", "judgments", "queries", "checklist"]


def scripted(answer: dict):
    def responder(messages, kwargs):
        return AIMessage(content=json.dumps(answer), usage_metadata={"input_tokens": 9000, "output_tokens": 1200, "total_tokens": 10200},
                         response_metadata={"stop_reason": "end_turn"})
    return responder


def answer(**over) -> dict:
    base = {
        "snapshot": {"activities": "Residential rental at 43 Te Wharo Drive.", "assets_and_funding": "One rental property funded by an ASB loan.",
                     "records": "ANZ bank export for the year; last year's statements.", "bookkeeping": "Bank exports only, no ledger.",
                     "period": "Year to 31 March 2026.", "sources": "B1, Z9"},
        "events": [], "prior_year": [], "risks": [], "sequence": [], "judgments": [], "queries": [], "checklist": [], "roll_forward": [],
    }
    base.update(over)
    return base


def test_the_guide_has_the_eight_sections_and_reads_the_precheck_and_its_result(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.pm.jobs["1"]["last_precheck"] = {"business_nature": {"label": "Residential rental"},
                                         "requests": [{"group": "ASB loan", "item": "Annual loan summary"}],
                                         "preparer_notes": [{"text": "Interest is fully deductible from 1 April 2025."}]}
    result = env.run("1", mode="guide")
    assert result["status"] == "complete" and result["mode"] == "guide" and len(env.precheck.calls) == 1
    body = env.precheck.calls[0]["messages"][-1].content
    system = env.precheck.calls[0]["messages"][0].content
    assert "# Skill: nz-preparation-guide" in system and "what happened → why it matters" in system.replace("**", "")
    assert f"B1 | {ACCOUNT}" in body and "Still requested from the client: ASB loan — Annual loan summary" in body
    assert "Note for the preparer: Interest is fully deductible from 1 April 2025." in body
    assert "items: everything this year's accounts need" not in body  # the pre-check's answer instructions are replaced
    guide = result["guide"]
    assert guide["format"] == 2 and all(s in guide for s in SECTIONS)
    (event,) = guide["events"]
    assert event["id"] == "E1" and event["status"] == "suspected" and event["not_followed_through"] == []  # step, query and checklist
    assert guide["queries"]["outstanding"][0]["item"] == "Annual loan summary"
    assert guide["sequence"][0]["sources"][0]["id"] == "B1" and guide["sequence"][0]["events"] == ["E1"]
    assert guide["decision"]["reason"] == "1 significant event (1 to confirm); 1 priority risk; 2 open checks."
    assert result["readiness"] == "Preparation guide" and "review" not in result
    again = env.run("1", mode="guide")
    assert len(env.precheck.calls) == 1 and again["guide"]["how"] == "cache"  # nothing changed: not paid again


def test_code_checks_figures_confirmations_follow_through_and_repeated_queries(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.precheck = llm.set_fake("precheck", scripted(answer(
        events=[
            # Confirmed with no document behind it: becomes suspected. Followed through everywhere.
            {"id": "a", "event": "Loan refinanced with ASB.", "status": "confirmed", "why_it_matters": "Interest and the loan balance change.",
             "action": "Reconcile settlement of the old loan and drawdown of the new loan.", "effect": "Not yet quantifiable.", "sources": "Z9"},
            # Confirmed by the bank line, but its amount is invented and it is never followed through.
            {"id": "b", "event": "Machinery bought for 99,999.00.", "status": "confirmed", "why_it_matters": "Capital, not expense.",
             "action": "Inspect the invoice.", "effect": "Fixed assets up.", "sources": "B1.2"},
            {"id": "c", "event": "Loan refinanced with ASB.", "status": "suspected", "why_it_matters": "Duplicate.", "action": "x", "effect": "", "sources": ""},
        ],
        sequence=[{"step": "Reconcile the ASB loan statements.", "depends_on": "Annual loan summary", "can_start_now": False,
                   "escalate": "", "events": "a, zz", "sources": "B1"}],
        queries=[{"to": "client", "text": "Annual loan summary", "events": "", "sources": ""},  # repeats an outstanding request
                 {"to": "client", "text": "Was the ASB loan refinanced, and on what date?", "events": "a", "sources": ""},
                 {"to": "outstanding", "text": "Annual loan summary", "events": "a", "sources": ""}],
        checklist=[{"check": "Refinance reconciled.", "status": "open", "events": "a"},
                   {"check": "Bank reconciled.", "status": "maybe", "events": ""}],
    )))
    guide = env.run("1", mode="guide")["guide"]
    refinance, machinery = guide["events"]  # the duplicate is dropped; ids are renumbered
    assert (refinance["id"], refinance["status"], refinance["sources"]) == ("E1", "suspected", [])
    assert "confirmation_not_documented" in refinance["flags"] and refinance["not_followed_through"] == []
    assert machinery["id"] == "E2" and machinery["status"] == "confirmed" and machinery["sources"][0]["id"] == "B1.2"
    assert "figure_not_in_documents" in machinery["flags"] and machinery["not_followed_through"] == ["sequence", "checklist"]
    assert guide["sequence"][0]["events"] == ["E1"]  # an unknown event reference is dropped
    assert [c["question"] for c in guide["queries"]["client"]] == ["Was the ASB loan refinanced, and on what date?"]
    assert guide["checklist"][1]["status"] == "open"  # an unknown status is read as open
    assert [s["id"] for s in guide["snapshot"]["sources"]] == ["B1"]  # Z9 does not exist
    assert guide["flags"] == [] and 0 < guide["words"] < 900


def test_what_last_years_guide_rolled_forward_is_taken_up_this_year(env):
    """This year's findings roll forward: next year's guide is given them (Y lines) and each one
    reaches its prior-year section, by the model or, if it skips one, by code."""
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.pm.jobs["1"]["rolled_forward"] = [
        {"from": "SMITH-FY25", "period": "Year ended 31 March 2025", "kind": "roll_forward", "item": "Agree the ASB loan to the annual summary.",
         "why": "Was not received last year."},
        {"from": "SMITH-FY25", "period": "Year ended 31 March 2025", "kind": "open_event", "item": "Large payment to Harcourts: possible property purchase."},
    ]
    env.precheck = llm.set_fake("precheck", scripted(answer(
        snapshot={"activities": "Rental.", "assets_and_funding": "", "records": "", "bookkeeping": "", "period": "", "sources": ""},
        prior_year=[{"item": "ASB loan not agreed last year.", "kind": "unresolved", "follow_through": "Agree it to this year's summary.", "sources": "Y1"}],
        roll_forward=[{"item": "Confirm the property purchase date.", "why": "Rental income starts from it.", "sources": "B1"},
                      {"item": "", "why": "empty", "sources": ""}],
    )))
    result = env.run("1", mode="guide")
    body = env.precheck.calls[-1]["messages"][-1].content
    assert "== ROLLED FORWARD FROM THE CLIENT'S EARLIER GUIDE" in body
    assert "Y1 | from SMITH-FY25 (Year ended 31 March 2025) | handed on | Agree the ASB loan to the annual summary. | Was not received last year." in body
    guide = result["guide"]
    taken, added = guide["prior_year"]
    assert taken["sources"][0]["id"] == "Y1" and taken["sources"][0]["label"].startswith("Rolled forward from SMITH-FY25")
    # The model skipped Y2: code adds it, so nothing handed on is lost.
    assert added["item"] == "Large payment to Harcourts: possible property purchase." and added["flags"] == ["added_by_code"]
    assert added["sources"][0]["id"] == "Y2" and "confirm whether it is resolved" in added["follow_through"]
    assert [r["item"] for r in guide["roll_forward"]] == ["Confirm the property purchase date."]  # the empty one is dropped
    assert guide["snapshot"]["period"].startswith("Not established from the documents")  # the period is always stated


def test_a_guide_longer_than_a_page_and_a_half_is_flagged(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    long_step = "Reconcile the account and agree every receipt and payment to the statement and the ledger with care " * 3
    env.precheck = llm.set_fake("precheck", scripted(answer(
        sequence=[{"step": f"{n}. {long_step}", "depends_on": "nothing in particular at this stage of the work", "can_start_now": True,
                   "escalate": "Raise with the manager if the difference cannot be explained within the day", "events": "", "sources": "B1"}
                  for n in range(12)],
        risks=[{"area": f"Area {n}", "what_could_be_wrong": f"Risk {n}: {long_step}", "examine": long_step, "evidence": long_step, "events": "", "sources": ""}
               for n in range(5)],
    )))
    guide = env.run("1", mode="guide")["guide"]
    assert guide["words"] > 900 and guide["flags"] == ["longer_than_a_page_and_a_half"]


def test_the_answer_shape_stays_small_enough_for_the_api():
    """The API compiles the answer shape into a grammar and refused the first version (an array of
    ids on every item, three query lists) as too large: ids are strings, queries one list."""
    from precheck_agent.guide import SCHEMA

    def arrays_of_strings(v) -> int:
        if isinstance(v, dict):
            here = 1 if v.get("type") == "array" and v.get("items", {}).get("type") == "string" else 0
            return here + sum(arrays_of_strings(x) for x in v.values())
        return sum(arrays_of_strings(x) for x in v) if isinstance(v, list) else 0

    assert arrays_of_strings(SCHEMA) == 0
    assert SCHEMA["properties"]["queries"]["type"] == "array"
