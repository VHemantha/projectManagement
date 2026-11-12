"""Missing information is provisional (gaps.py, 12 Nov 2026): a pre-check's "not found" becomes a gap
checked against every document of the task, backward when it is found and forward as documents
arrive, and is confirmed missing only once the case is finalised (by the autonomous re-check when the
folder has settled, or on request).

The pre-check model and the verifier are scripted, so the tests show what code does with their
answers: which passages it accepts as evidence, how it decides a gap's status, and when."""
import ast
import inspect
import json
import random
import re
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from precheck_agent import config, gaps, llm, runner
from precheck_agent.knowledge import Scope

INCOME = {"group": "Applicant", "item": "Applicant annual income", "reason": "The application needs the applicant's annual income."}
STATEMENTS = {"group": "Bank", "item": "Bank statements for April, May and June 2025",
              "reason": "Three months of bank statements are required: April, May and June 2025."}
MONTHS = ("April", "May", "June")


def _ai(answer: dict) -> AIMessage:
    text = json.dumps(answer)
    return AIMessage(content=text, usage_metadata={"input_tokens": 500, "output_tokens": 80, "total_tokens": 580},
                     response_metadata={"stop_reason": "end_turn"})


def precheck_asking_for(*wanted: dict, only_with: str | None = None):
    """The pre-check model asks for each wanted item ("not found in what it was shown"), citing the
    R line of a document that requires it when there is one. `only_with`: it asks only when a
    document with these words is in what it is shown (a checklist requiring the item)."""
    def responder(messages, kwargs):
        body = llm._flatten(messages[-1].content)
        if only_with and only_with not in body:
            items = []
        else:
            cite = next((ln.split(" | ")[0] for ln in body.splitlines() if re.match(r"^[QR]\d+ \| ", ln) and only_with and only_with in ln), None)
            items = [{**w, "decision": "request", "priority": "normal", "sources": [cite] if cite else [], "documents": []} for w in wanted]
        return _ai({"business_nature": {"type": "general", "summary": "Test.", "reasoning": "Test.", "sources": [], "facts": []},
                    "items": items, "preparer_notes": [], "lessons_applied": []})
    return responder


def verifier(messages, kwargs):
    """Reads the candidate passages as an accountant would: an annual income figure, or which of the
    three months of statements a passage is. Quotes the passage's own words."""
    body = llm._flatten(messages[-1].content)
    requirement = body.split("\n", 1)[0]
    found = body.split("ALREADY FOUND:", 1)[1].split("CANDIDATE PASSAGES:", 1)[0]
    passages = [ln.split(" | ", 2) for ln in body.split("CANDIDATE PASSAGES:", 1)[1].splitlines() if re.match(r"^K\d+ \| ", ln)]
    evidence = []
    if "income" in requirement.lower():
        for kid, _, text in passages:
            m = re.search(r"Annual income: \$?([\d,]+)", text)
            if m:
                evidence.append({"passage": kid, "extracted_value": m.group(1), "quoted_snippet": m.group(0), "confidence": 0.95})
        have = bool(evidence) or "(nothing yet)" not in found
        return _ai({"resolves": have, "partial": False, "single_value": True, "still_needed": "", "reasoning": "Income stated.", "evidence": evidence})
    months = {m for m in MONTHS if f": {m}" in found}
    for kid, _, text in passages:
        m = re.search(r"Bank statement for (April|May|June) 2025", text)
        if m:
            evidence.append({"passage": kid, "extracted_value": m.group(1), "quoted_snippet": m.group(0), "confidence": 0.9})
            months.add(m.group(1))
    missing = [m for m in MONTHS if m not in months]
    return _ai({"resolves": not missing, "partial": bool(months) and bool(missing), "single_value": False,
                "still_needed": f"the statement{'s' if len(missing) != 1 else ''} for {' and '.join(missing)} 2025" if missing else "",
                "reasoning": "Months counted.", "evidence": evidence})


