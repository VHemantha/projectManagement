"""The WP Agent's wages (PAYE) and imputation (ICA) reconciliations (AFIT, 10 Nov 2026), on the documents AFIT
supplied: Chambers International's IRD PAYE summary and EMP transaction summary for the year to 31 March
2026 (myIR's month-first dates), and the ICA workpaper's figures (opening 1,146.26, RWT 56.65, refund 42.73,
closing 1,160.18; terminal tax -56.65; permanent differences 2,858.16)."""
import base64
import io
from datetime import date
from decimal import Decimal

from openpyxl import load_workbook

from precheck_agent import ask, runner
from precheck_agent.knowledge import Scope, get_knowledge

from .conftest import write_xlsx
from .test_ask import answering

D = Decimal
# Month ending, gross, PAYE, KiwiSaver employee, net KiwiSaver employer, ESCT, student loan (IRD PAYE summary, FY2026).
PAYE = [
    ("4/30/2025", "16448.78", "3310.44", "643.93", "320.98", "115.32", "0"), ("5/31/2025", "11803.05", "2428.56", "450.88", "231.69", "81.04", "0"),
    ("6/30/2025", "12775.00", "2569.23", "502.80", "247.38", "90.41", "0"), ("7/31/2025", "16845.76", "3402.80", "657.63", "328.21", "116.39", "0"),
    ("8/31/2025", "13806.28", "2862.53", "540.10", "266.31", "97.90", "0"), ("9/30/2025", "12967.47", "2609.62", "505.26", "250.76", "90.98", "0"),
    ("10/31/2025", "16470.56", "3288.45", "653.42", "332.69", "115.92", "0"), ("11/30/2025", "13706.84", "2713.80", "531.20", "271.78", "94.42", "0"),
    ("12/31/2025", "18622.36", "3706.74", "713.85", "379.64", "124.20", "0"), ("1/31/2026", "13524.77", "2719.36", "544.36", "272.28", "94.82", "14.76"),
    ("2/28/2026", "13517.50", "2696.18", "523.28", "264.05", "93.31", "0"), ("3/31/2026", "13469.50", "2678.78", "526.71", "267.44", "93.89", "0"),
]
PAID = ["5/19/2025", "6/20/2025", "7/20/2025", "8/20/2025", "9/19/2025", "10/20/2025", "11/20/2025", "12/19/2025", "1/19/2026", "2/19/2026", "3/20/2026",
        "4/20/2026"]


def _total(m) -> Decimal:
    return sum((D(x) for x in m[2:]), D(0))


def wages_folder(root):
    folder = root / "paye"
    folder.mkdir()
    summary = [["Account ID:", "072-730-259-EMP004"], ["Name:", "CHAMBERS INTERNATIONAL LINEN & GIFTS LIMITED"], ["From:", "4/1/2025"], ["To:", "3/31/2026"], [],
               ["Month ending", "Gross earnings and/or schedular payments", "Not liable for ACC earners' levy", "PAYE (incl. tax on schedular payments)",
                "Child support deductions", "Student loan deductions", "KiwiSaver deductions", "Net KiwiSaver employer contributions", "ESCT deductions",
                "Total Deductions"]]
    summary += [[m[0], float(m[1]), 0, float(m[2]), 0, float(m[6]), float(m[3]), float(m[4]), float(m[5]), float(_total(m))] for m in PAYE]
    write_xlsx(folder / "W_PAYE - Summary 2026.xlsx", {"Summary": summary})
    tx = [["Account ID:", "072-730-259-EMP004"], [], ["Period ending", "Account type", "Date", "Transaction", "Amount"]]
    for m, paid in zip(PAYE, PAID):
        first = f"{m[0].split('/')[0]}/1/{m[0].split('/')[2]}"
        for label, value in (("PAYE deductions", m[2]), ("KiwiSaver employee deductions", m[3]), ("KiwiSaver employer contributions", m[4]),
                             ("Superannuation contribution tax", m[5]), ("Student loan deductions", m[6])):
            if D(value):
                tx.append([m[0], "Payroll", first, label, float(value)])
        tx.append([m[0], "Payroll", paid, "Payment", -float(_total(m))])
    write_xlsx(folder / "W_PAYE- Transaction Summary 2026.xlsx", {"Transactions": tx})
    august = _total(PAYE[4])  # paid 9/19/2025 but charged to wages in the books
    write_xlsx(folder / "Trial Balance.xlsx", {"TB": [
        ["Account Code", "Account", "Account Type", "Debit - Year to date", "Credit - Year to date"],
        [477, "Wages and Salaries", "Expense", float(D("173957.87") + august), None],
        [478, "KiwiSaver Employer Contributions", "Expense", 4641.81, None],
        [820, "PAYE Payable", "Current Liability", None, float(D("3566.82") + august)],
        [200, "Sales", "Revenue", None, 300000]]})
    gl = [["Date", "Account", "Description", "Reference", "Debit", "Credit"]]
    for m, paid in list(zip(PAYE, PAID))[:-1]:
        mm, dd, yy = (int(x) for x in paid.split("/"))
        account = "477 - Wages and Salaries" if m is PAYE[4] else "820 - PAYE Payable"
        gl.append([date(yy, mm, dd), account, "IRD payroll payment", "EMP", float(_total(m)), None])
    write_xlsx(folder / "General Ledger.xlsx", {"GL": gl})
    return folder


