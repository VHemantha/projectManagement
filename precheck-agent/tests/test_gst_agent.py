"""The WP Agent's GST reconciliation (AFIT, 8 Nov 2026), on a job built to the specification's acceptance
scenarios: a March return paid in May, prior-year arrears partly settled, a GST payment coded to
income tax, one correction in a journal and a late claim ($150, not $300), part-paid and zero-rated
debtors, a PAYE creditor, import GST matched to its return, a missing GST column (pause, then GL
analysis), invoice and hybrid basis, a missing return, and an unchanged rerun.

Expected bridge: A 2,500 (March return 2,000 + prior-year arrears 500) + B 450 - C 225 + D (-150)
= E 2,575; reported GL 4,475 less the 1,900 reclassification = F 2,575; unexplained nil."""
import base64
import io
import json
from datetime import date
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage
from openpyxl import load_workbook

from precheck_agent import llm, runner
from precheck_agent.gst import engine as E
from precheck_agent.gst.money import amount, day, gst_due_date

from .conftest import write_xlsx

D = Decimal
PRIOR_YEAR = {"balance_date": "2025-03-31", "gl_gst_balance": "1500.00", "ird_outstanding": "1500.00",
              "unpaid_returns": [{"period_end": "2025-03-31", "amount": "1,500.00", "source": "page 1"}], "timing_items": [], "unresolved": []}

RETURNS = [["Period start", "Period end", "Version", "Date filed", "Box 5", "Box 8", "Box 9", "Box 11", "Box 12", "Box 13", "Box 15"],
           ["01/04/2025", "31/05/2025", "Original", "25/06/2025", 23000, 3000, 0, 7666.67, 1000, 0, 2000],
           ["01/06/2025", "31/07/2025", "Original", "27/08/2025", 26833.33, 3500, 0, 9200, 1200, 0, 2300],
           ["01/08/2025", "30/09/2025", "Original", "27/10/2025", 21466.67, 2800, 0, 6900, 900, 0, 1900],
           ["01/10/2025", "30/11/2025", "Original", "10/01/2026", 23766.67, 3100, 0, 8433.33, 1100, 0, 2000],
           ["01/12/2025", "31/01/2026", "Original", "26/02/2026", 19933.33, 2600, 0, 6133.33, 800, 0, 1800],
           ["01/02/2026", "31/03/2026", "Original", "05/05/2026", 25300, 3300, 0, 9966.67, 1300, 0, 2000]]
IRD = [["Date", "Effective date", "Transaction type", "Period", "Debit", "Credit", "Reference"],
       ["07/05/2025", "07/05/2025", "Payment", "31/03/2025", None, 1000, "PAY-0507"],
       ["10/06/2025", "10/06/2025", "Late payment penalty", "31/03/2025", 50, None, ""],
       ["25/06/2025", "25/06/2025", "GST return", "31/05/2025", 2000, None, ""],
       ["26/06/2025", "26/06/2025", "Payment", "31/05/2025", None, 2000, "PAY-0626"],
       ["27/08/2025", "27/08/2025", "GST return", "31/07/2025", 2300, None, ""],
       ["28/08/2025", "28/08/2025", "Payment", "31/07/2025", None, 2300, "PAY-0828"],
       ["27/10/2025", "27/10/2025", "GST return", "30/09/2025", 1900, None, ""],
       ["28/10/2025", "28/10/2025", "Payment", "30/09/2025", None, 1900, "PAY-1028"],
       ["10/01/2026", "10/01/2026", "GST return", "30/11/2025", 2000, None, ""],
       ["15/01/2026", "15/01/2026", "Payment", "30/11/2025", None, 2000, "PAY-0115"],
       ["26/02/2026", "26/02/2026", "GST return", "31/01/2026", 1800, None, ""],
       ["27/02/2026", "27/02/2026", "Payment", "31/01/2026", None, 1800, "PAY-0227"],
       ["05/05/2026", "05/05/2026", "GST return", "31/03/2026", 2000, None, ""],
       ["07/05/2026", "07/05/2026", "Payment", "31/03/2026", None, 2000, "PAY-0507B"]]