def write(folder: Path, name: str, text: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def base(folder: Path) -> Path:
    """The documents every case starts with: an application form, which has no income on it."""
    write(folder, "Application form.txt", "Loan application form\nApplicant name: Jane Rewi\nAddress: 12 Kauri Street, Auckland\n")
    return folder


DOCS = {
    "income": ("Payslip summary.txt", "Employer summary for the year\nAnnual income: $50,000\nEmployer: Kauri Builders Ltd\n"),
    "income_other": ("Tax return extract.txt", "IR3 extract\nAnnual income: $65,000\nFiled 30 June 2025\n"),
    "april": ("ANZ April.txt", "ANZ cheque account 01-0702-0311954-00\nBank statement for April 2025\nClosing balance 1,200.00\n"),
    "may": ("ANZ May.txt", "ANZ cheque account 01-0702-0311954-00\nBank statement for May 2025\nClosing balance 1,350.00\n"),
    "june": ("ANZ June.txt", "ANZ cheque account 01-0702-0311954-00\nBank statement for June 2025\nClosing balance 1,410.00\n"),
    "checklist": ("Lender checklist.txt", "Lender checklist\nRequired: the applicant's annual income\nRequired: three months of bank statements\n"),
}


def add(folder: Path, *keys: str) -> None:
    for k in keys:
        write(folder, *DOCS[k])


@pytest.fixture
def gap_env(env, monkeypatch):
    env.verifier = llm.set_fake("verifier", verifier)

    def case(job_id: str, client: str = "client-a"):
        folder = base(env.drive_root / f"case-{job_id}")
        env.pm.add_job(job_id, client, f"case-{job_id}", direction=[])
        return folder

    def gap_of(job_id: str, item: str) -> dict:
        job = env.pm.get_job(job_id)
        rows = [g for g in gaps.load(Scope.of(job)).values() if g["item"] == item]
        assert len(rows) == 1, rows
        return rows[0]

    def model_gaps(job_id: str) -> list[dict]:
        return [g for g in gaps.load(Scope.of(env.pm.get_job(job_id))).values() if g["origin"] == "precheck"]

    env.case, env.gap_of, env.model_gaps = case, gap_of, model_gaps
    env.sweep = runner.sweep
    return env


def settle_now(monkeypatch):
    """No settle time: two quiet sweeps finalise the case."""
    monkeypatch.setenv("PRECHECK_GAP_SETTLE_DAYS", "0")
    config.get_settings.cache_clear()


# --- 1. forward ------------------------------------------------------------------------------------

def test_forward_a_document_that_arrives_later_resolves_the_gap(gap_env):
    env = gap_env
    folder = env.case("1")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    result = env.run("1")
    g = env.gap_of("1", INCOME["item"])
    assert g["status"] == gaps.OPEN and g["evidence"] == []
    request = next(r for r in result["precheck"]["requests"] if r["item"] == INCOME["item"])
    assert request["gap"]["status"] == gaps.OPEN
    # Never a final "missing" before the case is finalised: the result says it is provisional.
    assert result["precheck"]["decision"]["provisional"] is True and "not found in the documents so far" in result["precheck"]["decision"]["reason"]

    add(folder, "income")
    out = env.sweep("1")
    g = env.gap_of("1", INCOME["item"])
    assert g["status"] == gaps.RESOLVED
    [e] = g["evidence"]
    assert e["doc_name"] == "Payslip summary.txt" and e["doc_id"] == "case-1:Payslip summary.txt"
    assert e["found_direction"] == "forward" and e["extracted_value"] == "50,000" and e["quoted_snippet"] == "Annual income: $50,000"
    assert [h["to"] for h in g["history"]] == [gaps.RESOLVED]
    # The PM application is told, with the report.
    [event] = [ev for ev in env.pm.events if ev["type"] == "ai_precheck.gaps_updated"]
    assert out["changed"] and [r["item"] for r in event["report"]["resolved"]] == [INCOME["item"]]

    # The next pre-check shows it as provided, found by the search, with its evidence.
    again = env.run("1")["precheck"]
    assert INCOME["item"] not in [r["item"] for r in again["requests"]]
    provided = next(p for p in again["provided"] if p["item"] == INCOME["item"])
    assert provided["gap"]["status"] == gaps.RESOLVED and "Payslip summary.txt" in provided["documents"][0]["label"]


# --- 2. backward -----------------------------------------------------------------------------------

def test_backward_a_new_gap_is_searched_for_in_the_documents_already_read(gap_env):
    env = gap_env
    folder = env.case("2")
    add(folder, "income")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME, only_with="Lender checklist"))
    env.run("2")
    assert env.model_gaps("2") == []  # nothing required it yet

    add(folder, "checklist")
    result = env.run("2")["precheck"]
    g = env.gap_of("2", INCOME["item"])
    assert g["detected_in_doc_id"] == "case-2:Lender checklist.txt"  # the document that requires it
    assert g["status"] == gaps.RESOLVED
    [e] = g["evidence"]
    assert e["doc_name"] == "Payslip summary.txt" and e["found_direction"] == "backward"
    # Found before the client is asked: it is not in the requests or the email.
    assert INCOME["item"] not in [r["item"] for r in result["requests"]] and INCOME["item"] not in result["email"]["body"]


