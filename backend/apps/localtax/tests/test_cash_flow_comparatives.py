"""The cash flow statement's comparatives (27 Nov 2026): last year's statement of cash flows, as printed in last year's
financial statements, gives this year's comparative column - matched line by line - and totals stand out in the PDF."""
import os
from decimal import Decimal as D

import pytest

from apps.localtax import comparatives as CMP
from apps.localtax.fs_report import cash_flow_comparatives
from apps.localtax.tests.test_api import api, world  # noqa: F401
from apps.localtax.tests.test_phases import TB2

pytestmark = pytest.mark.django_db

ROWS = [
    {"label": "Operating activities", "kind": "head"}, {"label": "Profit before tax", "cy": D("15500")},
    {"label": "Adjustments", "kind": "head"}, {"label": "Depreciation", "cy": D("2000")},
    {"label": "Changes in working capital", "kind": "head"}, {"label": "Trade and other receivables", "cy": D("-2000")},
    {"label": "Trade and other operating payables", "cy": D("1000")}, {"label": "Income tax paid", "cy": D("-3000")},
    {"label": "Net cash from operating activities", "cy": D("13500"), "kind": "sub"}, {"label": "", "kind": "blank"},
    {"label": "Investing activities", "kind": "head"}, {"label": "Purchase of property, plant and equipment", "cy": D("-5000")},
    {"label": "Net cash used in investing activities", "cy": D("-5000"), "kind": "sub"}, {"label": "", "kind": "blank"},
    {"label": "Financing activities", "kind": "head"}, {"label": "Net movement in borrowings", "cy": D("3000")},
    {"label": "Net cash from financing activities", "cy": D("3000"), "kind": "sub"}, {"label": "", "kind": "blank"},
    {"label": "Net increase in cash and cash equivalents", "cy": D("11500"), "kind": "sub"}, {"label": "", "kind": "blank"},
    {"label": "Movement in cash and cash equivalents", "kind": "head"}, {"label": "At start of year", "cy": D("6000")},
    {"label": "Increase", "cy": D("11500")}, {"label": "At end of year", "cy": D("17500"), "kind": "grand"},
]
PRIOR = [  # last year's statement as printed (and as Local_Tax_AI reads it)
    {"section": "operating", "label": "Profit before taxation", "amount": "11000"},
    {"section": "operating", "label": "Depreciation", "amount": "1000"},
    {"section": "operating", "label": "(Increase)/decrease in trade receivables", "amount": "-1500"},
    {"section": "operating", "label": "Increase/(decrease) in trade payables", "amount": "800"},
    {"section": "operating", "label": "Income tax paid", "amount": "-2500"},
    {"section": "operating", "label": "Net cash generated from operating activities", "amount": "8800"},
    {"section": "investing", "label": "Acquisition of property, plant & equipment", "amount": "-4000"},
    {"section": "investing", "label": "Proceeds from sale of motor vehicle", "amount": "1200"},
    {"section": "investing", "label": "Net cash used in investing activities", "amount": "-2800"},
    {"section": "financing", "label": "Repayment of borrowings", "amount": "-1000"},
    {"section": "financing", "label": "Net cash used in financing activities", "amount": "-1000"},
    {"section": "cash", "label": "Net increase in cash and cash equivalents", "amount": "5000"},
    {"section": "cash", "label": "Cash and cash equivalents at the beginning of the year", "amount": "1000"},
    {"section": "cash", "label": "Cash and cash equivalents at the end of the year", "amount": "6000"},
]