TB = [["Code", "Account", "Debit", "Credit"],
      [610, "Accounts Receivable", 4250, None], [800, "Accounts Payable", None, 2625], [820, "GST", None, 4475],
      [830, "Income Tax Payable", 1900, None], [200, "Sales", None, 150000], [None, "Total", 6150, 6150]]
GL = [["Date", "Account", "Description", "Reference", "Debit", "Credit", "GST", "Tax Rate"],
      ["07/05/2025", "820 - GST", "GST payment to IRD", "PAY-0507", 1000, None, None, ""],
      ["26/06/2025", "820 - GST", "GST payment to IRD", "PAY-0626", 2000, None, None, ""],
      ["28/08/2025", "820 - GST", "GST payment to IRD", "PAY-0828", 2300, None, None, ""],
      ["28/10/2025", "830 - Income Tax Payable", "IRD payment", "PAY-1028", 1900, None, None, ""],
      ["15/01/2026", "820 - GST", "GST payment to IRD", "PAY-0115", 2000, None, None, ""],
      ["27/02/2026", "820 - GST", "GST payment to IRD", "PAY-0227", 1800, None, None, ""],
      ["10/02/2026", "820 - GST", "Import GST - NZ Customs entry 123", "NZCS-123", 300, None, None, "GST on Imports"],
      ["01/03/2026", "800 - Accounts Payable", "Supplies", "BILL-77", None, 1150, None, ""],
      ["01/03/2026", "400 - Purchases", "Supplies", "BILL-77", 1000, None, 150, "15% GST on Expenses"],
      ["05/03/2026", "800 - Accounts Payable", "Power", "BILL-78", None, 575, None, ""],
      ["05/03/2026", "410 - Power", "Power", "BILL-78", 500, None, 75, "15% GST on Expenses"],
      ["20/03/2026", "800 - Accounts Payable", "Inland Revenue PAYE March", "PAYE-03", None, 900, None, ""]]
AR = [["Invoice Date", "Invoice Number", "Contact", "Total", "GST"],
      ["10/03/2026", "INV-3001", "Alpha Ltd", 2300, 300], ["20/03/2026", "INV-3002", "Beta Ltd", 1150, 150],
      ["25/03/2026", "INV-3003", "Export Co", 800, 0], ["", "Total", "", 4250, 450]]
AP = [["Invoice Date", "Invoice Number", "Contact", "Total", "GST"],
      ["01/03/2026", "BILL-77", "Supplies Ltd", 1150, 150], ["05/03/2026", "BILL-78", "Power Co", 575, 75],
      ["20/03/2026", "PAYE-03", "Inland Revenue PAYE", 900, 0], ["", "Total", "", 2625, 225]]
AP_NO_GST = [[r[0], r[1], r[2], r[3]] for r in AP]
JOURNALS = [["Journal Number", "Date", "Created", "Account", "Description", "Debit", "Credit"],
            ["45", "20/03/2026", "20/05/2026", "GST", "Missed input GST INV-2045 Kiwi Supplies", 150, None],
            ["45", "20/03/2026", "20/05/2026", "Purchases", "Missed input GST INV-2045 Kiwi Supplies", None, 150]]
LATE = [["Date", "Reference", "Contact", "Description", "GST", "Type", "Return period"],
        ["18/03/2026", "INV-2045", "Kiwi Supplies", "Late claim - packaging", 150, "Purchases", "31/05/2026"],
        ["10/02/2026", "NZCS-123", "NZ Customs", "Import GST", 300, "Purchases", "31/03/2026"]]
SETUP = {"entity": "Acme Trading Ltd", "balance_date": "2026-03-31", "fy_start": "2025-04-01", "basis": "payments", "frequency": "two_monthly",
         "ird_number": "123-456-789", "gst_accounts": ""}