def test_a_similar_passage_is_not_evidence_unless_the_verifier_confirms_it(gap_env):
    env = gap_env
    folder = env.case("2b")
    write(folder, "Income notes.txt", "Notes about annual income\nThe applicant will send their income details later.\n")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    env.run("2b")
    assert env.gap_of("2b", INCOME["item"])["status"] == gaps.OPEN
    assert env.verifier.calls  # the passage was a candidate, but nothing in it fills the gap

    # A quote that is not in the passage is never accepted either.
    def inventing(messages, kwargs):
        body = llm._flatten(messages[-1].content)
        kid = next(ln.split(" | ")[0] for ln in body.splitlines() if re.match(r"^K\d+ \| ", ln))
        return _ai({"resolves": True, "partial": False, "single_value": True, "still_needed": "", "reasoning": "",
                    "evidence": [{"passage": kid, "extracted_value": "80,000", "quoted_snippet": "Annual income: $80,000", "confidence": 0.99}]})

    llm.set_fake("verifier", inventing)
    write(folder, "More notes.txt", "More about annual income\nSee the payslip.\n")
    env.sweep("2b")
    assert env.gap_of("2b", INCOME["item"])["status"] == gaps.OPEN


# --- 3. truly missing ------------------------------------------------------------------------------

def test_truly_missing_stays_open_while_the_folder_is_settling(gap_env):
    env = gap_env
    env.case("3a")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    env.run("3a")
    for _ in range(4):  # the default settle time is days: quiet sweeps alone never confirm it
        env.sweep("3a")
    assert env.gap_of("3a", INCOME["item"])["status"] == gaps.OPEN
    assert [c["task"] for c in gaps.cases_to_sweep()] == ["3a"]  # still being looked at


def test_truly_missing_is_confirmed_once_the_folder_has_settled(gap_env, monkeypatch):
    env = gap_env
    settle_now(monkeypatch)
    env.case("3")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    env.run("3")
    env.sweep("3")
    assert env.gap_of("3", INCOME["item"])["status"] == gaps.OPEN  # one quiet sweep is not enough
    env.sweep("3")
    g = env.gap_of("3", INCOME["item"])
    assert g["status"] == gaps.CONFIRMED
    assert g["history"][-1]["direction"] == "final"
    report = gaps.report(Scope.of(env.pm.get_job("3")))
    assert report["provisional"] is False and [r["item"] for r in report["confirmed_missing"] if r["origin"] == "precheck"] == [INCOME["item"]]
    assert gaps.cases_to_sweep() == []  # settled: the re-check stops looking


def test_a_document_that_arrives_after_confirmation_is_still_checked_by_the_next_run(gap_env):
    env = gap_env
    folder = env.case("3b")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    env.run("3b")
    env.sweep("3b", finalize=True)
    assert env.gap_of("3b", INCOME["item"])["status"] == gaps.CONFIRMED
    add(folder, "income")
    env.run("3b")
    g = env.gap_of("3b", INCOME["item"])
    assert g["status"] == gaps.RESOLVED and [h["to"] for h in g["history"]] == [gaps.CONFIRMED, gaps.RESOLVED]
    assert gaps.report(Scope.of(env.pm.get_job("3b")))["provisional"] is True  # reopened: provisional again


