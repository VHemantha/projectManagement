"""The review: the draft financial statements a preparer drafted, reviewed round after round with
the preparer's assumptions and the reviewer's responses, evidence from the knowledge store, and
code checking every answer."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import llm
from precheck_agent.knowledge import Scope, get_knowledge

from .conftest import write_xlsx

LAST_YEAR = ("Smith Rentals Ltd\nFinancial Statements\nFor the year ended 31 March 2025\nStatement of Profit or Loss\n"
             "Rental income 31,200 29,900\nInterest 14,322 15,010\nRepairs and maintenance 2,140 1,880\n")
DRAFT = ("Smith Rentals Ltd\nDraft Financial Statements\nFor the year ended 31 March 2026\nStatement of Profit or Loss\n"
         "Rental income 33,800 31,200\nInterest 15,900 14,322\nRepairs and maintenance 9,850 2,410\nHome office 1,200 0\n")
INVOICE = "Tax invoice\nKauri Plumbing Ltd\nReplace hot water cylinder at 12 Kauri Street\nTotal 7,420.00\nDate 14 Nov 2025\n"


def review_folder(env, draft=True):
    root = env.drive_root / "smith"
    (root / "2025").mkdir(parents=True)
    (root / "2026").mkdir(parents=True)
    (root / "2025" / "Smith 2025 Financial Statements - Signed.txt").write_text(LAST_YEAR, encoding="utf-8")
    write_xlsx(root / "2025" / "Final TB 2025.xlsx", {"Trial Balance": [
        ["Account Code", "Account", "Account Type", "Debit - Year to date", "Credit - Year to date"], [200, "Rental income", "Revenue", None, 31200]]})
    (root / "2026" / "Client Questionnaire 2026.txt").write_text("Client Questionnaire 2026\nAny repairs this year? Yes, a new hot water cylinder.\n", encoding="utf-8")
    (root / "2026" / "Kauri Plumbing invoice.txt").write_text(INVOICE, encoding="utf-8")
    if draft:
        (root / "2026" / "Smith 2026 Draft Financial Statements.txt").write_text(DRAFT, encoding="utf-8")
    return root


def add_review_job(env, findings=None, assumptions=None):
    env.pm.add_job("1", "client-smith", "smith", direction=[])
    env.pm.jobs["1"]["review"] = {
        "round": 2, "nature": "residential_rental",
        "assumptions": assumptions if assumptions is not None else [
            {"ref": "A1", "area": "Repairs", "fs_line": "Repairs and maintenance", "amount": "9,850",
             "judgement": "The hot water cylinder replacement is a repair, not capital.", "basis": "Like-for-like replacement of a worn part.",
             "evidence": "Kauri Plumbing invoice"}],
        "findings": findings if findings is not None else [
            {"ref": "R1", "status": "closed", "severity": "low", "area": "Presentation", "fs_line": "Rental income", "issue": "Show rent by property.",
             "response": "not_an_issue", "note": "Only one property."},
            {"ref": "R2", "status": "open", "severity": "medium", "area": "Home office", "fs_line": "Home office", "issue": "No basis for the home office claim.",
             "response": "agree", "note": ""}],
    }


def scripted(answer: dict):
    def responder(messages, kwargs):
        return AIMessage(content=json.dumps(answer), usage_metadata={"input_tokens": 12000, "output_tokens": 1800, "total_tokens": 13800},
                         response_metadata={"stop_reason": "end_turn"})
    return responder


def test_a_review_round_reads_the_draft_with_assumptions_feedback_and_evidence(env):
    review_folder(env)
    add_review_job(env)
    result = env.run("1", mode="review")
    assert result["status"] == "complete" and result["mode"] == "review" and len(env.precheck.calls) == 1
    body = env.precheck.calls[0]["messages"][-1].content
    system = env.precheck.calls[0]["messages"][0].content
    assert "# Skill: nz-fs-review" in system and "# Skill: nz-residential-rental" in system
    # The draft line by line with its comparatives; last year's signed statements; the assumption.
    s_lines = [ln.split("  [")[0] for ln in body.splitlines() if ln.startswith("S")]
    assert s_lines == ["S1 | Rental income | Income | this year 33,800.00 | comparative 31,200.00",
                       "S2 | Interest | - | this year 15,900.00 | comparative 14,322.00",
                       "S3 | Repairs and maintenance | - | this year 9,850.00 | comparative 2,410.00",
                       "S4 | Home office | - | this year 1,200.00 | comparative 0.00"]  # not "For the year ended 31 March | 2,026"
    assert "F" in body and "A1 | Repairs | line: Repairs and maintenance" in body
    # Code compared the draft's comparatives with last year's signed statements: one does not agree.
    assert "Comparative for Repairs and maintenance agrees to last year's signed statements | FAILED | draft comparative 2,410.00; last year's statements 2,140.00" in body
    assert "Comparative for Rental income agrees to last year's signed statements | passed" in body
    # Evidence for the assumption came from the knowledge store: the plumber's invoice, not the draft itself.
    e_lines = [ln for ln in body.splitlines() if ln.startswith("E")]
    assert any("Kauri Plumbing" in ln for ln in e_lines) and not any("Draft Financial Statements" in ln for ln in e_lines)
    # The reviewer's responses to earlier findings.
    assert "R1 | closed | low | Presentation" in body and "NOT AN ISSUE (closed) — Only one property." in body
    assert "R2 | open | medium | Home office" in body and "agreed, to be fixed" in body

    review = result["review"]
    assert review["draft_fs"][0]["name"] == "Smith 2026 Draft Financial Statements.txt" and review["draft_found_by"] == "folder"
    assert review["decision"]["state"] == "findings" and result["verdict"] == "not_ready"  # the demo turns the failed check into a high finding
    assert {f["ref"] for f in review["findings"]} >= {"R2"}
    assert review["assumption_reviews"][0]["assumption"] == "A1"


def test_code_holds_the_line_on_the_answer(env):
    review_folder(env)
    add_review_job(env)
    env.precheck = llm.set_fake("precheck", scripted({
        "summary": "Repairs look high; the comparative is wrong.",
        "findings": [
            {"ref": "R1", "area": "Presentation", "fs_line": "Rental income", "issue": "Show rent by property.", "why": "Clearer.", "severity": "low",
             "action": "Split it.", "sources": ["S1"], "assumptions": []},
            {"ref": "", "area": "Comparatives", "fs_line": "Repairs and maintenance", "issue": "The comparative 2,410 does not agree to last year's 2,140.",
             "why": "Opening figures must agree to the signed statements.", "severity": "high", "action": "Correct the comparative.",
             "sources": ["C1", "S99"], "assumptions": []},
            {"ref": "R9", "area": "Repairs", "fs_line": "Repairs and maintenance", "issue": "Repairs of 12,345 look capital.", "why": "Large.",
             "severity": "superbad", "action": "Check.", "sources": [], "assumptions": ["A1", "A7"]},
        ],
        "resolved": [{"ref": "R2", "reason": "Home office removed.", "sources": ["S1"]}, {"ref": "R1", "reason": "x", "sources": []}],
        "assumption_reviews": [{"assumption": "A1", "verdict": "challenged", "reason": "A new cylinder is a replacement of the whole asset.", "sources": ["E1"]},
                               {"assumption": "A9", "verdict": "supported", "reason": "x", "sources": []}],
        "lessons_applied": [],
    }))
    review = env.run("1", mode="review")["review"]
    by_issue = {f["issue"]: f for f in review["findings"]}
    assert "Show rent by property." not in by_issue  # R1 was closed by the reviewer: never raised again
    comp = by_issue["The comparative 2,410 does not agree to last year's 2,140."]
    assert comp["ref"] == "" and [s["id"] for s in comp["sources"]] == ["C1"] and comp["flags"] == []  # S99 does not exist
    capital = by_issue["Repairs of 12,345 look capital."]
    assert capital["ref"] == "" and capital["severity"] == "medium" and capital["assumptions"] == ["A1"]  # R9 is not ours; A7 does not exist
    assert capital["flags"] == ["no_source", "figure_not_in_documents"]  # 12,345 is not in the input
    assert [r["ref"] for r in review["resolved"]] == ["R2"]
    assert [a["assumption"] for a in review["assumption_reviews"]] == ["A1"] and review["assumption_reviews"][0]["verdict"] == "challenged"
    assert review["findings"][0]["severity"] == "high"  # most severe first
    evidence = review["evidence"][comp["sources"][0]["evidence_id"]]
    assert evidence["file_name"].startswith("Smith 2026 Draft Financial Statements.txt")


def test_the_knowledge_store_holds_the_review_with_the_cards_tags(env):
    review_folder(env)
    add_review_job(env)
    env.run("1", mode="review")
    scope = Scope.of(env.pm.jobs["1"])
    kn = get_knowledge()
    kinds = {e["source_type"] for e in kn.get(scope, source_types=["assumption", "finding", "feedback"])}
    assert kinds == {"assumption", "finding", "feedback"}
    a = kn.get(scope, source_types=["assumption"])[0]
    assert (a["team"], a["vendor"], a["project"], a["task"], a["ref"]) == ("team-1", "client-smith", "project-client-smith", "1", "A1")
    # The next round replaces what the task held, so a withdrawn assumption is gone.
    env.pm.jobs["1"]["review"]["assumptions"] = []
    env.run("1", mode="review")
    assert kn.get(scope, source_types=["assumption"]) == []


def test_without_a_draft_there_is_nothing_to_review(env):
    review_folder(env, draft=False)
    add_review_job(env, findings=[], assumptions=[])
    review = env.run("1", mode="review")["review"]
    assert review["decision"]["state"] == "blocked" and "No draft financial statements" in review["decision"]["reason"]
    assert not env.precheck.calls


def test_the_task_card_can_say_where_the_draft_is_and_an_unchanged_round_is_not_paid_again(env):
    root = review_folder(env, draft=False)
    (root / "2026" / "Working version.txt").write_text(DRAFT, encoding="utf-8")
    add_review_job(env, findings=[], assumptions=[])
    env.pm.jobs["1"]["key_paths"] = {"draft_fs": "2026/Working version.txt"}
    review = env.run("1", mode="review")["review"]
    assert review["draft_found_by"] == "task card" and review["draft_fs"][0]["name"] == "Working version.txt"
    again = env.run("1", mode="review")
    assert len(env.precheck.calls) == 1 and again["review"]["how"] == "cache"


def test_found_in_the_real_opus_round_on_12_oct_2026():
    """A balance sheet line is never income or an expense whatever its label says ("Chattels at
    cost less depreciation" was shown as an expense, and the model reported it as the preparer's
    mistake); and an amount from the firm's skills (the $1,000 low-value threshold) is not invented."""
    from precheck_agent import review as RV
    from precheck_agent.analysis import statement_lines

    blocks = [{"text": t, "loc": "x"} for t in ("Statement of Financial Performance", "Depreciation - chattels 950 1,120",
                                                 "Statement of Financial Position", "Chattels at cost less depreciation 4,650 5,600")]
    sections = {ln["label"]: ln["section"] for ln in statement_lines({"file": {}, "parsed": {"blocks": blocks}})}
    assert sections == {"Depreciation - chattels": "Expenses", "Chattels at cost less depreciation": ""}

    raw = {"summary": "", "resolved": [], "assumption_reviews": [], "lessons_applied": [], "findings": [
        {"ref": "", "area": "Repairs", "fs_line": "Repairs", "issue": "A payment over $1,000 needs an invoice.", "why": "Low-value threshold.",
         "severity": "low", "action": "Get the invoice.", "sources": ["S1"], "assumptions": []}]}
    index = {"S1": {"kind": "draft"}}
    assert RV.clean(raw, index, "S1 | Repairs 2,000", [])["findings"][0]["flags"] == ["figure_not_in_documents"]
    assert RV.clean(raw, index, "S1 | Repairs 2,000\n" + RV.system_text("residential_rental"), [])["findings"][0]["flags"] == []