def build_folder(root, name="acme-gst", **over):
    folder = root / name
    folder.mkdir()
    sheets = {"GST Returns FY26.xlsx": RETURNS, "IRD GST statement.xlsx": IRD, "Trial Balance 31 March 2026.xlsx": TB, "General Ledger.xlsx": GL,
              "Aged Receivables Detail.xlsx": AR, "Aged Payables Detail.xlsx": AP, "Journal Report.xlsx": JOURNALS, "GST late claims May 2026.xlsx": LATE}
    sheets.update(over)
    for file_name, rows in sheets.items():
        if rows is not None:
            write_xlsx(folder / file_name, {"Report": rows})
    (folder / "Prior year GST reconciliation FY25.txt").write_text("GST reconciliation at 31 March 2025\nGST per GL 1,500.00\n"
                                                                    "Return 31/03/2025 unpaid 1,500.00\n", encoding="utf-8")
    return folder


def prior_year_reader(messages, kwargs):
    """The model reading last year's reconciliation; everything else as the demo model (nothing)."""
    body = llm._flatten(messages[-1].content)
    if "last year's GST reconciliation" in body:
        return AIMessage(content=json.dumps(PRIOR_YEAR), usage_metadata={"input_tokens": 500, "output_tokens": 80, "total_tokens": 580})
    return llm.demo_gst(messages, kwargs)


@pytest.fixture
def gst_job(env):
    build_folder(env.drive_root)
    env.pm.add_job("301", "client-acme", "acme-gst")
    llm.set_fake("gst", prior_year_reader)
    return "301"


def run(job_id, link="local://acme-gst", setup=None, **options):
    return runner.execute(runner.new_run_id(), job_id, "gst", {"drive_link": link, "setup": {**SETUP, **(setup or {})}, **options})


def test_money_and_due_dates():
    assert amount("(1,234.56)") == D("-1234.56") and amount("1,234.56 CR") == D("-1234.56") and amount("-") is None and amount("$2,000") == D(2000)
    assert day("07/05/2026") == date(2026, 5, 7) and day("2026-03-31") == date(2026, 3, 31)
    assert gst_due_date(date(2026, 3, 31)) == date(2026, 5, 7) and gst_due_date(date(2025, 11, 30)) == date(2026, 1, 15)
    assert gst_due_date(date(2026, 1, 31)) == date(2026, 2, 28)


def test_the_reconciliation_follows_the_acceptance_scenarios(env, gst_job):
    final = run(gst_job)
    assert final["status"] == "complete", final
    g = final["gst"]
    b = g["bridge"]
    assert (b["A"], b["A_current"], b["A_prior"], b["B"], b["C"], b["D"], b["E"]) == ("2500.00", "2000.00", "500.00", "450.00", "225.00", "-150.00", "2575.00")
    assert (b["reported"], b["corrections"], b["F"], b["unexplained"]) == ("4475.00", "-1900.00", "2575.00", "0.00")
    assert g["status"] == "Reconciled subject to corrections" and final["verdict"] == "ready_with_exceptions"
    # March return paid in May: outstanding at 31 March, the payment shown apart.
    march = next(p for p in g["periods"] if p["period_end"] == "2026-03-31")
    assert (march["outstanding_bd"], march["settled_after"], march["paid_at_bd"]) == ("2000.00", "-2000.00", "No")
    assert march["standing"] == "not yet due at balance date"
    # Prior-year arrears partly settled: only the unpaid 500 carried; the penalty isn't GST principal.
    arrears = next(p for p in g["periods"] if p["period_end"] == "2025-03-31")
    assert arrears["outstanding_bd"] == "500.00" and arrears["origin"] == "prior_year"
    # GST payment coded to income tax: a proposed reclassification, not a timing item.
    (fix,) = g["corrections"]
    assert fix["title"] == "GST payment debited to income tax" and fix["status"] == "proposed — not posted"
    assert [(ln["account"], ln["debit"], ln["credit"]) for ln in fix["lines"]] == [("GST", "1900.00", "0.00"), ("Income Tax Payable", "0.00", "1900.00")]
    # One correction in a journal and a late claim: one $150 adjustment with both as evidence.
    (adj,) = g["adjustments"]
    assert adj["effect"] == "-150.00" and len(adj["journals"]) == 1 and len(adj["late_claims"]) == 1 and adj["subsequent_return"] == "2026-05-31"
    assert adj["category"] == "Expenses not claimed"
    # Import GST matched to the return: no adjustment.
    (imp,) = g["imports"]["items"]
    assert imp["finding"] == "Correctly recorded in both GL and return"
    assert g["counts"]["blocking"] == 0
    assert final["usage"]["model_calls"] >= 1 and "nz-gst-reconciliation" in final["versions"]["skills"]
    assert env.pm.completed()[-1]["result"]["mode"] == "gst"

    wb = load_workbook(io.BytesIO(base64.b64decode(final["workbook_b64"])))
    assert wb.sheetnames == ["L1 GST reconciliation", "Summary", "L1.1 Returns & settlements", "Opening items", "G1 Receivables GST",
                             "M1 Payables GST", "Import GST", "Journals & late claims", "Payment matching", "Proposed corrections",
                             "Period analysis", "Exceptions & evidence", "Sources"]
    l1 = wb["L1 GST reconciliation"]
    cells = {str(c.value): c.coordinate for row in l1.iter_rows() for c in row if c.value is not None}
    for label in ("GST return information", "GST ledger information", "Timing differences", "Adjustments required", "Accounts receivable per",
                  "Accounts payable per", "GST returns still outstanding at balance date", "Income not declared", "Expenses not claimed",
                  "Entertainment adjustment", "Total adjustments", "Ledger totals", "Variance", "Paid/rec'd @ bal date"):
        assert label in cells, label
    assert l1[cells["Accounts receivable per"].replace("A", "J")].value == 450
    assert l1[cells["Accounts payable per"].replace("A", "J")].value == -225
    assert str(l1["J12"].value).startswith("=(G12+H12+I12)-(C12+D12+E12)")  # (payment)/refund, as the template shows it
    m1 = [[c.value for c in r] for r in wb["M1 Payables GST"].iter_rows(min_row=4)]
    paye = next(r for r in m1 if r[1] == "PAYE-03")
    assert paye[7] == "No" and "PAYE" in paye[8]


