"""Which year each document belongs to, and what code works out from last year's accounts and this year's bank, on a folder laid out like a real
one: a zip holding last year's finished pack (…/2025/) next to what arrived this year (…/2026/)."""
import zipfile
from datetime import datetime, timedelta

from precheck_agent import analysis as A
from precheck_agent import llm
from precheck_agent.directions import normalize_items
from precheck_agent.periods import assign_years, doc_year

from .conftest import write_xlsx
from .test_precheck import scripted

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
    (src / "2026" / "Client Questionnaire 2026.txt").write_text("Client questionnaire\nAny changes this year? No.\n", encoding="utf-8")
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


def test_the_checks_code_can_answer_reach_the_precheck(env):
    """This year's opening bank balance against last year's closing balance, and whether the bank
    data covers the year: worked out by code and given to the pre-check as C lines."""
    two_year_folder(env, opening=18000.00, last_day=datetime(2026, 2, 27))
    env.pm.add_job("1", "client-pack", "client-pack", direction=[])
    result = env.run("1")
    body = env.precheck.calls[0]["messages"][-1].content
    assert "| This year's opening bank balance equals last year's closing balance | FAILED | " in body and "18,000.00" in body and "18,479.45" in body
    assert "| Bank data covers the whole year | FAILED | " in body and "ends 27 Feb 2026" in body
    assert f"B1 | {ACCOUNT} | 03 Apr 2025 to 27 Feb 2026 | opening 18,000.00" in body
    assert "T1 | Contract Work | Revenue | -18,330.00 | year before -61,250.00" in body
    checks = {c["label"]: c["passed"] for c in result["precheck"]["checks"]}
    assert checks["This year's opening bank balance equals last year's closing balance"] is False
    # Last year's finished workpaper with a difference is the baseline, not something to check again.
    assert not any("unreconciled difference" in c["label"] for c in result["trail"]["checked"]["detail"])


def test_an_item_citing_a_code_check_links_to_the_bank_line(env):
    two_year_folder(env, opening=18000.00, last_day=datetime(2026, 2, 27))
    env.pm.add_job("1", "client-pack", "client-pack", direction=[])
    env.precheck = llm.set_fake("precheck", scripted({
        "business_nature": {"type": "general", "summary": "Contracting.", "reasoning": "T1.", "sources": ["T1"], "facts": []},
        "items": [{"group": "Bank", "item": "March 2026 bank statement", "decision": "request",
                   "reason": "The bank data ends 27 Feb 2026, a month before year end.", "sources": ["C2"], "documents": []}],
        "preparer_notes": [], "lessons_applied": []}))
    p = env.run("1")["precheck"]
    src = p["requests"][0]["sources"][0]
    assert src["label"].startswith("Check: ") and p["evidence"][src["evidence_id"]]["file_name"].startswith(ACCOUNT)


def test_this_years_questionnaire_names_the_year():
    """Landm, 6 Oct 2026: only this year's documents, a questionnaire "QD--FY2026--…", and a loan
    statement with debit and credit columns. The statement is a bank document, not a trial
    balance (which would read as finished accounts and push this year to FY2027)."""
    from precheck_agent.classify import classify

    statement = "ORBIT Home Loan\nAccount Number: 12-3026-0117614-00\nFrom Date: 01 Apr 2025\nTo Date: 02 Oct 2025\nDate Description Debit Credit Balance"
    assert classify("ITA statement to 2 Oct.pdf", statement) == "bank"

    def doc(name, path, cls):
        return {"file": {"file_id": name, "name": name, "path": path, "document_class": cls}, "parsed": {"blocks": []}}

    docs = [doc("QD--FY2026--Landm Ltd-Meredith Bates.pdf", "2026/Documents/", "questionnaire"),
            doc("Rates.pdf", "2026/Rates/", "other_evidence"), doc("Final TB.xlsx", "2026/", "trial_balance")]
    periods = assign_years(docs, {"title": "Landm Ltd year end"})
    assert periods["current"] == 2026 and periods["by_file"]["QD--FY2026--Landm Ltd-Meredith Bates.pdf"]["role"] == "current"
    # Last year's questionnaire left beside this year's bank data does not move the year back.
    old = [doc("Client Questionnaire 2025.pdf", "2025/", "questionnaire"), doc("Bank 2026.csv", "2026/", "bank")]
    assert assign_years(old, {"title": "x"})["current"] == 2026