# --- 4. conflict -----------------------------------------------------------------------------------

def test_two_documents_with_different_values_conflict_and_both_are_kept(gap_env):
    env = gap_env
    folder = env.case("4")
    add(folder, "income", "income_other")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    result = env.run("4")["precheck"]
    g = env.gap_of("4", INCOME["item"])
    assert g["status"] == gaps.CONFLICTING
    assert sorted((e["doc_name"], e["extracted_value"]) for e in g["evidence"]) == [("Payslip summary.txt", "50,000"), ("Tax return extract.txt", "65,000")]
    # Neither is picked: it goes to the accountant, not to the client.
    question = next(q for q in result["accountant_questions"] if q["item"] == INCOME["item"])
    assert "50,000" in question["reason"] and "65,000" in question["reason"]
    assert INCOME["item"] not in [r["item"] for r in result["requests"]] and INCOME["item"] not in result["email"]["body"]
    # Finalising does not settle a conflict: a person does.
    env.sweep("4", finalize=True)
    assert env.gap_of("4", INCOME["item"])["status"] == gaps.CONFLICTING


def test_a_resolved_gap_becomes_conflicting_when_a_later_document_contradicts_it(gap_env):
    env = gap_env
    folder = env.case("4b")
    add(folder, "income")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    env.run("4b")
    assert env.gap_of("4b", INCOME["item"])["status"] == gaps.RESOLVED
    add(folder, "income_other")
    env.sweep("4b")
    g = env.gap_of("4b", INCOME["item"])
    assert g["status"] == gaps.CONFLICTING and len(g["evidence"]) == 2


# --- 5. partial ------------------------------------------------------------------------------------

def test_partial_evidence_says_what_is_still_needed_until_the_last_piece_arrives(gap_env):
    env = gap_env
    folder = env.case("5")
    add(folder, "april", "may")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(STATEMENTS))
    result = env.run("5")["precheck"]
    g = env.gap_of("5", STATEMENTS["item"])
    assert g["status"] == gaps.PARTIAL and g["still_needed"] == "the statement for June 2025"
    request = next(r for r in result["requests"] if r["item"] == STATEMENTS["item"])
    assert "still needed: the statement for June 2025" in request["reason"] and len(request["documents"]) == 2

    add(folder, "june")
    env.sweep("5")
    g = env.gap_of("5", STATEMENTS["item"])
    assert g["status"] == gaps.RESOLVED and sorted(e["extracted_value"] for e in g["evidence"]) == ["April", "June", "May"]
    assert [h["to"] for h in g["history"]] == [gaps.PARTIAL, gaps.RESOLVED]


# --- 6. order independence -------------------------------------------------------------------------

def _content(report: dict) -> dict:
    """The report without what only says when or how something was found."""
    out = {}
    for key in ("resolved", "partially_resolved", "conflicting", "open", "confirmed_missing"):
        out[key] = sorted((r["item"], r["still_needed"], tuple(sorted((e["doc_name"], e["quoted_snippet"], e["extracted_value"]) for e in r["evidence"])))
                          for r in report[key] if r["origin"] == "precheck")
    return out


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_final_report_is_the_same_whatever_order_the_documents_arrive_in(gap_env, seed):
    env = gap_env
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME, STATEMENTS))
    keys = ["income", "april", "may", "june"]

    # All at once.
    all_at_once = env.case(f"6-all-{seed}")
    add(all_at_once, *keys)
    env.run(f"6-all-{seed}")
    reference = _content(env.sweep(f"6-all-{seed}", finalize=True)["report"])

    # One at a time, in a shuffled order, with runs and sweeps in between.
    order = keys[:]
    random.Random(seed).shuffle(order)
    folder = env.case(f"6-one-{seed}")
    env.run(f"6-one-{seed}")
    for n, k in enumerate(order):
        add(folder, k)
        (env.run if n % 2 else env.sweep)(f"6-one-{seed}")
    assert _content(env.sweep(f"6-one-{seed}", finalize=True)["report"]) == reference
    assert [r[0] for r in reference["resolved"]] == sorted([INCOME["item"], STATEMENTS["item"]])


