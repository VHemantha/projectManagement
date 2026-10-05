"""This year's documents checked against last year's accounts, on a folder laid out like a real
one: a zip holding last year's finished pack (…/2025/) next to what arrived this year (…/2026/)."""
import json
import zipfile
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage

from precheck_agent import analysis as A
from precheck_agent import llm
from precheck_agent.config import get_settings
from precheck_agent.directions import normalize_items
from precheck_agent.periods import assign_years, doc_year

from .conftest import write_xlsx

ACCOUNT = "01-0702-0311954-00"
TB = [
    ["Trial Balance"], ["Example Locum Limited"], ["As at 31 March 2025"], [],
    ["Account Code", "Account", "Account Type", "Debit - Year to date", "Credit - Year to date", "31 Mar 2024"],
    [231, "Contract Work", "Revenue", None, 18330, -61250],
    [39401, "Insurance", "Expense", 1255, None, 1255],
    [400, "Accountancy Fees", "Expense", 4366.34, None, 2079.21],
    [413, "Home Office", "Expense", 2912.86, None, 2774.15],
    [437, "Staff Training", "Expense", 26448.22, None, 15901.37],
    [464, "Depreciation - Motor Vehicles", "Expense", 4992.11, None, 7131.59],
    [404, "Bank Charges", "Expense", 102, None, 102],
    [680, "ANZ Business Current Account", "Current Asset", 18479.45, None, 68.56],
    [744, "Motor Vehicles at cost", "Fixed Asset", 50868.7, None, 50868.7],
    [50101, "Shareholder - Capital Introduced", "Non-current Liability", None, 111424.08, -215678.68],
]
DIRECTION_TEXT = [
    "- Prior-year final/signed financial statements and supporting schedules or asset register, if available.",
    "- Annual questionnaire, emails, permanent notes and current-year instructions.",
    "- Bank PDFs, CSVs, available Xero bank-feed information, and balance evidence.",
    "- Loan statements, lender summaries and refinancing documents.",
    "- Property sale and purchase agreements, both parts of settlement documentation, subdivision records",
    "and chattel information.",
    "- Property manager annual summaries or monthly statements.",
    "- Invoices, expense lists, mileage information and other documents in the job folder.",
    "Confirm or record as unknown:",
    "- Entity name and type; accounting firm; start and end of financial year.",
    "- New entity, continuing entity, or existing entity new to AFIT.",
    "- Whether AFIT is preparing the books from source transactions.",
    "- Property addresses; ownership; rental periods; property managers and periods managed.",
    "- Separate bank balance confirmation requirement: Required / Not required / Unknown.",
    "- Evidence of complete bank-feed coverage for each account.",
    "- Accounting firm's approved home office document-request policy.",
    "- Any firm-specific evidence requirements or accounting instructions.",
]


def bank_rows(opening: float, last_day: datetime):
    """A bank export, newest first, starting 1 April 2025 at `opening`."""
    txns = [(datetime(2025, 4, 3), "Direct Credit", "People 2.0 New Z", 8601.98), (datetime(2025, 6, 12), "Bill Payment", "Tower Insurance", -1290.0),
            (datetime(2025, 8, 21), "Direct Credit", "People 2.0 New Z", 3028.23), (datetime(2025, 11, 18), "Tax Payment", "Inland Revenue Gst", -3602.9),
            (datetime(2025, 12, 31), "Bank Fee", "Monthly A/C Fee", -8.5), (last_day, "Direct Credit", "People 2.0 New Z", 76.0)]
    rows, balance = [], opening
    for when, typ, who, amount in txns:
        balance = round(balance + amount, 2)
        rows.append([when, when, typ, who, "", "", "", amount, balance])
    return [["Transaction Date", "Processed Date", "Type", "Details", "Particulars", "Code", "Reference", "Amount", "Balance"]] + rows[::-1]