def test_a_missing_gst_column_pauses_that_side_then_gl_analysis(env, gst_job):
    (env.drive_root / "acme-gst" / "Aged Payables Detail.xlsx").unlink()
    write_xlsx(env.drive_root / "acme-gst" / "Aged Payables Detail.xlsx", {"Report": AP_NO_GST})
    paused = run(gst_job)["gst"]
    assert paused["status"] == "Incomplete evidence"
    assert paused["paused"]["ap"]["message"].startswith("Please re-upload the ageing report with the GST column")
    assert "The uploaded Accounts Payable ageing report does not include the GST attributable" in paused["paused"]["ap"]["message"]
    assert "ar" not in paused["paused"] and paused["bridge"]["B"] == "450.00" and paused["bridge"]["C"] == "0.00"  # checked independently; not zero GST

    gl = run(gst_job, choices={"ap_gl_fallback": True})["gst"]
    assert gl["bridge"]["C"] == "225.00" and gl["payables"]["source"] == "general ledger analysis (fallback)"
    assert gl["payables"]["categories"]["non-GST liability"] == "0.00"
    assert gl["status"] == "Reconciled subject to corrections"


def test_zero_gst_column_is_not_a_missing_column(env, gst_job):
    rows = [AR[0]] + [[r[0], r[1], r[2], r[3], 0] for r in AR[1:-1]]
    (env.drive_root / "acme-gst" / "Aged Receivables Detail.xlsx").unlink()
    write_xlsx(env.drive_root / "acme-gst" / "Aged Receivables Detail.xlsx", {"Report": rows})
    g = run(gst_job)["gst"]
    assert "ar" not in g["paused"] and g["bridge"]["B"] == "0.00"


@pytest.mark.parametrize("basis,b_,c_", [("invoice", "0.00", "0.00"), ("hybrid", "0.00", "225.00")])
def test_invoice_and_hybrid_basis(env, gst_job, basis, b_, c_):
    g = run(gst_job, setup={"basis": basis})["gst"]
    assert (g["bridge"]["B"], g["bridge"]["C"]) == (b_, c_)
    assert g["receivables"]["identified"] == "450.00"  # still shown as evidence


def test_a_missing_return_is_incomplete_evidence(env):
    build_folder(env.drive_root, "acme-missing", **{"GST Returns FY26.xlsx": RETURNS[:-1]})
    env.pm.add_job("302", "client-acme", "acme-missing")
    llm.set_fake("gst", prior_year_reader)
    g = run("302", link="local://acme-missing")["gst"]
    assert g["status"] == "Incomplete evidence"
    assert any(x["code"] == "missing_return" and "31/03/2026" in x["text"] for x in g["exceptions"])