def test_each_line_takes_last_years_printed_figure():
    out = cash_flow_comparatives(ROWS, PRIOR, {})
    py = {r["label"]: r.get("py") for r in out if r.get("kind") not in ("head", "blank")}
    assert py["Profit before tax"] == D("11000") and py["Depreciation"] == D("1000")
    assert py["Trade and other receivables"] == D("-1500") and py["Trade and other operating payables"] == D("800")
    assert py["Income tax paid"] == D("-2500") and py["Net cash from operating activities"] == D("8800")
    assert py["Purchase of property, plant and equipment"] == D("-4000") and py["Net cash used in investing activities"] == D("-2800")
    assert py["Net movement in borrowings"] == D("-1000") and py["Net cash from financing activities"] == D("-1000")
    assert py["Net increase in cash and cash equivalents"] == D("5000") and py["Increase"] == D("5000")
    assert py["At start of year"] == D("1000") and py["At end of year"] == D("6000")
    # A line printed only last year comes in before its section's total, with Nil for this year.
    labels = [r["label"] for r in out]
    sale = labels.index("Proceeds from sale of motor vehicle")
    assert out[sale]["cy"] == 0 and out[sale]["py"] == D("1200") and labels[sale + 1] == "Net cash used in investing activities"


def test_without_a_printed_line_the_trial_balance_comparatives_fill_in():
    fin = {"pl": {"comparative": {"pbt": D("11000")}}, "bs": {"cash": {"comparative": D("6000")}}}
    out = cash_flow_comparatives(ROWS, [{"section": "operating", "label": "Depreciation", "amount": "1000"}], fin)
    py = {r["label"]: r.get("py") for r in out}
    assert py["Profit before tax"] == D("11000") and py["At end of year"] == D("6000") and py["Depreciation"] == D("1000")
    assert py["Income tax paid"] == 0  # not in last year's statement: Nil, never made up


def test_last_years_cash_flow_lines_are_kept_apart_from_the_accounts():
    lines = [{"description": "Trade receivables", "amount": "5000", "category": "trade_receivables"},
             {"description": "operating | Depreciation", "amount": "1000", "category": "cash_flow"},
             {"description": "cash | Cash at end of year", "amount": "6000", "category": "cash_flow"}]
    tb = [{"code": "1200", "name": "Trade receivables", "heading": "trade_receivables"}]
    props = CMP.propose(lines, tb)
    assert [p["action"] for p in props] == ["match", "cash_flow", "cash_flow"]

    class T:
        code, heading = "1200", "trade_receivables"
    got = CMP.apply(lines, props, [T()], [])
    assert got["comparatives"] == {"1200": D("5000")}
    assert got["cash_flow"] == [{"section": "operating", "label": "Depreciation", "amount": D("1000")},
                                {"section": "cash", "label": "Cash at end of year", "amount": D("6000")}]


def test_the_pdf_shows_the_comparatives(world):  # noqa: F811
    c = api(world.pat)
    from apps.localtax.models import TaxEngagement

    c.patch(world.url, {"entity_type": "company", "audited": True, "fy_end": "2025-03-31"}, format="json")
    c.put(world.url + "tb/", {"rows": [{"code": a, "name": n, "amount": x, "comparative": p} for a, n, x, p in TB2]}, format="json")
    eng = TaxEngagement.objects.get(issue=world.issue)  # as confirming last year's statements stores it
    eng.data = {**(eng.data or {}), "prior_cash_flow": {"document": "FS 2024.pdf", "lines": PRIOR}}
    eng.save()
    pdf = c.get(world.url + "export/fs.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    from apps.localtax import fs_report as FR
    from apps.localtax import services as S

    rep = FR._Report(S.state(eng, world.pat))
    flow = rep.cash_flow()
    table = next(x for x in flow if x.__class__.__name__ == "Table")
    cells = [[str(getattr(v, "text", v)) for v in row] for row in table._cellvalues]
    assert cells[1][2:] == ["2025", "2024"]  # this year and last year
    by_label = {row[0]: row[2:] for row in cells[2:]}
    assert by_label["Net cash from operating activities"][1] == "8,800" and by_label["At end of year"][1] == "6,000"
    if os.environ.get("CF_PDF_OUT"):  # to look at it
        with open(os.environ["CF_PDF_OUT"], "wb") as f:
            f.write(pdf.content)