def run(job_id, link, agent, setup):
    base = {"entity": "Chambers International", "balance_date": "2026-03-31", "fy_start": "2025-04-01"}
    return runner.execute(runner.new_run_id(), job_id, agent, {"drive_link": link, "setup": {**base, **setup}})


def test_the_wages_reconciliation_on_the_supplied_paye_documents(env):
    wages_folder(env.drive_root)
    env.pm.add_job("601", "client-chambers", "paye")
    final = run("601", "local://paye", "wages", {"opening_ird_payable": "0"})
    assert final["status"] == "complete" and final["mode"] == "wages", final
    g = final["gst"]
    kinds = {s["name"]: s["kind"] for s in g["sources"]}
    assert kinds["W_PAYE - Summary 2026.xlsx"] == "payroll_summary" and kinds["W_PAYE- Transaction Summary 2026.xlsx"] == "payroll_ird"
    e, li = g["expense"], g["liabilities"]
    # Baseline: gross 173,957.87 + net employer KiwiSaver 3,433.21 + ESCT 1,208.60 (the 4,641.81 in the supplied summary).
    assert (e["totals"]["gross"], e["totals"]["ks_employer"], e["totals"]["esct"], e["baseline"]) == ("173957.87", "3433.21", "1208.60", "178599.68")
    # Liabilities: 46,436.48 charged, 42,869.66 paid by 31 March; March's 3,566.82 paid 20 April is still payable ("Payable FY2026").
    assert (li["charges"], li["credits"], li["closing"], li["later"]) == ("46436.48", "-42869.66", "3566.82", "-3566.82")
    (fix,) = g["corrections"]
    assert fix["title"].startswith("IRD payment debited to salary expense") and fix["expense_effect"] == "-3766.84" and fix["liability_effect"] == "-3766.84"
    assert g["residuals"] == {"expense": "0.00", "liabilities": "0.00"}
    assert g["expense_status"] == g["liability_status"] == g["status"] == "Reconciled subject to corrections"
    assert len(g["months"]) == 12 and g["months"][0]["month_end"] == "2025-04-30"  # myIR's month-first dates read as such
    wb = load_workbook(io.BytesIO(base64.b64decode(final["workbook_b64"])))
    assert wb.sheetnames == ["Summary", "IRD monthly totals", "GL mapping", "IRD settlements", "Liability roll-forward", "Accruals & prior-year",
                             "Monthly differences", "Proposed journals", "Exceptions & evidence", "Sources"]
    labels = [c.value for c in wb["Summary"]["A"] if c.value]
    assert "IRD-based employer-cost baseline" in labels and "IRD payroll principal payable at the balance date" in labels


def test_without_an_opening_balance_the_liabilities_are_incomplete_not_nil(env):
    wages_folder(env.drive_root)
    env.pm.add_job("602", "client-chambers", "paye")
    g = run("602", "local://paye", "wages", {})["gst"]
    assert g["liability_status"] == "Incomplete evidence" and g["expense_status"] == "Reconciled subject to corrections"
    assert any(x["code"] == "no_opening" for x in g["exceptions"])