def test_an_unchanged_rerun_gives_the_same_totals_and_ids(env, gst_job):
    one, two = run(gst_job)["gst"], run(gst_job)["gst"]
    assert one["bridge"] == two["bridge"]
    assert [a["id"] for a in one["adjustments"]] == [a["id"] for a in two["adjustments"]]
    assert [c["id"] for c in one["corrections"]] == [c["id"] for c in two["corrections"]]


def test_a_bad_link_fails_plainly(env, gst_job):
    final = run(gst_job, link="https://example.com/not-drive")
    assert final["status"] == "failed" and "isn't a Google Drive folder or file link" in final["reason"]


# --- the duplicate check, on its own ---------------------------------------------------------------------

def _recon():
    su = E.Setup(entity="X", balance_date=date(2026, 3, 31), fy_start=date(2025, 4, 1))
    return E.Recon(su, E.Data())


def _journal(jid, effect, desc):
    return {"id": f"J-{jid}", "kind": "journal", "journal": jid, "date": date(2026, 3, 20), "effect": D(effect), "direction": "output" if D(effect) > 0 else "input",
            "description": desc, "ref": "", "contact": "", "source": f"journal {jid}"}


def _late(lid, gst, ref, contact="", side="input"):
    return {"id": f"LC-{lid}", "kind": "late_claim", "date": date(2026, 3, 18), "ref": ref, "contact": contact, "description": "", "gst": D(gst),
            "direction": side, "return_period_end": date(2026, 5, 31), "source": f"late {lid}"}


def test_journal_and_late_claim_are_one_adjustment_whatever_the_order():
    j, lc = _journal("45", "-150", "Missed input GST INV-2045"), _late("1", "150", "INV-2045")
    a = _recon().adjustments([j], [lc])
    b = _recon().adjustments([j], [lc][::-1])
    assert [x["effect"] for x in a] == [D("-150.00")] and a[0]["id"] == b[0]["id"]


def test_a_part_match_includes_only_the_unmatched_part_once():
    (adj,) = _recon().adjustments([_journal("46", "-150", "INV-2046 adjustment")], [_late("2", "200", "INV-2046")])
    assert adj["effect"] == D("-200.00") and adj["unmatched"] == D("50.00") and adj["review"]


def test_an_equal_amount_alone_is_not_a_duplicate():
    r = _recon()
    out = r.adjustments([_journal("47", "-150", "Year end GST adjustment")], [_late("3", "150", "INV-9999", contact="Other Ltd")])
    assert sorted(x["effect"] for x in out) == [D("-150.00"), D("-150.00")]
    assert any(x["code"] == "possible_duplicate" for x in r.exceptions)


def test_one_journal_can_match_several_late_claims():
    out = _recon().adjustments([_journal("48", "-300", "Late GST INV-1 and INV-2")], [_late("4", "100", "INV-1"), _late("5", "200", "INV-2")])
    (adj,) = out
    assert adj["effect"] == D("-300.00") and len(adj["late_claims"]) == 2 and not adj["unmatched"]


def test_import_gst_only_in_the_gl_is_a_reconciling_item():
    su = E.Setup(entity="X", balance_date=date(2026, 3, 31), fy_start=date(2025, 4, 1))
    data = E.Data(gl=[{"id": "S1:9", "account": "GST", "code": "", "date": date(2026, 2, 10), "source_type": "", "contact": "NZ Customs",
                       "description": "GST on imports entry 555", "ref": "NZCS-555", "debit": D(400), "credit": D(0), "gross": None, "gst": None,
                       "tax_code": "", "source": "S1 row 9"}], has_return_detail=True)
    r = E.Recon(su, data)
    ledger = {"gst_accounts": ["GST"]}
    imports = r.import_gst(ledger, set(), set())
    (item,) = imports["items"]
    assert item["finding"] == "Recorded in GL but not in the return"
    (adj,) = r.import_corrections(imports, ledger)
    assert adj["effect"] == D("-400.00") and adj["review"]


