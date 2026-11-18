"""Bank reconciliations in the electronic workpapers (AFIT, 18 Nov 2026): every bank reconciliation found
in the task folder and its subfolders gets its own F1 sheet (F1.1, F1.2 ...), as the template's macro
makes them from the Workbench's bank quantity (M40): each filled from its reconciliation and statement,
with its balance in the accounts on B1, and linked into the workbook as the macro would link it."""
import base64
from decimal import Decimal as D

from precheck_agent.ewp import procedures
from precheck_agent.ewp import xlsm
from precheck_agent.ewp.run import apply_request

from . import test_ewp as T
from .conftest import write_xlsx
from .test_ewp import by_cell, run, tmc  # noqa: F401  (the fixture)

ASB = ("Bank/ASB Savings bank rec 31.03.26.txt",
       "Teece Marine Consultancy Limited\nBank reconciliation 31 Mar 2026\nASB Savings 12-3045-0123456-00\n",
       {"account": "ASB Savings", "account_number": "12-3045-0123456-00", "date": "2026-03-31", "ledger_balance": "20,000.00",
        "statement_balance": "20,250.00", "outstanding_deposits": [],
        "outstanding_withdrawals": [{"date": "2026-03-30", "reference": "CHQ 12", "description": "Cheque to GTR Marine", "amount": "250.00"}]})
WESTPAC = ("Bank/2026/Westpac bank rec 31.03.26.txt",
           "Teece Marine Consultancy Limited\nBank reconciliation 31 Mar 2026\nWestpac Business 03-0049-0001100-00\n",
           {"account": "Westpac Business", "account_number": "03-0049-0001100-00", "date": "2026-03-31", "ledger_balance": "5,000.00",
            "statement_balance": "5,000.00", "outstanding_deposits": [], "outstanding_withdrawals": []})


def three_banks(env, monkeypatch):
    """The sample folder, with a second bank account in the ledger (its reconciliation in a subfolder)
    and a third reconciliation, two folders down, for an account the ledger does not have."""
    folder = env.drive_root / "tmc"
    rows = T.ledger() + T.account("1-1100", "ASB Savings 12-3045-0123456-00", 20000.00)
    write_xlsx(folder / "TMC Ltd MYOB GL Detail FY26.xlsx", {"report": rows})
    for name, text, record in (ASB, WESTPAC):
        (folder / name).parent.mkdir(parents=True, exist_ok=True)
        (folder / name).write_text(text, encoding="utf-8")
        monkeypatch.setitem(T.DOCS, name, (text, record))


def test_each_bank_reconciliation_gets_its_own_sheet(tmc, env, monkeypatch):
    three_banks(env, monkeypatch)
    final = run(tmc)
    g = final["gst"]
    assert g["bank_sheets"] == ["F1.1", "F1.2", "F1.3"]
    f = by_cell(g)
    # The Workbench's bank quantity (column M, the F1 row under the "Qty" heading of row 38).
    assert f[("Workbench", "M40")]["value"] == 3
    assert "3 bank reconciliation(s) found in the folder and its subfolders" in f[("Workbench", "M40")]["source"]
    # F1.1 stays the cheque account; F1.2 is ASB from its reconciliation, matched by account number.
    assert f[("F1.1", "I12")]["value"] == D("101868.92")
    assert f[("F1.2", "D10")]["value"] == "ASB Savings 12-3045-0123456-00 (1-1100)"
    assert f[("F1.2", "I12")]["value"] == D("20250.00") and f[("F1.2", "I23")]["value"] == D("250.00")
    assert f[("F1.2", "D23")]["value"] == "Cheque to GTR Marine" and f[("F1.2", "H5")]["value"] == "F1.2"
    asb = next(c for c in g["checks"] if c["label"].startswith("F1.2: Bank 1-1100"))
    assert asb["status"] == "agrees" and D(str(asb["workpaper"])) == D("20000.00")
    # F1.3: a reconciliation for an account the ledger does not have is still prepared, and flagged.
    assert f[("F1.3", "D10")]["value"] == "Westpac Business"
    codes = {x["code"] for x in g["exceptions"]}
    assert {"no_ledger_account_3", "lead_sheet_rows"} <= codes
    # B1: each bank's balance in the accounts, in the order of the sheets.
    assert f[("B1", "G19")]["value"] == D("20000.00") and f[("B1", "D19")]["value"] == "ASB Savings 12-3045-0123456-00"
    assert f[("B1", "D20")]["value"] == "Westpac Business" and f[("B1", "G20")]["value"] == D("5000.00")

    # The workbook: the sheets exist, filled, and are linked in as the template's macro links them.
    book = base64.b64decode(final["workbook_b64"])
    assert xlsm.read(book, "Workbench", ["M40"])["M40"] == 3.0
    assert xlsm.read(book, "F1.2", ["D10", "I12", "I23", "H5"]) == {"D10": "ASB Savings 12-3045-0123456-00 (1-1100)", "I12": 20250.0,
                                                                      "I23": 250.0, "H5": "F1.2"}
    assert xlsm.read(book, "F1.2", ["I58"])["I58"] == "=I18"  # its own formulas, as F1.1's
    assert xlsm.read(book, "F1.1", ["I12"])["I12"] == 101868.92
    assert xlsm.read(book, "B1", ["H18", "H19", "H20"]) == {"H18": "=IFERROR(F1.1!WPBal1,0)", "H19": "=IFERROR('F1.2'!WPBal1,0)",
                                                            "H20": "=IFERROR('F1.3'!WPBal1,0)"}
    hidden = xlsm.read(book, "Hidden", ["S25", "L74", "L75", "Q74"])
    assert hidden["S25"] == 3.0 and hidden["L74"] == "F1.2" and hidden["L75"] == "F1.3" and "'F1.2'!A1" in hidden["Q74"]
    assert xlsm.read(book, "F", ["B11", "H11"]) == {"B11": "F1.2", "H11": "=IFERROR('F1.2'!GLBal,\"\")"}

    # A correction on a copied sheet: its formulas are as protected as F1.1's.
    out = apply_request(final["workbook_b64"], [{"sheet": "F1.2", "cell": "I12", "value": 20300.0, "kind": "money"},
                                                {"sheet": "F1.2", "cell": "I58", "value": 1.0, "kind": "money"}])
    edited = base64.b64decode(out["workbook_b64"])
    assert xlsm.read(edited, "F1.2", ["I12", "I58"]) == {"I12": 20300.0, "I58": "=I18"}
    assert [r["cell"] for r in out["refused"]] == ["I58"]


def test_one_bank_account_keeps_one_sheet(tmc):
    g = run(tmc)["gst"]
    assert g["bank_sheets"] == ["F1.1"] and by_cell(g)[("Workbench", "M40")]["value"] == 1
    book = base64.b64decode(run(tmc)["workbook_b64"])
    assert "F1.2" not in xlsm.sheet_paths(__import__("zipfile").ZipFile(__import__("io").BytesIO(book)))


def test_a_reconciliation_is_matched_to_its_ledger_account():
    cheque = {"name": "Cheque account", "code": "1-1000"}
    asb = {"name": "ASB Savings 12-3045-0123456-00", "code": "1-1100"}
    assert procedures.same_account({"account": "1-1000 Cheque account", "number": ""}, cheque)
    assert not procedures.same_account({"account": "1-1000 Cheque account", "number": ""}, asb)
    assert procedures.same_account({"account": "Savings", "number": "12-3045-0123456-000"}, asb)  # a longer suffix
    assert not procedures.same_account({"account": "Westpac Business", "number": "03-0049-0001100-00"}, asb)
