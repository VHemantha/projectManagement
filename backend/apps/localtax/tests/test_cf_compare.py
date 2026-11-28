"""Last year's cash flow statement as printed, matched to this year's lines by what each line is (28 Nov 2026) - with the
wording of a real client's statement (Local-28), where matching by the words alone put last year's figures on lines of
their own."""
from decimal import Decimal as D

from apps.localtax.engine.cf_compare import annotate, group_of, with_comparatives

PRIOR = [  # as read from last year's statements
    {"section": "operating", "label": "Profit/(Loss) for the year before the taxation", "amount": "61878.33"},
    {"section": "operating", "label": "Depreciation", "amount": "100000"},
    {"section": "operating", "label": "Less - Tax Paid", "amount": "0"},
    {"section": "operating", "label": "Real estate stock", "amount": "-16199289.75"},
    {"section": "operating", "label": "Payable", "amount": "3425000"},
    {"section": "operating", "label": "Net cash used from operating activities", "amount": "-12612411.42"},
    {"section": "investing", "label": "Office Equipment Purchases", "amount": "-360000"},
    {"section": "investing", "label": "Net cash used from investing activities", "amount": "-360000"},
    {"section": "financing", "label": "Movement of shreholder loan", "amount": "0"},
    {"section": "financing", "label": "Movement in shreholdercurrent account", "amount": "13242906.42"},
    {"section": "financing", "label": "Net cash (used) / generated from financing activities", "amount": "13242906.42"},
    {"section": "cash", "label": "(Decrease) / increase in cash and cash equivalents", "amount": "270495"},
    {"section": "cash", "label": "At start of year", "amount": "3780"},
    {"section": "cash", "label": "Decrease", "amount": "270495"},
    {"section": "cash", "label": "At end of year", "amount": "274275"},
]

PDF_ROWS = [  # this year's lines as the PDF lays them out
    {"label": "Operating activities", "kind": "head"}, {"label": "Profit before tax", "cy": D("77995")},
    {"label": "Adjustments", "kind": "head"}, {"label": "Depreciation", "cy": D("110900")},
    {"label": "Changes in working capital", "kind": "head"}, {"label": "Inventories", "cy": D("5399763")},
    {"label": "Trade and other operating payables", "cy": D("5000")}, {"label": "Other current liabilities", "cy": D("-5821339")},
    {"label": "Income tax paid", "cy": D("-32998")}, {"label": "Net cash used in operating activities", "cy": D("-260680"), "kind": "sub"},
    {"label": "", "kind": "blank"}, {"label": "Investing activities", "kind": "head"},
    {"label": "Purchase of property, plant and equipment", "cy": D("282000")}, {"label": "Net cash from investing activities", "cy": D("282000"), "kind": "sub"},
    {"label": "", "kind": "blank"}, {"label": "Financing activities", "kind": "head"},
    {"label": "Net cash from financing activities", "cy": D("0"), "kind": "sub"}, {"label": "", "kind": "blank"},
    {"label": "Net increase in cash and cash equivalents", "cy": D("21320"), "kind": "sub"}, {"label": "", "kind": "blank"},
    {"label": "Movement in cash and cash equivalents", "kind": "head"}, {"label": "At start of year", "cy": D("272250")},
    {"label": "Increase", "cy": D("21320")}, {"label": "At end of year", "cy": D("18430"), "kind": "grand"},
]


def test_lines_are_grouped_by_what_they_are():
    assert group_of("Profit/(Loss) for the year before the taxation") == "pbt"
    assert group_of("Real estate stock") == "inventories" and group_of("Payable") == "payables"
    assert group_of("Less - Tax Paid") == "tax_paid" and group_of("Office Equipment Purchases") == "ppe"
    assert group_of("Movement in shreholdercurrent account") == group_of("Movement of shreholder loan") == "shareholder"
    assert group_of("(Decrease) / increase in cash and cash equivalents") == "net_change" and group_of("Decrease", "cash") == "net_change"
    assert group_of("Net cash (used) / generated from financing activities") == "total"


def test_the_pdf_rows_take_last_years_figures():
    out = annotate(PDF_ROWS, PRIOR, {})
    py = {r["label"]: r.get("py") for r in out if r.get("kind") not in ("head", "blank")}
    assert py["Profit before tax"] == D("61878.33") and py["Depreciation"] == D("100000")
    assert py["Inventories"] == D("-16199289.75") and py["Trade and other operating payables"] == D("3425000")
    assert py["Income tax paid"] == D("0") and py["Net cash used in operating activities"] == D("-12612411.42")
    assert py["Purchase of property, plant and equipment"] == D("-360000") and py["Net cash from investing activities"] == D("-360000")
    assert py["Net cash from financing activities"] == D("13242906.42")
    assert py["Net increase in cash and cash equivalents"] == D("270495") and py["Increase"] == D("270495")
    assert py["At start of year"] == D("3780") and py["At end of year"] == D("274275")
    assert py["Other current liabilities"] == 0  # not in last year's statement
    # last year's shareholder account movements (nothing this year) come in before financing's total
    labels = [r["label"] for r in out]
    i = labels.index("Net cash from financing activities")
    assert out[i - 1]["label"] == "Movement in shreholdercurrent account" and out[i - 1]["py"] == D("13242906.42") and out[i - 1]["cy"] == 0
    assert "Real estate stock" not in labels and "Payable" not in labels  # on this year's lines, not lines of their own


def test_the_web_statement_gets_a_comparative_column():
    cf = {"available": True, "net_change": D("21320"), "opening_cash": D("272250"), "closing_cash": D("18430"), "sections": [
        {"key": "operating", "title": "Cash flows from operating activities",
         "rows": [{"label": "Profit before tax", "amount": D("77995"), "note": ""}, {"label": "Depreciation", "amount": D("110900"), "note": ""},
                  {"label": "(Increase) / decrease in inventories", "amount": D("5399763"), "note": ""}],
         "subtotal": {"label": "Cash generated from operations", "amount": D("5588658")},
         "after": [{"label": "Income tax paid", "amount": D("-32998"), "note": ""}], "total": {"label": "Net cash from operating activities", "amount": D("-260680")}},
        {"key": "investing", "title": "Cash flows from investing activities",
         "rows": [{"label": "Purchase of property, plant and equipment (net of disposals)", "amount": D("282000"), "note": ""}], "subtotal": None,
         "total": {"label": "Net cash used in investing activities", "amount": D("282000")}},
        {"key": "financing", "title": "Cash flows from financing activities", "rows": [], "subtotal": None,
         "total": {"label": "Net cash from financing activities", "amount": D("0")}}]}
    out = with_comparatives(cf, PRIOR, {}, "FS 2025.pdf")
    op, inv, fin = out["sections"]
    assert out["has_comparative"] and out["comparative_source"] == "FS 2025.pdf"
    assert [r["comparative"] for r in op["rows"][:3]] == [D("61878.33"), D("100000"), D("-16199289.75")]
    assert op["total"]["comparative"] == D("-12612411.42") and op["after"][0]["comparative"] == D("0")
    assert any(r.get("prior_only") and r["label"] == "Payable" for r in op["rows"])  # no payables line this year: added
    assert inv["rows"][0]["comparative"] == D("-360000") and fin["total"]["comparative"] == D("13242906.42")
    assert (out["net_change_comparative"], out["opening_cash_comparative"], out["closing_cash_comparative"]) == (D("270495"), D("3780"), D("274275"))
    assert "has_comparative" not in cf  # the statement given isn't changed