def test_no_import_gst_means_no_adjustment():
    r = _recon()
    imports = r.import_gst({"gst_accounts": ["GST"]}, set(), set())
    assert imports["items"] == [] and "no adjustment" in imports["note"]


def test_what_is_saved_fits_the_pm_applications_columns(env, gst_job):
    """AFIT Connect keeps each call's node in 20 characters and the prompt version in 40 (Postgres
    refuses longer values: a run's result was lost that way on 9 Nov 2026)."""
    final = run(gst_job)
    assert len(final["versions"]["prompt"]) <= 40 and len(final["readiness"]) <= 40
    assert final["usage"]["calls"] and all(len(c["node"]) <= 20 and len(c["task_id"]) <= 80 for c in final["usage"]["calls"])


# --- the real export layouts (Xero and myIR, as uploaded on 9 Nov 2026) ----------------------------------------

def _titled(title, header, rows, header_row=5):
    """A report as Xero/myIR export it: title lines, a blank line, the headings, then the rows."""
    top = [[title], ["Jaw Stone Two Limited"], ["As at 31 March 2026"], ["Ageing by due date"], []][: header_row - 1]
    return top + [header] + rows


REAL = {
    "Client - 2026 GST Return Summary Report.xlsx": [["Account ID:", "134-433-612-GST003"], ["Name:", "CLIENT LIMITED"], ["From:", "2025-04-01"],
        ["To:", "2026-03-31"], [], ["Disclaimer: This information may not include everything"], [],
        ["Period ending", "Total sales", "Zero-rated supplies", "Debit adjustments", "Total GST collected", "Total expenses", "Credit adjustments",
         "Total GST paid", "Payment / Refund"],
        [date(2025, 9, 30), 11500, 0, 100, 1500, 3833.33, 0, 500, 1000],
        [date(2026, 3, 31), 15333.33, 0, 0, 2000, 6133.33, 0, 800, 1200]],
    "Client - 2026 GST Transaction Summary Report.xlsx": [["Account ID:", "134-433-612-GST003"], ["Name:", "CLIENT LIMITED"], [], [], [], [], [],
        ["Period ending", "Account type", "Date", "Transaction", "Amount"],
        [date(2025, 9, 30), "GST", date(2025, 10, 28), "Assessment", 1000],
        [date(2025, 9, 30), "GST", date(2025, 10, 28), "Transfer from 134-433-612-INC001", -400],
        [date(2025, 9, 30), "GST", date(2025, 10, 29), "Payment", -600],
        [date(2026, 3, 31), "GST", date(2026, 5, 7), "Assessment", 1200],
        [date(2026, 3, 31), "Income Tax", date(2026, 5, 7), "Payment", -999],
        [date(2026, 3, 31), "GST", date(2026, 5, 8), "Payment", -1200]],
    "Client_-_Aged_Receivables_Summary.xlsx": _titled("Aged Receivables Summary",
        ["Contact", "Current", "< 1 Month", "1 Month", "2 Months", "3 Months", "Older", "Total", "Outstanding GST"],
        [[], ["Aged Receivables"], ["Alpha Ltd", 1150, 0, 0, 0, 0, 0, 1150, 150], ["Beta Ltd", 2300, 0, 0, 0, 0, 0, 2300, 300],
         ["Total Aged Receivables", 3450, 0, 0, 0, 0, 0, 3450, 450]], header_row=6),
    "Client_-_Aged_Payables_Summary.xlsx": _titled("Aged Payables Summary",
        ["Contact", "Current", "< 1 Month", "1 Month", "2 Months", "3 Months", "Older", "Total", "Outstanding GST"],
        [[], ["Aged Payables"], ["Bizphones", 74.75, 0, 0, 0, 0, 0, 74.75, 9.75], ["Payroll - A-Temp Recruitment", 35339.87, 0, 0, 0, 0, 0, 35339.87, 0],
         ["Total Aged Payables", 35414.62, 0, 0, 0, 0, 0, 35414.62, 9.75]], header_row=6),
    "Client_-_Trial_Balance.xlsx": [["Trial Balance"], ["Client"], ["As at 31 March 2026"], [],
        ["Account Code", "Account", "Account Type", "Debit - Year to date", "Credit - Year to date"],
        [610, "Accounts Receivable", "Current Asset", 3450, None], [800, "Accounts Payable", "Current Liability", None, 35414.62],
        [820, "GST", "Current Liability", None, 1590.25], [230, "Contracting Income", "Sales", None, 100000]],
    "Client_-_Journal_Report.xlsx": [["Journal Report"], ["Client"], ["For the period 1 April 2025 to 31 March 2026"], [],
        ["Date", "Journal ID", "Account Code", "Account", "Debit", "Credit", "Posted Date", "Posted By"], [],
        ["ID 29061 Missed GST INV-77 Kiwi Packaging"],
        [date(2026, 3, 20), 29061, 820, "GST", 50, 0, "2026-06-01 10:15:00.12", "Contractor One"],
        [date(2026, 3, 20), 29061, 400, "Purchases", 0, 50, "2026-06-01 10:15:00.12", "Contractor One"],
        ["Total", None, None, None, 50, 50]],
}
LATER_RETURN = {
    "Return": [["GST return", None, "Filed"], ["Client Limited"], ["134-433-612"], [], ["For the period 1 April 2026 to 31 May 2026"], [],
               ["GST to pay", None, 999]],
    "Transactions": [["Transactions"], ["Client Limited"], ["For the period 1 April 2026 to 31 May 2026"], [],
                     ["Date", None, "Code", "Account", "Contact", "Reference", "Description", "Tax rate", "Gross", "Net", "Total GST"],
                     ["15% GST on Expenses"],
                     ["20-03-2026", None, 400, "Purchases", "Kiwi Packaging", "INV-77", "Packaging", "15% GST on Expenses (15%)", 383.33, 333.33, 50],
                     ["02-04-2026", None, 400, "Purchases", "Kiwi Packaging", "INV-80", "Packaging", "15% GST on Expenses (15%)", 115, 100, 15]],
}


