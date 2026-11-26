"""Team 3 > Local cards (AFIT, 26 Nov 2026):
- the audit or compilation report, chosen with the client details, in the firm's own formats; edited by the accountant;
  a document of its own, as Word and PDF; the statements as Word too;
- figures edited on the statements (never totals), flagged until they balance, then posted to the trial balance as a
  journal whose accounts Local_Tax_AI chooses;
- Update: everything worked out again, with what changed since the last update."""
import io
from decimal import Decimal as D

import docx
import pytest

from apps.localtax import ai
from apps.localtax.models import Adjustment

from .test_api import api, world  # noqa: F401 - the fixture
from .test_client_requests import company

pytestmark = pytest.mark.django_db


def words(content: bytes) -> str:
    d = docx.Document(io.BytesIO(content))
    return "\n".join(p.text for p in d.paragraphs)


# --- the report --------------------------------------------------------------------------------------------------

def test_the_audit_report_is_the_firms_format_filled_in_edited_and_downloaded(world):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    st = c.patch(world.url, {"audited": True, "reporting_framework": "smes", "data": {"report_date": "2025-06-30"}}, format="json").data
    rep = st["report"]
    assert rep["kind"] == "audit" and rep["date_text"] == "30 June 2025"
    sec = {s["key"]: s for s in rep["sections"]}
    assert sec["addressee"]["text"] == "To Shareholders of ABC Trading (Pvt) Ltd."
    assert "comprise the balance sheet as at 31 March 2025" in sec["intro"]["text"]
    assert "(SLFRS for SMEs)" in sec["management"]["text"] and "Companies Act No. 07 of 2007" in sec["legal"]["text"]
    # The result for the year is the engine's: a loss here (sales 1.45m against 2m of expenses).
    assert "its loss and cash flows" in sec["opinion"]["text"]
    # The accountant edits a paragraph; "" goes back to the format's wording.
    st = c.patch(world.url, {"data": {"report_text": {"audit": {"scope_basis": "We obtained all the information we needed."}}}}, format="json").data
    sec = {s["key"]: s for s in st["report"]["sections"]}
    assert sec["scope_basis"]["text"] == "We obtained all the information we needed." and sec["scope_basis"]["edited"]
    # Word: the firm's template itself - its letterhead and footer kept - with the paragraphs filled in.
    r = c.get(world.url + "export/report.docx")
    assert r.status_code == 200 and r["Content-Type"].endswith("wordprocessingml.document")
    text = words(r.content)
    assert "INDEPENDENT AUDITOR’S REPORT" in text and "To Shareholders of ABC Trading (Pvt) Ltd." in text
    assert "We obtained all the information we needed." in text and "30 June 2025" in text and "{TODAY}" not in text
    assert "____" not in text and "……" not in text
    d = docx.Document(io.BytesIO(r.content))
    assert "AFIT Connect (Chartered Accountants)" in "\n".join(p.text for p in d.sections[0].footer.paragraphs)
    pdf = c.get(world.url + "export/report.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"


def test_a_compilation_report_for_a_company_and_for_a_sole_proprietor(world):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    st = c.patch(world.url, {"audited": False}, format="json").data
    rep = st["report"]
    assert rep["kind"] == "compilation"
    title, body = rep["sections"][0]["text"], rep["sections"][1]["text"]
    assert title == "COMPILATION REPORT TO THE SHAREHOLDERS OF ABC TRADING (PVT) LTD"
    assert "the balance sheet of ABC Trading (Pvt) Ltd as of March 31, 2025 and statements of income and cash flows" in body
    text = words(c.get(world.url + "export/report.docx").content)
    assert title in text and "accordingly express no assurance thereon." in text and text.count("accordingly express no assurance") == 1
    assert "[PROPRIETOR" not in text
    # a sole proprietor with books, income statement only
    st = c.patch(world.url, {"entity_type": "individual", "tax_type": "IIT", "data": {"directors": "Mr. A. Perera", "fs_scope": "income_statement"}},
                 format="json").data
    rep = st["report"]
    assert rep["sections"][0]["text"] == "COMPILATION REPORT TO MR. A. PERERA, TRADING AS ABC TRADING (PVT) LTD"
    assert "the statement of income of ABC Trading (Pvt) Ltd for the year ended March 31, 2025" in rep["sections"][1]["text"]


def test_the_statements_download_as_word_without_the_report_inside(world):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    c.patch(world.url, {"audited": True}, format="json")
    r = c.get(world.url + "export/fs.docx")
    assert r.status_code == 200
    text = words(r.content)
    assert "ABC TRADING (PVT) LTD" in text and "FINANCIAL STATEMENTS - 31 MARCH 2025" in text
    assert "INDEPENDENT AUDITOR" not in text  # the report is its own document
    d = docx.Document(io.BytesIO(r.content))
    cells = [cell.text for t in d.tables for row in t.rows for cell in row.cells]
    assert any("Revenue" in x for x in cells) and any("1,450,000" in x for x in cells)
    assert c.get(world.url + "export/journals.docx").status_code == 404


# --- editing figures on the statements ------------------------------------------------------------------------------

def test_an_edited_figure_is_flagged_until_the_other_side_is_edited_then_goes_to_the_tb(world, monkeypatch):  # noqa: F811
    c, lead = api(world.pat), api(world.lee)
    company(c, world.url)
    # admin expenses (rent 1,000,000 + sundry 1,000,000) shown at 2,050,000
    st = c.post(world.url + "fs/edit/", {"heading": "admin_expenses", "value": "2,050,000"}, format="json").data
    assert D(str(st["financials"]["pl"]["current"]["admin_expenses"])) == D("2050000")
    edits = st["fs_edits"]
    assert edits["items"][0]["delta"] == "50000.00" and not edits["balanced"] and not edits["can_post"]
    assert any(a["severity"] == "blocking" and "out of balance by 50,000.00" in a["text"] for a in st["alerts"])
    # it can't go forward while out of balance
    r = c.post(world.url + "stages/fs/", {"status": "ready_for_review"}, format="json")
    assert r.status_code == 409 and "out of balance" in r.data["detail"]
    assert c.post(world.url + "fs/edits/post/", format="json").status_code == 409
    # totals are never edited
    assert c.post(world.url + "fs/edit/", {"heading": "gross_profit", "value": "1"}, format="json").status_code == 400
    # the other side: accruals shown at 100,000 (from 50,000)
    st = c.post(world.url + "fs/edit/", {"heading": "trade_payables", "value": "100000"}, format="json").data
    assert st["fs_edits"]["balanced"] and st["fs_edits"]["can_post"]
    assert not [a for a in st["alerts"] if a["severity"] == "blocking" and "out of balance" in a["text"]]
    # Local_Tax_AI chooses the accounts; an account from another heading is ignored (the heading's largest is used)
    seen = {}

    def fake(path, body, timeout=180):
        seen.update(path=path, body=body)
        return {"picks": [{"heading": "admin_expenses", "code": "6900", "reason": "Sundry"}, {"heading": "trade_payables", "code": "6100", "reason": "x"}],
                "notes": []}

    monkeypatch.setattr(ai, "_call", fake)
    st = c.post(world.url + "fs/edits/post/", format="json").data
    assert seen["path"] == "/v1/fs-edit-accounts" and {e["heading"] for e in seen["body"]["context"]["edits"]} == {"admin_expenses", "trade_payables"}
    je = Adjustment.objects.get(engagement__issue=world.issue, target="auto:fs_edits")
    assert je.status == "proposed" and sorted((ln["code"], ln["amount"]) for ln in je.lines) == [("2110", "-50000.00"), ("6900", "50000.00")]
    assert st["fs_edits"]["journal"]["ref"] == je.ref and not st["fs_edits"]["can_post"]
    # approving it puts the change in the TB and clears the edits; the figures stay as edited
    st = lead.post(f"{world.url}adjustments/{je.id}/decide/", {"decision": "approve"}, format="json").data
    assert st["fs_edits"] is None
    tb = {ln["code"]: D(str(ln["amount"])) for ln in st["financials"]["tb"]}
    assert tb["6900"] == D("1050000") and tb["2110"] == D("-100000") and not any(k.startswith("EDIT:") for k in tb)
    assert D(str(st["financials"]["pl"]["current"]["admin_expenses"])) == D("2050000")


def test_editing_again_withdraws_the_waiting_journal_and_an_edit_can_be_undone(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    monkeypatch.setattr(ai, "_call", lambda path, body, timeout=180: (_ for _ in ()).throw(ai.Unavailable("down")))
    c.post(world.url + "fs/edit/", {"heading": "revenue", "value": "1500000"}, format="json")
    c.post(world.url + "fs/edit/", {"heading": "cash", "value": "550000"}, format="json")
    st = c.post(world.url + "fs/edits/post/", format="json").data
    je = Adjustment.objects.get(engagement__issue=world.issue, target="auto:fs_edits")
    assert sorted((ln["code"], ln["amount"]) for ln in je.lines) == [("1100", "50000.00"), ("4000", "-50000.00")]  # largest accounts
    assert any("not available" in n for n in st["engagement"]["data"]["fs_edits"]["notes"])
    st = c.post(world.url + "fs/edit/", {"heading": "revenue", "value": "1460000"}, format="json").data
    je.refresh_from_db()
    assert je.status == "rejected" and "edited again" in je.decision_note and st["fs_edits"]["journal"] is None
    st = c.delete(world.url + "fs/edit/", {}, format="json").data
    assert st["fs_edits"] is None and D(str(st["financials"]["pl"]["current"]["revenue"])) == D("1450000")


def test_an_income_statement_only_edit_balances_through_retained_earnings(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    c.patch(world.url, {"data": {"fs_scope": "income_statement"}}, format="json")
    monkeypatch.setattr(ai, "_call", lambda path, body, timeout=180: {"picks": [], "notes": []})
    st = c.post(world.url + "fs/edit/", {"heading": "admin_expenses", "value": "1900000"}, format="json").data
    assert st["fs_edits"]["balanced"]  # nothing to balance against
    c.post(world.url + "fs/edits/post/", format="json")
    je = Adjustment.objects.get(engagement__issue=world.issue, target="auto:fs_edits")
    assert sorted(ln["heading"] for ln in je.lines) == ["admin_expenses", "retained_earnings"]


# --- Update ----------------------------------------------------------------------------------------------------------

def test_update_works_everything_out_and_says_what_changed(world):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    r = c.post(world.url + "update/", {"stage": "fs"}, format="json")
    assert r.status_code == 200 and r.data["first"] and r.data["changes"] == [] and r.data["state"]["engagement"]["task"] == world.issue.key
    c.post(world.url + "fs/edit/", {"heading": "revenue", "value": "1500000"}, format="json")
    r = c.post(world.url + "update/", {"stage": "fs"}, format="json")
    changed = {x["key"]: x for x in r.data["changes"]}
    assert not r.data["first"] and {"revenue", "profit", "tb_difference", "blocking"} <= set(changed)
    assert changed["revenue"]["from"] == "1450000.00" and changed["revenue"]["to"] == "1500000.00"