def ica_folder(root):
    folder = root / "ica"
    folder.mkdir()
    write_xlsx(folder / "Income Tax Transaction Summary 2026.xlsx", {"T": [
        ["Account ID:", "072-730-259-INC001"], [], ["Period ending", "Account type", "Date", "Transaction", "Amount"],
        ["3/31/2025", "Income Tax", "6/15/2025", "Refund", 42.73],
        ["3/31/2025", "Income Tax", "6/15/2025", "Use of money interest", 1.20]]})
    write_xlsx(folder / "Trial Balance.xlsx", {"TB": [
        ["Account Code", "Account", "Account Type", "Debit - Year to date", "Credit - Year to date"],
        [620, "Income Tax Receivable", "Current Asset", 56.65, None], [960, "Retained Earnings", "Equity", None, 0]]})
    write_xlsx(folder / "General Ledger.xlsx", {"GL": [["Date", "Account", "Description", "Reference", "Debit", "Credit"],
                                                       [date(2025, 9, 30), "RWT on Interest Received", "ANZ interest RWT", "", 56.65, None]]})
    return folder


def test_the_ica_reconciliation_follows_the_workpaper_layout(env):
    ica_folder(env.drive_root)
    env.pm.add_job("603", "client-ica", "ica")
    setup = {"opening_ica": "1146.26", "retained_earnings": "0", "permanent_differences": "2858.16"}
    final = run("603", "local://ica", "ica", setup)
    assert final["status"] == "complete" and final["mode"] == "ica", final
    g = final["gst"]
    a, b = g["movements"], g["retained"]
    assert (a["opening"], a["credits"]["RWT on Interest Received"], a["debits"]["Income Tax Refunded"], a["closing"]) == ("1146.26", "56.65", "42.73",
                                                                                                                          "1160.18")
    # Terminal tax -56.65 (a refund due); balance 1,103.53; grossed up at exactly 72/28 (the workpaper's 0.3889 gives 2,837.57).
    assert (b["terminal"], b["balance"], b["grossed"], b["tax_paid_rp"]) == ("-56.65", "1103.53", "2837.65", "2858.16")
    assert (b["difference"], b["missing"]) == ("-20.51", "-7.98") and g["status"] == "Unreconciled"
    assert any(x["code"] == "uomi" for x in g["exceptions"])  # use-of-money interest isn't an ICA movement
    wb = load_workbook(io.BytesIO(base64.b64decode(final["workbook_b64"])))
    assert wb.sheetnames[:2] == ["Imputation Credits", "Reconcile ICA to RE"]
    first = [c.value for c in wb["Imputation Credits"]["A"] if c.value]
    for label in ("Opening Balance", "Credits", "Income Tax Paid", "FDP Paid", "RWT on Interest Received", "IMP & FDP Credits attached to div rec",
                  "Other Credits", "Total Credits", "Debits", "Income Tax Refunded", "FDP Refunds", "IMP Credits attached to div paid", "Other Debits",
                  "Total Debits", "Closing Balance"):
        assert any(str(v).strip() == label for v in first), label
    second = [str(c.value).strip() for c in wb["Reconcile ICA to RE"]["A"] if c.value]
    for label in ("End of Year Balance of IC Reconciliation", "Plus EOY Terminal Tax still to pay/refund", "Plus Prov 3 Tax still to pay/refund",
                  "Other Adjustments", "Balance", "Imputation Ratio", "Balance Grossed Up", "Retained Profit",
                  "Permanent Tax Differences (enter credits as -ve)", "Timing Tax Differences", "Remaining 33% IC as at 31 Mar 2011",
                  "33% RE differential", "30% RE differential", "Tax Paid Retained Profit", "Difference", "Missing Credits"):
        assert label in second, label
    ws = wb["Reconcile ICA to RE"]
    grossed = next(r for r in ws.iter_rows() if r[0].value == "Balance Grossed Up")
    assert str(grossed[1].value).endswith("*72/28")

    within = run("603", "local://ica", "ica", {**setup, "tolerance": "25"})["gst"]
    assert within["status"] == "Reconciled"


def test_ask_answers_about_the_wages_and_ica_work(env):
    wages_folder(env.drive_root)
    env.pm.add_job("604", "client-chambers", "paye")
    run("604", "local://paye", "wages", {"opening_ird_payable": "0"})
    assert get_knowledge().count(Scope.of(env.pm.jobs["604"]), source_types=["wp_wages"]) > 20
    seen: dict = {}
    from precheck_agent import llm

    llm.set_fake("assistant", answering({"answer": "See the passages.", "status": "answered", "outside_job": False, "points": []}, seen))
    out = ask.answer(env.pm.jobs["604"], "How much PAYE was still payable at the balance date?")
    assert out["areas"] == ["the WP Agent's wages (PAYE) reconciliation"]
    assert "[WP Agent (wages reconciliation)]" in seen["body"] and "3,566.82" in seen["body"]