def two_year_folder(env, name="client-pack", opening=18479.45, last_day=datetime(2026, 2, 27)):
    src = env.tmp / f"{name}-src"
    (src / "2025").mkdir(parents=True)
    (src / "2026").mkdir(parents=True)
    write_xlsx(src / "2025" / "1. Example 2025 - Final TB.xlsx", {"Trial Balance": TB})
    (src / "2025" / "A1. Example 2025 - Bank Balance.txt").write_text(
        f"Statement of Accounts\nAccount number {ACCOUNT}\nStatement period 28 Feb 2025 - 31 Mar 2025 Closing balance 18,479.45\n", encoding="utf-8")
    (src / "2025" / "Example 2025 - Financial Statements - Signed.txt").write_text(
        "Financial Statements\nFor the year ended 31 March 2025\nStatement of Profit or Loss\nTrading Income\nContract Work 18,330 61,250\n"
        "Expenses\nInsurance 1,255 1,255\nAccountancy Fees 4,366 2,079\nTotal Expenses 41,076 46,222\n", encoding="utf-8")
    write_xlsx(src / "2025" / "K2. Example 2025 - Income Reconciliation.xlsx", {"Rec": [["Income reconciliation"], ["Difference", 517.5]]})
    write_xlsx(src / "2026" / f"{ACCOUNT}_Transactions_2025-04-01_2026-03-31.xlsx", {"Transactions": bank_rows(opening, last_day)})
    (src / "2026" / "Tower Insurance renewal 2026.txt").write_text("Tower Insurance\nRenewal notice\nPremium 1,290.00 for the year to 30 June 2026\n", encoding="utf-8")
    folder = env.drive_root / name
    folder.mkdir()
    with zipfile.ZipFile(folder / "Example Locum Limited.zip", "w") as z:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                z.write(path, "Example Locum Limited/" + path.relative_to(src).as_posix())
    return folder


def direction(lines):
    return [{"id": f"D{n}", "text": t} for n, t in enumerate(lines, start=1)]


def test_folders_and_periods_decide_each_documents_year():
    row = lambda name, path="": {"file_id": name, "name": name, "path": path}  # noqa: E731
    assert doc_year(row("TB.xlsx", "Pack.zip/Client/2025/"), {"blocks": []}) == (2025, "folder 2025")
    assert doc_year(row(f"{ACCOUNT}_Transactions_2025-04-01_2026-03-31.xlsx"), {"blocks": []})[0] == 2026
    assert doc_year(row("Accounts.pdf"), {"blocks": [{"text": "Fortheyearended31March2025"}]}) == (2025, "period stated in the document")
    assert doc_year(row("Notes FY24.pdf"), {"blocks": []})[0] == 2024
    assert doc_year(row("Letter.pdf"), {"blocks": []}) == (None, "")
    docs = [{"file": row("a", "x/2025/"), "parsed": {"blocks": []}}, {"file": row("b", "x/2026/"), "parsed": {"blocks": []}},
            {"file": row("c"), "parsed": {"blocks": []}}]
    p = assign_years(docs)
    assert (p["current"], p["prior"], p["split"]) == (2026, 2025, True)
    assert [p["by_file"][k]["role"] for k in "abc"] == ["prior", "current", "unknown"]
    assert assign_years(docs, {"title": "Year end FY27"})["current"] == 2027  # the task's title wins


def test_a_pasted_direction_note_is_put_back_together():
    items = normalize_items(direction(DIRECTION_TEXT))
    texts = [i["text"] for i in items]
    assert len(items) == 15  # 17 lines: one wrapped line joined, one heading folded into its bullets
    assert texts[4] == "Property sale and purchase agreements, both parts of settlement documentation, subdivision records and chattel information."
    assert texts[7] == "Confirm or record as unknown: Entity name and type; accounting firm; start and end of financial year."
    assert not any(t.startswith("- ") or t.endswith(":") for t in texts)
    assert [i["id"] for i in items][:6] == ["D1", "D2", "D3", "D4", "D5", "D7"]  # an item keeps its first line's id


