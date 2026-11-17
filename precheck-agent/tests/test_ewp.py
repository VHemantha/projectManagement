"""The WP Agent's electronic workpapers (AFIT, 16 Nov 2026): the firm's "Electronic Workpapers Static 2026"
macro workbook prepared from a Drive folder like the one AFIT supplied (a company's MYOB ledger, IRD
summaries, statements and minutes - mixed with another client's documents and the owners' personal
ones, which are set aside). The PDFs are text stand-ins read by the scripted model; figures follow
AFIT's sample (bank 101,868.92; interest 21,741.18 with RWT 6,087.53; ICA opening 560,327.85)."""
import base64
import io
import json
import zipfile
from decimal import Decimal

import pytest
from langchain_core.messages import AIMessage

from precheck_agent import llm, runner
from precheck_agent.ewp import catalogue as C
from precheck_agent.ewp import xlsm
from precheck_agent.ewp.run import apply_request

from .conftest import write_xlsx

ENTITY = "Teece Marine Consultancy Ltd"
HEADER = [["General ledger report"], ["Teece Marine Consultancy Limited"], ["Accrual mode:  Generated 24 Oct 2026"], ["01 Apr 2025 - 31 Mar 2026"], [" "],
          ["Date", "Reference number", "Transaction type", "Transaction description", "Open ($)", "Debit ($)", "Credit ($)", "Net activity ($)",
           "Balance ($)", "Tax amount ($)"]]


def account(code, name, opening, lines=()):
    """MYOB's layout: the account row, its lines, then its total."""
    if not lines:
        return [[code, name, "", "", opening, "", "", "", opening, ""]]
    rows, bal = [[code, name, "", "", "", "", "", "", "", ""]], opening
    dr = cr = tax = 0
    for when, ref, desc, debit, credit, t in lines:
        bal = round(bal + debit - credit, 2)
        dr, cr, tax = dr + debit, cr + credit, tax + t
        rows.append([when, ref, "Spend money", desc, 0, debit or "", credit or "", debit - credit, bal, t])
    rows.append(["Total", "", "", "", opening, round(dr, 2), round(cr, 2), round(dr - cr, 2), bal, round(tax, 2)])
    return rows


def ledger():
    rows = list(HEADER)
    rows += account("1-1000", "Cheque account", 65067.15, [
        ("29/04/2025", "591", "INLAND REVENUE 14-600-108 INC 31032025 Other A/c 03-0049-0001100-027 TP", 0, 4619, 0),
        ("31/07/2025", "CR000210", "AIMEX LTD Aimex Ltd Dividend Pmt", 100000, 0, 0),
        ("28/08/2025", "612", "INLAND REVENUE 14-600-108 INC 31032026 Other A/c 03-0049-0001100-027 TP", 0, 4850, 0),
        ("30/09/2025", "EFT", "TotalMoney INTERNET XFR", 0, 53729.23, 0)])
    rows += account("1-1600", "Accounts receivable", 72662.13, [("31/03/2026", "INV", "Fees billed less receipts", 0, 60203.63, 0)])
    rows += account("1-2000", "Motor vehicles", 7875.94)
    rows += account("2-1600", "Accounts payable", 543.61)
    rows += account("2-2000", "GST collected", -142297.39, [("31/03/2026", "GST", "GST on fees", 0, 17122.87, 0)])
    rows += account("2-2200", "GST paid", 158849.90, [("31/03/2026", "GST", "GST on purchases", 25249.76, 0, 0)])
    rows += account("3-1400", "Income tax", 144685.72, [("31/03/2026", "TAX", "Tax paid", 23001.86, 0, 0)])
    rows += account("3-1600", "Retained earnings", -3034045.26)
    rows += account("3-9999", "Historical balancing", -6436.89)
    rows += account("4-1200", "Fee income", 0, [("31/03/2026", "INV", "Fees", 0, 114152.49, 0)])
    rows += account("4-1700", "AIMEX Dividends & Share Sales", 0, [("31/07/2025", "CR", "Aimex dividend", 0, 300000, 0)])
    rows += account("6-1000", "A.C.C. expenses", 0, [("15/07/2025", "ACC", "ACC levy Teece Marine", 1581.32, 0, 237.20)])
    rows += account("6-1200", "Accounting fees", 0, [("31/03/2026", "PA", "Pretty Accounting fees", 3913.61, 0, 587.04)])
    rows += account("6-2500", "Entertainment", 0, [("12/09/2025", "631", "Nelson Independent", 624.01, 0, 93.60)])
    rows += account("6-3800", "Motor vehicle expenses", 0, [("12/09/2025", "EFT", "Fuel", 3813.96, 0, 572.09)])
    rows += account("6-5200", "Repairs & maintenance", 0, [("05/05/2025", "EFT", "GTR Inv 0650 boat engine", 1500, 0, 225), ("01/06/2025", "EFT", "Bits", 200, 0, 30)])
    rows += account("8-1200", "Interest income", 0, [("31/03/2026", "INT", "M&G interest", 0, 15653.65, 0)])
    return rows


