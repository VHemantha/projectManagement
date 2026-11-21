"""The preparation guide, format 3 (AFIT, 21 Nov 2026): points, never questions; the job's areas of
caution as its summary; the significant events worked out but not shown as a section; a step-by-step
plan from the start of preparation to finalisation, by phase; the areas that need judgment; and the
completion checklist. Code checks every figure and source, keeps "confirmed" for events a document
shows, follows every event through, drops anything worded as a question, lists the documents still to
come from the pre-check, and makes sure the steps reach review and finalisation."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import llm
from precheck_agent.guide import PHASES

from .test_precheck import ACCOUNT, ready_folder

SECTIONS = ["cautions", "snapshot", "prior_year", "risks", "steps", "judgments", "points", "outstanding", "checklist", "roll_forward"]


def scripted(answer: dict):
    def responder(messages, kwargs):
        return AIMessage(content=json.dumps(answer), usage_metadata={"input_tokens": 9000, "output_tokens": 1200, "total_tokens": 10200},
                         response_metadata={"stop_reason": "end_turn"})
    return responder


def answer(**over) -> dict:
    base = {
        "cautions": [],
        "snapshot": {"activities": "Residential rental at 43 Te Wharo Drive.", "assets_and_funding": "One rental property funded by an ASB loan.",
                     "records": "ANZ bank export for the year; last year's statements.", "bookkeeping": "Bank exports only, no ledger.",
                     "period": "Year to 31 March 2026.", "sources": "B1, Z9"},
        "events": [], "prior_year": [], "risks": [], "steps": [], "judgments": [], "points": [], "checklist": [], "roll_forward": [],
    }
    base.update(over)
    return base


def test_the_guide_reads_the_precheck_and_gives_points_steps_to_finalisation_and_cautions(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.pm.jobs["1"]["last_precheck"] = {"business_nature": {"label": "Residential rental"},
                                         "requests": [{"group": "ASB loan", "item": "Annual loan summary"}],
                                         "preparer_notes": [{"text": "Interest is fully deductible from 1 April 2025."}]}
    result = env.run("1", mode="guide")
    assert result["status"] == "complete" and result["mode"] == "guide" and len(env.precheck.calls) == 1
    body = env.precheck.calls[0]["messages"][-1].content
    system = env.precheck.calls[0]["messages"][0].content
    assert "# Skill: nz-preparation-guide" in system and "never questions" in system
    assert f"B1 | {ACCOUNT}" in body and "Still requested from the client: ASB loan — Annual loan summary" in body
    assert "Write statements and instructions, never questions" in body
    assert "items: everything this year's accounts need" not in body  # the pre-check's answer instructions are replaced
    guide = result["guide"]
    assert guide["format"] == 3 and all(s in guide for s in SECTIONS)
    (event,) = guide["events"]  # worked out (not shown), and followed through
    assert event["id"] == "E1" and event["status"] == "suspected" and event["not_followed_through"] == []
    # The documents still to come are listed by code from the pre-check.
    assert guide["outstanding"] == [{"group": "ASB loan", "item": "Annual loan summary", "flags": []}]
    # A point worded as a question is dropped; the guide says so.
    assert [p["text"] for p in guide["points"]] == ["Confirm what the payments to the first payee were for from the invoices."]
    assert guide["questions_dropped"] == 1 and "questions_dropped" in guide["flags"]
    # The steps run in phase order through review to finalisation (code writes in what the model left out).
    phases = [s["phase"] for s in guide["steps"]]
    assert phases == sorted(phases, key=PHASES.index) and phases[-2:] == ["review", "finalise"]
    assert [s["n"] for s in guide["steps"]] == list(range(1, len(phases) + 1))
    assert guide["steps"][-1]["flags"] == ["added_by_code"] and guide["steps"][-2]["flags"] == ["added_by_code"] and guide["phase_labels"]["finalise"] == "Finalisation"
    assert guide["judgments"][0]["area"] == "Expenses" and guide["cautions"][0]["level"] == "medium"
    assert guide["decision"]["reason"] == f"1 area of caution; {len(phases)} steps to finalisation; 1 judgment; 2 open checks."
    assert result["readiness"] == "Preparation guide" and "review" not in result
    again = env.run("1", mode="guide")
    assert len(env.precheck.calls) == 1 and again["guide"]["how"] == "cache"  # nothing changed: not paid again


def test_code_checks_figures_confirmations_follow_through_and_questions(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.precheck = llm.set_fake("precheck", scripted(answer(
        cautions=[{"area": "Loan", "caution": "The refinance changes the interest.", "level": "medium", "sources": ""},
                  {"area": "Assets", "caution": "Machinery may be capital.", "level": "high", "sources": ""},
                  {"area": "Bank", "caution": "Has the bank been reconciled?", "level": "low", "sources": ""}],
        events=[
            # Confirmed with no document behind it: becomes suspected. Followed through everywhere.
            {"id": "a", "event": "Loan refinanced with ASB.", "status": "confirmed", "why_it_matters": "Interest and the loan balance change.",
             "action": "Reconcile settlement of the old loan and drawdown of the new loan.", "effect": "Not yet quantifiable.", "sources": "Z9"},
            # Confirmed by the bank line, but its amount is invented and it is never followed through.
            {"id": "b", "event": "Machinery bought for 99,999.00.", "status": "confirmed", "why_it_matters": "Capital, not expense.",
             "action": "Inspect the invoice.", "effect": "Fixed assets up.", "sources": "B1.2"},
            {"id": "c", "event": "Loan refinanced with ASB.", "status": "suspected", "why_it_matters": "Duplicate.", "action": "x", "effect": "", "sources": ""},
        ],
        steps=[{"phase": "finalise", "step": "File the return.", "depends_on": "the review", "can_start_now": False, "escalate": "", "events": "", "sources": ""},
               {"phase": "reconcile", "step": "Reconcile the ASB loan statements.", "depends_on": "Annual loan summary", "can_start_now": False,
                "escalate": "", "events": "a, zz", "sources": "B1"},
               {"phase": "nowhere", "step": "Open the folder.", "depends_on": "nothing", "can_start_now": True, "escalate": "", "events": "", "sources": ""}],
        points=[{"kind": "action", "text": "Agree the refinance to the bank's settlement letter.", "events": "a", "sources": ""},
                {"kind": "note", "text": "Was the ASB loan refinanced, and on what date?", "events": "a", "sources": ""}],
        judgments=[{"area": "", "judgment": "Repairs or capital for the deck.", "evidence": "The invoice.", "manager_approval": True,
                    "reference": "IR 264", "events": "", "sources": ""}],
        checklist=[{"check": "Refinance reconciled.", "status": "open", "events": "a"},
                   {"check": "Bank reconciled.", "status": "maybe", "events": ""}],
    )))
    guide = env.run("1", mode="guide")["guide"]
    refinance, machinery = guide["events"]  # the duplicate is dropped; ids are renumbered
    assert (refinance["id"], refinance["status"], refinance["sources"]) == ("E1", "suspected", [])
    assert "confirmation_not_documented" in refinance["flags"] and refinance["not_followed_through"] == []
    assert machinery["id"] == "E2" and machinery["status"] == "confirmed" and machinery["sources"][0]["id"] == "B1.2"
    assert "figure_not_in_documents" in machinery["flags"] and machinery["not_followed_through"] == ["step", "checklist"]
    # Cautions: the highest first, and none worded as a question.
    assert [(c["area"], c["level"]) for c in guide["cautions"]] == [("Assets", "high"), ("Loan", "medium")]
    # Steps in phase order (an unknown phase is the start), with the review written in by code.
    assert [(s["phase"], s["step"]) for s in guide["steps"]] == [
        ("start", "Open the folder."), ("reconcile", "Reconcile the ASB loan statements."),
        ("review", guide["steps"][2]["step"]), ("finalise", "File the return.")]
    assert guide["steps"][1]["events"] == ["E1"]  # an unknown event reference is dropped
    assert [p["text"] for p in guide["points"]] == ["Agree the refinance to the bank's settlement letter."]
    assert guide["judgments"][0]["area"] == "General" and guide["judgments"][0]["manager_approval"] is True
    assert guide["checklist"][1]["status"] == "open"  # an unknown status is read as open
    assert [s["id"] for s in guide["snapshot"]["sources"]] == ["B1"]  # Z9 does not exist
    assert guide["flags"] == ["questions_dropped"] and 0 < guide["words"] < 1200


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


def test_a_guide_longer_than_two_pages_is_flagged(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    long_step = "Reconcile the account and agree every receipt and payment to the statement and the ledger with care " * 3
    env.precheck = llm.set_fake("precheck", scripted(answer(
        steps=[{"phase": "reconcile", "step": f"{n}. {long_step}", "depends_on": "nothing in particular at this stage of the work", "can_start_now": True,
                "escalate": "Raise with the manager if the difference cannot be explained within the day", "events": "", "sources": "B1"}
               for n in range(16)],
        risks=[{"area": f"Area {n}", "what_could_be_wrong": f"Risk {n}: {long_step}", "examine": long_step, "evidence": long_step, "events": "", "sources": ""}
               for n in range(5)],
    )))
    guide = env.run("1", mode="guide")["guide"]
    assert guide["words"] > 1200 and guide["flags"] == ["longer_than_two_pages"]


def test_the_answer_shape_stays_small_enough_for_the_api():
    """The API compiles the answer shape into a grammar and refused an early version (an array of ids on
    every item) as too large: ids are strings."""
    from precheck_agent.guide import SCHEMA

    def arrays_of_strings(v) -> int:
        if isinstance(v, dict):
            here = 1 if v.get("type") == "array" and v.get("items", {}).get("type") == "string" else 0
            return here + sum(arrays_of_strings(x) for x in v.values())
        return sum(arrays_of_strings(x) for x in v) if isinstance(v, list) else 0

    assert arrays_of_strings(SCHEMA) == 0
    assert "queries" not in SCHEMA["properties"] and SCHEMA["properties"]["points"]["type"] == "array"
