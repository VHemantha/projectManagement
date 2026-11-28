"""The financial statements' notes (AFIT, 28 Nov 2026): no draft footer; revenue by nature from last year's statements;
auditors' remuneration disclosed; the tax reconciliation with last year's figures (as printed, or worked out); the PPE
note's wording and last year's asset categories; bank overdrafts in short-term borrowings and in cash and cash
equivalents for the cash flow; and the notes from Commitments on written from the questionnaire."""
import os
from decimal import Decimal as D

import pytest

from apps.localtax import comparatives as CMP
from apps.localtax.engine import depth as DP
from apps.localtax.engine import fs as FS
from apps.localtax.fs_report import tax_rec_comparatives
from apps.localtax.tests.test_api import api, world  # noqa: F401

pytestmark = pytest.mark.django_db

# code, name, this year (debit +), last year
TB = [
    ("4000", "Sales - goods", "-60000", "-45000"), ("4010", "Service income", "-20000", "-15000"),
    ("5000", "Cost of sales", "40000", "30000"), ("6100", "Audit fees", "1500", "1200"), ("6110", "Directors' remuneration", "6000", "5000"),
    ("6200", "Depreciation", "2000", "1000"), ("8000", "Income tax expense", "9000", "7000"),
    ("1500", "Plant and machinery", "13000", "10000"), ("1510", "Accumulated depreciation - plant", "-3000", "-1000"),
    ("1200", "Trade receivables", "15000", "9000"), ("1000", "Bank", "25000", "6000"),
    ("2050", "Bank overdraft", "-2500", "-1000"), ("2000", "Trade creditors", "-5000", "-4000"), ("2100", "Income tax payable", "-9000", "-7000"),
    ("3000", "Stated capital", "-3000", "-3000"), ("3100", "Retained earnings", "-9000", "6800"),  # last year's closing = this year's opening
]


def fin():
    lines = [{"code": c, "name": n, "amount": D(a), "comparative": D(p), "heading": FS.suggest_heading(n, D(a))} for c, n, a, p in TB]
    return FS.statements(lines)


def test_overdrafts_are_short_term_borrowings_and_cash_equivalents_for_the_cash_flow():
    f = fin()
    assert f["bs"]["borrowings_current"]["label"] == "Short-term borrowings" and f["bs"]["borrowings_current"]["amount"] == D("2500")
    cf = DP.cash_flows(f)
    assert cf["check"]["passed"], cf["check"]
    # cash and cash equivalents = cash at bank less the overdraft, this year and last
    assert (cf["closing_cash"], cf["opening_cash"]) == (D("22500"), D("5000"))
    assert cf["cash_components"] == {"cash": D("25000"), "overdraft": D("2500"), "cash_comparative": D("6000"), "overdraft_comparative": D("1000")}
    fin_rows = {r["label"]: r["amount"] for s in cf["sections"] if s["key"] == "financing" for r in s["rows"]}
    assert "Net movement in borrowings" not in fin_rows  # the overdraft's movement isn't financing


def test_the_tax_reconciliation_takes_last_years_figures():
    rows = [{"label": "Accounting profit before tax", "amount": D("30500")}, {"label": "Tax at the standard rate of 30%", "amount": D("9150")},
            {"label": "Tax effect of disallowable expenses", "amount": D("600")},
            {"label": "Tax effect of allowable deductions, allowances and losses", "amount": D("-750")},
            {"label": "Income tax on taxable income (per the tax computation)", "amount": D("9000"), "kind": "subtotal"},
            {"label": "Income tax expense in profit or loss", "amount": D("9000"), "kind": "total"}]
    printed = [{"label": "Profit before tax", "amount": "22800"}, {"label": "Tax at 30%", "amount": "6840"},
               {"label": "Disallowable expenses", "amount": "460"}, {"label": "Tax effect of exempt income", "amount": "-300"},
               {"label": "Current tax per the computation", "amount": "7000"}, {"label": "Income tax expense", "amount": "7000"}]
    out = tax_rec_comparatives(rows, printed, {})
    py = {lb: p for lb, _, p, _ in out}
    assert py["Accounting profit before tax"] == D("22800") and py["Tax at the standard rate of 30%"] == D("6840")
    assert py["Tax effect of disallowable expenses"] == D("460") and py["Income tax expense in profit or loss"] == D("7000")
    assert ("Tax effect of exempt income", None, D("-300"), None) in out  # printed only last year: before current tax
    # No reconciliation in last year's statements: worked out so it adds up to last year's tax expense.
    out = tax_rec_comparatives(rows, [], {"pbt": D("22800"), "rate": "0.30", "current": D("7000"), "deferred": D("500")})
    py = {lb: p for lb, _, p, _ in out}
    assert py["Accounting profit before tax"] == D("22800") and py["Tax at the standard rate of 30%"] == D("6840.00")
    assert py["Tax effect of disallowable expenses, deductions and other items (prior year, net)"] == D("160.00")
    assert py["Income tax on taxable income (per the tax computation)"] == D("7000")
    assert py["Deferred tax and under- / (over-) provision"] == D("500") and py["Income tax expense in profit or loss"] == D("7500")