DOCS = {
    "Banking reconciliation report 31.03.26.txt": ("Teece Marine Consultancy Limited\nBanking reconciliation report 31 Mar 2026\n1-1000 Cheque account "
                                                   "101,868.92\nExpected balance on bank statement 101,868.92\n",
                                                   {"account": "1-1000 Cheque account", "date": "2026-03-31", "ledger_balance": "101,868.92",
                                                    "statement_balance": "101,868.92", "outstanding_withdrawals": [], "outstanding_deposits": []}),
    "T2 - IRD Income Summary.txt": ("TEECE MARINE CONSULTANCY LIMITED IRD number 104-656-348\nIncome from myIR\nNZ interest received $21,741.18\n",
                                    {"interest": [{"payer": "MARINE AND GENERAL 2021 LIMITED", "date": "2026-03-31", "gross": "$21,741.18",
                                                   "tax": "$6,087.53", "source": "page 3"}],
                                     "dividends": [{"payer": "AIMEX LIMITED", "date": "2025-07-31", "gross": "$312,500.00", "tax": "$0.00",
                                                    "imputation": "$87,500.00", "source": "page 3"},
                                                   {"payer": "AIMEX LIMITED", "date": "2025-08-31", "gross": "$104,166.67", "tax": "$0.00",
                                                    "imputation": "$29,166.67", "source": "page 3"}],
                                     "period_from": "2025-04-01", "period_to": "2026-03-31"}),
    "T2 - Marine & General Shareholder Statement - TMC.txt": ("MARINE AND GENERAL (2021) LTD SHAREHOLDER CURRENT ACCOUNT STATEMENT\nTeece Marine "
                                                              "Consultancy Ltd\nGross interest payment for tax purposes 21,741.18\n",
                                                              {"payer": "Marine and General (2021) Ltd", "period_end": "2026-03-31",
                                                               "gross": "21,741.18$", "rwt": "6,087.53$", "net": "15,653.65$"}),
    "FY26 Aimex Dividend Statement - TMC.txt": ("AIMEX LTD DIVIDEND STATEMENT\nTeece Marine Consultancy Limited\nGross dividend 312,500.00\n",
                                                {"payer": "Aimex Ltd", "date": "2025-07-31", "gross": "312,500.00$", "imputation": "87,500.00",
                                                 "rwt": "Nil", "net": "225,000.00"}),
    "Teece Marine Dividend 2026 Minutes.txt": ("Teece Marine Consultancy Limited\nCompany minute\nMinutes of a Resolution of the Directors\n",
                                               {"date": "2025-10-31", "gross": "150,000.00", "imputation": "42,000.00", "rwt": "7,500.00",
                                                "net": "108,000.00"}),
    "Q1 & Q3a - Account details - Attributes - myIR.txt": ("Account details 31-Mar-2025 Income tax 104-656-348-INC004\nTEECE MARINE CONSULTANCY "
                                                           "LIMITED\nICA closing balance : -$560,327.85\n",
                                                           {"period_end": "2025-03-31", "ica_closing": "-$560,327.85"}),
    "Q1 - 31-Mar-2026 Transactions - Transaction details - myIR.txt": ("Period details 31-Mar-2026 Income tax 104-656-348-INC004\nTEECE MARINE "
                                                                       "CONSULTANCY LIMITED\nThere has been no financial activity.\n", {"lines": []}),
    "V5 - PA Statements 01Apr2025-31Mar2026.txt": ("Pretty Accounting Ltd STATEMENT To: Teece Marine Consultancy Ltd\n",
                                                   {"client": "Teece Marine Consultancy Ltd", "lines": [
                                                       {"date": "2025-07-09", "description": "Invoice - 5650", "reference": "5650", "debit": "2,429.01"},
                                                       {"date": "2025-07-10", "description": "Payment", "reference": "", "credit": "2,429.01"},
                                                       {"date": "2025-10-27", "description": "Invoice - 5757", "reference": "5757", "debit": "1,456.24"},
                                                       {"date": "2025-12-01", "description": "Invoice - 5790", "reference": "5790", "debit": "295.71"},
                                                       {"date": "2026-01-15", "description": "Invoice - 5801", "reference": "5801", "debit": "121.90"},
                                                       {"date": "2026-02-15", "description": "Invoice - 5822", "reference": "5822", "debit": "121.90"},
                                                       {"date": "2026-04-20", "description": "Invoice - 5850", "reference": "5850", "debit": "500.00"}]}),
    # Another client's documents in the same folder, and the owners' personal ones: set aside.
    "V5 - Accountancy Fee Statement.txt": ("Pretty Accounting Ltd STATEMENT To: Tory Channel Kelp Products Ltd\n", {"client": "Tory Channel Kelp", "lines": []}),
    "F1.1 - 38-9000-0391612-00_16Apr.txt": ("Account name: TORY CHANNEL KELP PROD\nTransaction history\nClosing balance $63,876.90\n",
                                            {"closing_balance": "63,876.90", "closing_date": "2026-03-31"}),
    # An owner's own IRD summary names the company as her employer: still not the company's document.
    "Personal/AM IRD Earnings FY26.txt": ("Date generated IRD number Name 12-Aug-2026 020-599-898 Teece, Anne-Marie\nIncome from myIR\n"
                                          "Salary from TEECE MARINE CONSULTANCY LIMITED 104-656-348 $90,000\n", {"interest": [], "dividends": []}),
}