def test_this_year_is_checked_against_last_years_accounts(env):
    two_year_folder(env)
    env.pm.add_job("1", "client-pack", "client-pack", direction=[{"id": "D1", "text": "Bank statements for the year and balance evidence"}])
    result = env.run("1")
    assert result["status"] == "complete" and result["periods"] == {"this_year": 2026, "last_year": 2025, "split": True}
    detail = {d["name"].split(" (in ")[0]: d for d in result["trail"]["read"]["detail"]}
    assert detail["1. Example 2025 - Final TB.xlsx"]["year"] == "last year's pack (FY2025)"
    assert detail["Tower Insurance renewal 2026.txt"]["year"] == "this year (FY2026)"

    # Last year's finished workpapers are the baseline, not something to check again.
    assert not any("unreconciled difference" in f["title"] for f in result["findings"])

    a = result["analysis"]
    assert a["available"] and (a["this_year"], a["last_year"]) == ("FY2026", "FY2025")
    assert a["period"] == "01 Apr 2025 to 31 Mar 2026" and a["baseline"] == ["1. Example 2025 - Final TB.xlsx"]
    lines = {ln["label"]: ln for ln in a["lines"]}
    assert lines["Contract Work"]["last_year"] == 18330 and lines["Contract Work"]["year_before"] == 61250 and lines["Contract Work"]["section"] == "Income"
    assert lines["Insurance"]["status"] == "covered" and any("Tower Insurance" in r["label"] for r in lines["Insurance"]["refs"])
    assert lines["Accountancy Fees"]["status"] == "not_yet"
    assert "Bank Charges" not in lines  # below the amount worth listing

    # Bank export of this year, summarised by code.
    (bank,) = a["bank"]
    assert bank["account"] == ACCOUNT and bank["from"] == "03 Apr 2025" and bank["to"] == "27 Feb 2026" and bank["opening"] == 18479.45
    checks = {c["label"]: c for c in a["checks"]}
    assert checks["This year's opening bank balance equals last year's closing balance"]["passed"] is True
    assert checks["Bank data covers the whole year"]["passed"] is False and "ends 27 Feb 2026" in checks["Bank data covers the whole year"]["detail"]

    # Findings: the checks and what has not arrived, each tied to the documents.
    titles = {f["title"]: f for f in result["findings"]}
    gap = titles["Bank data does not cover the whole year"]
    assert gap["source"] == "rule" and gap["severity"] == "medium" and gap["evidence_ids"]
    waiting = titles["Nothing yet for Staff Training this year"]  # the largest such lines become findings
    ev = {e["id"]: e for e in result["evidence"]}[waiting["evidence_ids"][0]]
    assert ev["file_name"].startswith("1. Example 2025 - Final TB.xlsx") and "Staff Training" in ev["quote"]
    assert "Nothing yet for Accountancy Fees this year" not in titles  # smaller: in the analysis table only
    tb = titles["No trial balance for FY2026 yet"]
    assert tb["severity"] == "medium" and "Last year's" in tb["why"]

    # The model read the compact lists code made, never the documents themselves.
    sent = env.analyst.calls[0]["messages"][-1].content
    payload = json.loads(sent.split("INPUT:")[1])
    assert set(payload) >= {"prior_year_lines", "bank", "current_documents", "checks_by_code"}
    assert "Renewal notice" not in sent and "Statement period" not in sent
    assert [c["node"] for c in result["usage"]["calls"]].count("analysis") == 1

    # Unchanged folder: nothing is asked again.
    calls = len(env.analyst.calls)
    again = env.run("1")
    assert len(env.analyst.calls) == calls and again["analysis"]["how"] == "cache"