# --- 7. case isolation -----------------------------------------------------------------------------

def test_evidence_from_one_case_never_resolves_a_gap_in_another(gap_env):
    env = gap_env
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME))
    add(env.case("7x", client="client-a"), "income")
    env.case("7y", client="client-a")  # the same client, another task
    env.case("7z", client="client-b")  # another client
    for job in ("7x", "7y", "7z"):
        env.run(job)
    env.sweep("7y")
    env.sweep("7z")
    assert env.gap_of("7x", INCOME["item"])["status"] == gaps.RESOLVED
    assert env.gap_of("7y", INCOME["item"])["status"] == gaps.OPEN
    assert env.gap_of("7z", INCOME["item"])["status"] == gaps.OPEN
    # The verifier was never shown 7x's passage for the other cases.
    for call in env.verifier.calls:
        body = llm._flatten(call["messages"][-1].content)
        assert "Payslip summary" not in body or "Applicant annual income" in body
    assert all(g["case_id"] in ("7y", "7z") for job in ("7y", "7z") for g in env.model_gaps(job))


# --- 8. idempotency --------------------------------------------------------------------------------

def test_reading_the_same_document_again_adds_no_gap_or_evidence(gap_env):
    env = gap_env
    folder = env.case("8")
    add(folder, "april", "may")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(STATEMENTS, INCOME))
    env.run("8")

    def snapshot():
        gs = env.model_gaps("8")
        return sorted((g["gap_id"], g["status"], len(g["evidence"]), len(g["history"])) for g in gs)

    first = snapshot()
    env.run("8")
    env.sweep("8")
    env.run("8")
    assert snapshot() == first
    # The same document saved again with a new version (an extra line): its evidence is the same evidence.
    write(folder, *DOCS["april"])
    (folder / DOCS["april"][0]).write_text(DOCS["april"][1] + "\n", encoding="utf-8")
    env.run("8")
    env.sweep("8")
    assert snapshot() == first
    # A request worded slightly differently by the model is the same gap.
    env.precheck = llm.set_fake("precheck", precheck_asking_for({**INCOME, "item": "Applicant annual income."}, STATEMENTS))
    env.run("8")
    assert len(env.model_gaps("8")) == 2


# --- 9. no early verdict -----------------------------------------------------------------------------

def test_only_finalize_case_ever_confirms_a_gap_missing(gap_env):
    # In code: the one call that sets CONFIRMED_MISSING is in finalize_case, and nothing outside
    # gaps.py names the status.
    tree = ast.parse(inspect.getsource(gaps))
    setters = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        for call in [n for n in ast.walk(fn) if isinstance(n, ast.Call)]:
            if getattr(call.func, "id", "") == "set_status" and any(getattr(a, "id", "") == "CONFIRMED" for a in call.args):
                setters.append(fn.name)
    assert setters == ["finalize_case"]
    package = Path(gaps.__file__).parent
    for path in package.glob("*.py"):
        if path.name != "gaps.py":
            assert "CONFIRMED_MISSING" not in path.read_text(encoding="utf-8"), path.name
    # In use: runs and sweeps, however many, never confirm one before the case settles.
    env = gap_env
    folder = env.case("9")
    env.precheck = llm.set_fake("precheck", precheck_asking_for(INCOME, STATEMENTS))
    for n in range(4):
        env.run("9")
        env.sweep("9")
        add(folder, ["april", "may", "checklist", "june"][n])
    assert all(g["status"] != gaps.CONFIRMED for g in gaps.load(Scope.of(env.pm.get_job("9"))).values())
    assert gaps.report(Scope.of(env.pm.get_job("9")))["provisional"] is True