def build(root):
    folder = root / "tmc"
    (folder / "Personal").mkdir(parents=True)
    write_xlsx(folder / "TMC Ltd MYOB GL Detail FY26.xlsx", {"report": ledger()})
    write_xlsx(folder / "M1 - Creditors.xlsx", {"report": [["General ledger report"], ["Teece Marine Consultancy Limited"], ["Cash mode"],
                                                           ["01 Apr 2026 - 30 Apr 2026"], [" ", "NO CREDITORS for FY26"]]})
    write_xlsx(folder / "Q1 - 31-Mar-2025 Transactions - Transaction details - myIR.xlsx", {"T": [
        ["TEECE MARINE CONSULTANCY LIMITED"], ["Account ID:", "104-656-348-INC004"], [],
        ["Period ending", "Account type", "Date", "Transaction", "Amount"],
        ["31/03/2025", "Income tax", "29/04/2025", "Payment", -4619]]})
    for name, (text, _) in DOCS.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def reader(messages, kwargs):
    body = llm._flatten(messages[-1].content)
    for name, (_, record) in DOCS.items():
        if f": {name.split('/')[-1]} ==" in body:
            if "ewp_creditors" in body or "creditors list" in body:
                break
            return AIMessage(content=json.dumps(record), usage_metadata={"input_tokens": 300, "output_tokens": 60, "total_tokens": 360})
    if "creditors list" in body:
        return AIMessage(content=json.dumps({"as_at": "2026-03-31", "none_stated": True, "rows": []}),
                         usage_metadata={"input_tokens": 300, "output_tokens": 20, "total_tokens": 320})
    return llm.demo_gst(messages, kwargs)


SETUP = {"entity": ENTITY, "balance_date": "2026-03-31", "fy_start": "2025-04-01", "ird_number": "104-656-348", "entity_type": "Company",
         "reviewed_by": "Pretty Accounting", "tolerance": "1"}