def test_an_opening_balance_that_does_not_follow_on_is_a_high_finding(env):
    two_year_folder(env, opening=18000.00, last_day=datetime(2026, 3, 30))
    env.pm.add_job("1", "client-pack", "client-pack", direction=[])
    result = env.run("1")
    f = next(f for f in result["findings"] if f["title"].startswith("Opening bank balance does not match"))
    assert f["severity"] == "high" and f["status"] == "exception" and "18,000.00" in f["why"] and "18,479.45" in f["why"]
    names = {e["file_name"].split(" (in ")[0] for e in result["evidence"] if e["id"] in f["evidence_ids"]}
    assert names == {f"{ACCOUNT}_Transactions_2025-04-01_2026-03-31.xlsx", "A1. Example 2025 - Bank Balance.txt"}
    assert result["verdict"] == "not_ready"
    checks = {c["label"]: c["passed"] for c in result["analysis"]["checks"]}
    assert checks["Bank data covers the whole year"] is True


def test_the_models_answer_is_held_to_code_figures():
    body = json.dumps({"prior_year_lines": [{"id": "P1", "label": "Insurance", "last_year": 1255.0}], "bank": [{"id": "B1", "money_in": 11706.21}]})
    index = {"P1": {"kind": "prior"}, "B1": {"kind": "bank"}}
    raw = {
        "summary": ["Insurance was 1,255 last year.", "Revenue will be about 45,000 this year.", "Money in so far is 11,706.21."],
        "lines": [{"id": "P1", "status": "covered", "refs": ["X9"], "comment": "Paid 1,290 this year.", "question": "Ask about 1,255."},
                  {"id": "P7", "status": "covered", "refs": [], "comment": "", "question": ""}],
        "new_this_year": [{"text": "A new payer.", "refs": ["B1"]}, {"text": "Invented.", "refs": ["Z1"]}],
    }
    clean = A.clean_answer(raw, index, body)
    assert clean["summary"] == ["Insurance was 1,255 last year.", "Money in so far is 11,706.21."]  # 45,000 is not a figure code gave
    line = clean["lines"]["P1"]
    assert line["status"] == "unclear" and line["refs"] == []  # "covered" with no real reference is not trusted
    assert line["comment"] == "" and line["question"] == "Ask about 1,255."
    assert "P7" not in clean["lines"] and [n["text"] for n in clean["new_this_year"]] == ["A new payer."]


def test_statements_read_as_text_give_last_years_lines():
    doc = {"file": {"file_id": "F", "name": "FS.pdf"}, "parsed": {"blocks": [{"text": t, "loc": "page 7"} for t in [
        "Statement of Profit or Loss", "For the year ended 31 March 2025", "2025 2024", "Trading Income", "Contract Work 18,330 61,250",
        "Total Trading Income 18,330 61,250", "Expenses", "ACC Levies - 81", "Accountancy Fees 4,366 2,079", "Page 7 of 15",
        "Current Assets", "ANZ Business Current Account 18,479 69"]]}}
    lines = {ln["label"]: ln for ln in A.statement_lines(doc)}
    assert (lines["Contract Work"]["amount"], lines["Contract Work"]["comparative"], lines["Contract Work"]["section"]) == (18330, 61250, "Income")
    assert lines["ACC Levies"]["amount"] == 0 and lines["Accountancy Fees"]["section"] == "Expenses"
    assert lines["ANZ Business Current Account"]["section"] == "Assets"
    assert "Total Trading Income" not in lines and not any(k.startswith("Page") for k in lines)


def test_a_long_direction_note_is_read_in_full(env):
    two_year_folder(env)
    env.pm.add_job("1", "client-pack", "client-pack", direction=direction(DIRECTION_TEXT))
    result = env.run("1")
    assert result["status"] == "complete" and not result["skipped"]  # every item read, the judge ran
    assert len(result["direction_items"]) == 15
    assert result["usage"]["reader_calls"] >= 15 and result["trail"]["judged"]["how"] == "model"
    s = get_settings()
    assert result["usage"]["totals"]["input"] <= s.budget_max_uncached_input_tokens