def test_the_real_xero_and_ird_layouts_are_read(env):
    folder = env.drive_root / "real"
    folder.mkdir()
    for name, rows in REAL.items():
        write_xlsx(folder / name, {"Sheet1": rows})
    write_xlsx(folder / "Client 31_05_2026 - Subsequent GST return.xlsx", LATER_RETURN)
    env.pm.add_job("401", "client-real", "real")
    final = run("401", link="local://real", setup={"frequency": "six_monthly", "first_year": True})
    g = final["gst"]
    kinds = {s["name"]: s["kind"] for s in g["sources"]}
    assert kinds["Client - 2026 GST Transaction Summary Report.xlsx"] == "ird_statement"
    assert kinds["Client - 2026 GST Return Summary Report.xlsx"] == "gst_returns"
    assert kinds["Client 31_05_2026 - Subsequent GST return.xlsx"] == "late_claims"
    b = g["bridge"]
    # Returns: "Total GST collected" includes the debit adjustments (not added twice); the transfer settles September.
    assert (b["A"], b["A_current"], b["B"], b["C"]) == ("1200.00", "1200.00", "450.00", "9.75")
    assert not g["paused"]  # "Outstanding GST" in row 6 is the GST column
    # The journal (date in column A, narration on its "ID 29061" row) and the late claim are one adjustment.
    (adj,) = [a for a in g["adjustments"] if a["included"]]
    assert adj["effect"] == "-50.00" and adj["journals"] and adj["late_claims"] and adj["subsequent_return"] == "2026-05-31"
    assert (b["E"], b["reported"], b["unexplained"]) == ("1590.25", "1590.25", "0.00")
    assert g["status"] == "Reconciled" and g["counts"]["blocking"] == 0

    wb = load_workbook(io.BytesIO(base64.b64decode(final["workbook_b64"])))
    g1 = wb["G1 Receivables GST"]
    assert g1["J1"].value == "G1" and g1["A3"].value == "G1 Receivables GST"
    assert g1.print_title_rows and g1.page_setup.orientation == "landscape"
    summary = wb["Summary"]
    assert any(str(c.value).startswith("Status: Reconciled") for row in summary.iter_rows(max_row=10) for c in row if c.value)