@pytest.fixture
def tmc(env):
    if not C.TEMPLATE.exists():
        pytest.skip("the workpapers template isn't in templates/")
    build(env.drive_root)
    env.pm.add_job("701", "client-tmc", "tmc")
    llm.set_fake("gst", reader)
    return "701"


def run(job_id, **options):
    return runner.execute(runner.new_run_id(), job_id, "ewp", {"drive_link": "local://tmc", "setup": SETUP, "prepared_by": "Pat", **options})


def by_cell(g):
    """Fields by cell, amounts back as Decimals (the result carries them as exact strings)."""
    out = {}
    for f in g["fields"]:
        f = dict(f)
        if f["kind"] in ("money", "number") and f["value"] is not None:
            f["value"] = Decimal(str(f["value"]))
        out[(f["sheet"], f["cell"])] = f
    return out


def test_the_workpapers_are_prepared_from_the_entitys_own_documents(tmc):
    final = run(tmc)
    assert final["status"] == "complete" and final["mode"] == "ewp", final
    g = final["gst"]
    inv = {i["name"]: i for i in g["inventory"]}
    # Another client's statement and bank history, and an owner's personal IRD summary, are set aside.
    for other in ("V5 - Accountancy Fee Statement.txt", "F1.1 - 38-9000-0391612-00_16Apr.txt", "AM IRD Earnings FY26.txt"):
        assert inv[other]["status"] == "excluded", inv[other]
    assert inv["TMC Ltd MYOB GL Detail FY26.xlsx"]["status"] == "used"
    f = by_cell(g)
    D = Decimal
    # B1 from the ledger (debit +), prior year from the opening balances.
    assert f[("B1", "G18")]["value"] == D("101868.92") and f[("B1", "K18")]["value"] == D("65067.15")
    assert f[("B1", "G28")]["value"] == D("12458.50") and f[("B1", "G161")]["value"] == D("-15653.65") and f[("B1", "G197")]["value"] == D("3913.61")
    codes = {x["code"] for x in g["exceptions"]}
    assert {"unmapped_3-1400", "unmapped_3-9999"} <= codes  # a tax appropriation in equity and a balancing account: for review
    # F1.1: the software's expected statement balance, flagged - not the bank's own statement.
    assert f[("F1.1", "I12")]["value"] == D("101868.92") and "no_statement" in codes
    assert next(c for c in g["checks"] if c["wp"] == "F1.1")["status"] == "agrees"
    # T2: IRD's income summary, confirmed by the payers' statements; the ledger has them net -> gross-up journals.
    assert (f[("T2", "C17")]["value"], f[("T2", "G17")]["value"], f[("T2", "H17")]["value"]) == ("MARINE AND GENERAL 2021 LIMITED", D("21741.18"),
                                                                                              D("6087.53"))
    assert f[("T2", "G17")]["status"] == "verified" and f[("T2", "G67")]["status"] == "verified" and f[("T2", "G68")]["status"] == "extracted"
    assert (f[("T2", "G67")]["value"], f[("T2", "I67")]["value"], f[("T2", "G68")]["value"]) == (D("312500.00"), D("87500.00"), D("104166.67"))
    journals = {j["title"]: j for j in g["journals"]}
    assert D(journals["Gross up interest for tax deducted"]["lines"][0]["debit"]) == D("6087.53")
    assert D(journals["Gross up dividends for tax deducted"]["lines"][1]["credit"]) == D("116666.67")
    assert f[("D1", "J14")]["value"] == D("6087.53") and f[("D1", "K15")]["value"] == D("6087.53")
    # Q1: no tax computation (blocking); the ledger's 4,850 for 2026 isn't in IRD's 2026 account.
    assert "no_tax_comp" in codes and any(c.startswith("gl_pay_") for c in codes)
    # Q3a: IRD's ICA closing (-560,327.85) opens the year as a credit; the 2025 terminal tax; credits attached to the dividend paid.
    assert f[("Q3a", "I10")]["value"] == D("560327.85")
    assert (f[("Q3a", "H24")]["value"], f[("Q3a", "C24")]["value"]) == (D("4619.00"), "2025-04-29")
    assert (f[("Q3a", "H50")]["value"], f[("Q3a", "C50")]["value"]) == (D("42000.00"), "2025-10-31")
    # V5: the year's invoices to the entity (not April's); differs from the ledger.
    assert f[("V5", "D12")]["value"] == D("4424.76")
    v5 = next(c for c in g["checks"] if c["wp"] == "V5")
    assert (D(v5["workpaper"]), D(v5["ledger"]), v5["status"]) == (D("3847.62"), D("3913.61"), "difference")
    # M1: no creditors, yet a debit balance in accounts payable.
    assert f[("M1", "I26")]["value"] == D("-543.61") and "ap_debit" in codes and f[("M1", "B13")]["value"].startswith("No creditors")
    # V1: ACC gross of GST; a possible capital item in repairs; entertainment flagged.
    assert f[("V1", "J21")]["value"] == D("1818.52") and any(c.startswith("capital_") for c in codes) and "entertainment" in codes
    assert f[("Workbench", "E8")]["value"] == ENTITY and f[("Workbench", "Q20")]["value"] == "2026-03-31"
    statuses = {w["key"]: w["status"] for w in g["workpapers"]}
    assert statuses["Q1"] == "Incomplete evidence" and statuses["F1.1"] == "Prepared - review" and g["status"] == "Incomplete evidence"

    # The workbook: the template with only its input cells written - formulas, macros and other parts as they were.
    book = base64.b64decode(final["workbook_b64"])
    template = C.TEMPLATE.read_bytes()
    a, b = zipfile.ZipFile(io.BytesIO(template)), zipfile.ZipFile(io.BytesIO(book))
    assert a.namelist() == b.namelist()
    assert "xl/vbaProject.bin" in b.namelist() and a.read("xl/vbaProject.bin") == b.read("xl/vbaProject.bin")
    changed = {n for n in a.namelist() if a.read(n) != b.read(n)}
    assert changed <= {"xl/workbook.xml"} | {p for p in xlsm.sheet_paths(a).values()}
    cells = xlsm.read(book, "F1.1", ["I12", "I18", "D10"])
    assert cells["I12"] == 101868.92 and cells["I18"].startswith("=SUM(") and cells["D10"] == "Cheque account (1-1000)"
    assert xlsm.read(book, "T2", ["G17"])["G17"] == 21741.18
    docs = xlsm.read(book, "Supporting Docs", [f"{c}{r}" for r in range(1, 330) for c in "BH"])
    t2_row = next(r for r in range(1, 330) if docs[f"H{r}"] == "T2")
    assert docs[f"B{t2_row}"] in ("T2 - IRD Income Summary.txt", "T2 - Marine & General Shareholder Statement - TMC.txt", "FY26 Aimex Dividend Statement - TMC.txt")