def test_items_the_limit_stopped_are_said_to_be_not_checked(env, monkeypatch):
    monkeypatch.setenv("PRECHECK_BUDGET_MAX_READER_CALLS", "2")
    monkeypatch.setenv("PRECHECK_BUDGET_READER_CALLS", "2")
    get_settings.cache_clear()
    two_year_folder(env)
    env.pm.add_job("1", "client-pack", "client-pack", direction=direction(DIRECTION_TEXT))
    result = env.run("1")
    assert result["status"] == "partial"
    not_checked = [f for f in result["findings"] if f["title"].startswith("Not checked in this run")]
    assert not_checked and all("Run the pre-check again" in f["why"] for f in not_checked)
    assert not any(f["title"].startswith("No evidence found") for f in result["findings"])
    assert result["analysis"]["available"]  # the reserve kept room for the analysis


def test_a_reader_can_cite_a_file_being_in_the_folder(env):
    two_year_folder(env)

    def reader(messages, kwargs):
        docs = [b for b in messages[-1].content if isinstance(b, dict) and b.get("type") == "document"]
        listing = len(docs) - 1
        assert docs[listing]["title"].startswith("Files in the task folder")
        names = [b["text"] for b in docs[listing]["source"]["content"]]
        at = next(i for i, n in enumerate(names) if "Tower Insurance renewal" in n)
        cite = {"type": "content_block_location", "cited_text": names[at], "document_index": listing, "document_title": docs[listing]["title"],
                "start_block_index": at, "end_block_index": at + 1}
        return AIMessage(content=[{"type": "text", "text": "addressed|low|Insurance renewal received|The renewal notice is in this year's folder.", "citations": [cite]}],
                         usage_metadata={"input_tokens": 3000, "output_tokens": 40, "total_tokens": 3040})

    env.reader = llm.set_fake("reader", reader)
    env.pm.add_job("1", "client-pack", "client-pack", direction=[{"id": "D1", "text": "Insurance invoices and renewal for the year"}])
    result = env.run("1")
    f = next(f for f in result["findings"] if f["direction_ref"] == "D1")
    assert f["status"] == "addressed"
    ev = {e["id"]: e for e in result["evidence"]}[f["evidence_ids"][0]]
    assert ev["file_name"].startswith("Tower Insurance renewal 2026.txt") and ev["location"] == "file in the task folder"


def test_without_last_years_accounts_the_analysis_says_why(env):
    folder = env.drive_root / "only-this-year"
    folder.mkdir()
    (folder / "Notes.txt").write_text("Client notes for the year\n", encoding="utf-8")
    env.pm.add_job("1", "client-x", "only-this-year", direction=[{"id": "D1", "text": "Read the notes"}])
    result = env.run("1")
    assert result["analysis"] == {"available": False, "reason": result["analysis"]["reason"]}
    assert "No last-year accounts" in result["analysis"]["reason"] and not env.analyst.calls


def test_bank_export_summary_by_code():
    rows = bank_rows(100.0, datetime(2026, 3, 31))
    table = {"name": "T", "rows": [[n, r] for n, r in enumerate(rows, start=1)]}
    doc = {"file": {"file_id": "B", "name": f"{ACCOUNT}_Transactions.xlsx"}, "parsed": {"blocks": [], "tables": [table]}}
    (e,) = A.bank_exports(doc)
    assert (e["account"], e["opening"], e["count"]) == (ACCOUNT, 100.0, 6)
    assert e["money_in"] == round(8601.98 + 3028.23 + 76.0, 2) and e["money_out"] == round(1290.0 + 3602.9 + 8.5, 2)
    top = A.counterparties(e)[0]
    assert top["name"] == "People 2.0 New Z" and top["count"] == 3
    assert e["to"] - e["from"] > timedelta(days=300)