def test_last_years_statements_give_revenue_its_nature_and_ppe_its_categories():
    lines = [{"description": "Sale of goods", "amount": "45000", "category": "revenue"},
             {"description": "Rendering of services", "amount": "15000", "category": "revenue"},
             {"description": "Plant and machinery | cost", "amount": "10000", "category": "ppe_note"},
             {"description": "Boats | cost", "amount": "5000", "category": "ppe_note"},
             {"description": "Profit before tax", "amount": "22800", "category": "tax_reconciliation"}]

    class T:
        def __init__(self, code, heading):
            self.code, self.heading = code, heading
    tb = [T("4000", "revenue"), T("4010", "revenue")]
    props = [{"index": 0, "action": "match", "code": "4000", "heading": "revenue"}, {"index": 1, "action": "match", "code": "4010", "heading": "revenue"},
             {"index": 2, "action": "ppe"}, {"index": 3, "action": "ppe"}, {"index": 4, "action": "tax_rec"}]
    from apps.localtax.engine import depreciation as DEP
    got = CMP.apply(lines, props, tb, DEP.default_policy())
    assert got["revenue_nature"] == {"4000": "Sale of goods", "4010": "Rendering of services"}
    assert got["tax_rec"] == [{"label": "Profit before tax", "amount": D("22800")}]
    assert got["ppe_categories"]["new"] == [{"key": "boats", "label": "Boats"}]  # last year's class the policy lacks
    assert got["ppe_categories"]["labels"] == {"plant_machinery": "Plant and machinery", "boats": "Boats"}
    assert got["opening"]["boats"]["cost"] == D("5000")
    assert CMP.propose(lines, [])[4]["action"] == "tax_rec"


def test_the_pdf_notes(world):  # noqa: F811
    from apps.localtax import fs_report as FR
    from apps.localtax import services as S
    from apps.localtax.models import TaxEngagement

    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "audited": True, "fy_end": "2025-03-31", "data": {"disclosures": {
        "commitments": {"answer": "yes", "details": "The Company had ordered a delivery van for Rs. 4,500,000, received in May 2025."},
        "events": {"answer": "no", "details": ""}}}}, format="json")
    c.put(world.url + "tb/", {"rows": [{"code": a, "name": n, "amount": x, "comparative": p} for a, n, x, p in TB]}, format="json")
    eng = TaxEngagement.objects.get(issue=world.issue)
    eng.data = {**(eng.data or {}), "revenue_nature": {"4000": "Sale of goods", "4010": "Rendering of services"}}
    eng.save()
    assert eng.data["disclosures"]["commitments"]["answer"] == "yes"  # kept by the questionnaire's save
    rep = FR._Report(S.state(eng, world.pat))
    rep.build()
    flat = []

    def walk(x):
        for attr in ("_content", "_flowables"):
            for y in getattr(x, attr, None) or []:
                walk(y)
        if hasattr(x, "_cellvalues"):
            for row in x._cellvalues:
                flat.append([str(getattr(v, "text", v)) for v in row])
                for v in row:
                    walk(v)
        if hasattr(x, "text"):
            flat.append([x.text])
    for b in rep.notes_pages():
        walk(b)
    text = "\n".join(" | ".join(r) for r in flat)
    assert "Sale of goods | 60,000 | 45,000" in text and "Rendering of services | 20,000 | 15,000" in text  # revenue by nature
    assert "Auditors' remuneration | 1,500 | 1,200" in text and "Profit before tax is stated after charging:" in text
    assert "For the purpose of the statement of cash flows, the year end cash and cash equivalents comprise the following:" in text
    assert "Cash and bank balances | 25,000 | 6,000" in text and "(2,500) | (1,000)" in text
    assert "delivery van" in text and "To be confirmed" not in text
    pdf = c.get(world.url + "export/fs.pdf").content
    assert b"prepared in TASKO" not in pdf
    if os.environ.get("FS_PDF_OUT"):
        with open(os.environ["FS_PDF_OUT"], "wb") as f:
            f.write(pdf)