def test_only_the_chosen_workpapers_are_prepared(tmc):
    g = run(tmc, workpapers=["V5", "T2"])["gst"]
    assert {w["key"] for w in g["workpapers"]} == {"Workbench", "T2", "V5"}
    assert not any(f["sheet"] == "B1" for f in g["fields"])


def test_an_accountants_correction_is_written_and_a_formula_is_never_overwritten(tmc):
    final = run(tmc)
    out = apply_request(final["workbook_b64"], [{"sheet": "F1.1", "cell": "I12", "value": 101900.0, "kind": "money"},
                                                {"sheet": "F1.1", "cell": "I18", "value": 1.0, "kind": "money"},
                                                {"sheet": "Q3a", "cell": "C24", "value": "2025-04-30", "kind": "date"}])
    book = base64.b64decode(out["workbook_b64"])
    assert xlsm.read(book, "F1.1", ["I12"])["I12"] == 101900.0
    assert [(r["cell"], r["reason"][:20]) for r in out["refused"]] == [("I18", "The template has a f")]
    assert xlsm.read(book, "Q3a", ["C24"])["C24"] == 45777.0  # 30/04/2025 as an Excel date


def test_without_a_ledger_nothing_is_compared_and_it_says_so(tmc, env):
    (env.drive_root / "tmc" / "TMC Ltd MYOB GL Detail FY26.xlsx").unlink()
    g = run(tmc)["gst"]
    assert "no_gl" in {x["code"] for x in g["exceptions"]} and not any(f["sheet"] == "B1" for f in g["fields"])
