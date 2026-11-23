"""Team 3 > Local cards (AFIT): the client info pre-filled from supporting documents (uploaded or from the client's
shared Google Drive folder) - each value with its source, used only once the accountant confirms it, with what is
missing, unclear or inconsistent flagged; the income-statement-only option; and the financial statements in AFIT's
house format, checked against Life Path Educations & Migrations' signed statements for the year to 31 March 2025."""
import re
from decimal import Decimal as D

import pytest
from django.core.files.base import ContentFile

from apps.issues.models import Attachment
from apps.localtax import ai
from apps.localtax.models import Flag, Suggestion

from .test_api import api, world  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

# Life Path's trial balance rebuilt from its signed statements (2025, 2024; debit +), headings as AFIT mapped them.
LIFE_PATH = [
    ("4000", "Consultancy fees", "-46983649", "-23362000", "revenue"),
    ("5010", "Professional fees", "1823400", "1637000", "cost_of_sales"),
    ("5020", "Training & educational expenses", "27467394", "13652478", "cost_of_sales"),
    ("5030", "Exam supporting services", "1936600", "1378850", "cost_of_sales"),
    ("4900", "Interest income", "-11645", "-3873", "other_income"),
    ("6010", "Salaries", "5479757", "2520783", "admin_expenses"),
    ("6020", "Directors' salaries", "3600000", "0", "admin_expenses"),
    ("6030", "Rent expense", "1584000", "1440000", "admin_expenses"),
    ("6040", "Depreciation", "340602", "217500", "admin_expenses"),
    ("6090", "Other administrative expenses", "862009", "1589105", "admin_expenses"),
    ("6510", "Advertising & promotions", "2409495", "240000", "distribution_expenses"),
    ("6520", "Traveling charges", "825480", "452859", "distribution_expenses"),
    ("6530", "Commissions", "32000", "30000", "distribution_expenses"),
    ("6540", "Subscription charges", "230000", "56483", "distribution_expenses"),
    ("7000", "Bank charges", "36518", "7102", "finance_costs"),
    ("8000", "Income tax expense", "121248", "56164", "income_tax_expense"),
    ("1510", "Office equipment", "541000", "541000", "ppe"),
    ("1520", "Furniture & fittings", "724406", "152000", "ppe"),
    ("1530", "Computer equipment", "257000", "177000", "ppe"),
    ("1511", "Accumulated depreciation - Office equipment", "-306517", "-171267", "ppe"),
    ("1521", "Accumulated depreciation - Furniture & fittings", "-224102", "-43000", "ppe"),
    ("1531", "Accumulated depreciation - Computer equipment", "-75283", "-51033", "ppe"),
    ("1600", "Rent deposit", "720000", "720000", "other_non_current_assets"),
    ("1210", "Trade receivables", "928450", "230000", "trade_receivables"),
    ("1220", "Pre-payments", "50270", "25000", "trade_receivables"),
    ("1010", "Cash in hand", "293594", "230000", "cash"),
    ("1020", "Cash at bank (Cheque account)", "230706", "165512", "cash"),
    ("1030", "Petty cash", "30000", "25000", "cash"),
    ("2010", "Trade payables", "-231680", "-106667", "trade_payables"),
    ("2020", "Accrued expenses - electricity", "-17785", "-52768", "trade_payables"),
    ("2030", "Accrued expenses - water", "-2634", "-4473", "trade_payables"),
    ("2100", "Income tax payable", "-31248", "-16164", "tax_payable"),
    ("2200", "Shareholder's current account", "-2255809", "-1436563", "shareholder_current_account"),
    ("3000", "Stated capital", "-100000", "-100000", "share_capital"),
    ("3100", "Retained earnings", "-283577", "-196028", "retained_earnings"),
]


def load_life_path(c, url, **extra):
    c.patch(url, {"entity_type": "company", "legal_name": "Life Path Educations and Migrations (Private) Limited", "fy_end": "2025-03-31",
                  "audited": True, "activity": "Consultancy services to students seeking overseas education.", **extra}, format="json")
    return c.put(url + "tb/", {"rows": [{"code": a, "name": n, "amount": cy, "comparative": py, "heading": h} for a, n, cy, py, h in LIFE_PATH]},
                 format="json").data


def test_the_statements_agree_with_life_paths_signed_accounts(world):  # noqa: F811
    c = api(world.pat)
    st = load_life_path(c, world.url)
    fin = st["financials"]
    assert all(ch["passed"] for ch in fin["checks"]), fin["checks"]
    cur, comp = fin["pl"]["current"], fin["pl"]["comparative"]
    assert (cur["gross_profit"], cur["pbt"], cur["profit"]) == (D("15756255.00"), D("368039.00"), D("246791.00"))
    assert (comp["gross_profit"], comp["pbt"], comp["profit"]) == (D("6693672.00"), D("143713.00"), D("87549.00"))
    assert fin["totals"]["assets"] == D("3169524.00") and fin["totals"]["equity"] == D("630368.00")
    dp = st["statements"]
    assert dp["equity"]["rows"][-1]["total"] == D("630368.00")
    cf = dp["cash_flows"]
    assert cf["check"]["passed"] and cf["net_change"] == D("133788.00")
    rows = {r["label"]: r["amount"] for s in cf["sections"] for r in s["rows"] + (s.get("after") or [])}
    assert rows["Income tax paid"] == D("-106164.00") and rows["Purchase of property, plant and equipment (net of disposals)"] == D("-652406.00")
    assert rows["Net movement in shareholder's current account"] == D("819246.00")
    pdf = c.get(world.url + "export/fs.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and len(pdf.content) > 8000


def test_an_income_statement_only_engagement_has_no_financial_position(world):  # noqa: F811
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "fy_end": "2025-03-31", "data": {"fs_scope": "income_statement"}}, format="json")
    st = c.put(world.url + "tb/", {"rows": [{"code": a, "name": n, "amount": cy, "comparative": py, "heading": h}
                                            for a, n, cy, py, h in LIFE_PATH if h in ("revenue", "cost_of_sales", "admin_expenses")]}, format="json").data
    assert [ch["label"] for ch in st["financials"]["checks"]] == ["Every account is mapped to a heading"]  # P&L only: not checked to balance
    assert st["statements"]["equity"] is None and st["statements"]["cash_flows"] is None
    assert not {n["key"] for n in st["statements"]["notes"]} & {"ppe", "cash", "trade_payables"}
    assert c.patch(world.url, {"data": {"fs_scope": "balance_sheet"}}, format="json").status_code == 400
    assert c.get(world.url + "export/fs.pdf").content[:4] == b"%PDF"


READINGS = {
    "confirmation.pdf": {"kind": "bank_confirmation", "summary": "Bank balance confirmation", "period_end": "2025-03-31",
                         "fields": [{"field": "legal_name", "value": "Life Path Educations & Migrations (Pvt) Ltd", "cite": "p1"},
                                    {"field": "tin", "value": "114567890", "cite": "p1"}],
                         "lines": [], "balances": [{"bank": "BOC", "account": "0012 3456 7890", "date": "2025-03-31", "balance": "230706", "cite": "p1"}],
                         "flags": []},
    "statement.pdf": {"kind": "bank_statement", "summary": "March statement", "period_end": "2025-03-31",
                      "fields": [{"field": "tin", "value": "114-567-899", "cite": "header"}],
                      "lines": [{"list": "payments", "category": "WHT", "description": "WHT on interest", "amount": "1165", "comparative": "", "code": "",
                                 "date": "2025-03-31", "cite": "line 14"}],
                      "balances": [{"bank": "BOC", "account": "****7890", "date": "2025-03-31", "balance": "230000", "cite": "closing balance"}],
                      "flags": [{"kind": "unclear", "text": "Page 3 is missing.", "cite": ""}]},
}


def test_documents_prefill_the_client_info_with_sources_and_flags(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    load_life_path(c, world.url)
    for name in READINGS:
        Attachment.objects.create(issue=world.issue, file=ContentFile(b"%PDF-1.4 x", name=name), filename=name, uploaded_by=world.pat)

    def fake(path, body, timeout=180):
        assert path == "/v1/prefill"
        return READINGS[body["name"]]

    monkeypatch.setattr(ai, "_call", fake)
    docs = c.get(world.url + "documents/").data["documents"]
    assert {d["name"] for d in docs} == set(READINGS) and all(d["origin"] == "upload" and d["read_at"] is None for d in docs)
    ids = c.post(world.url + "prefill/start/", {}, format="json").data["documents"]
    for i in ids:
        assert c.post(world.url + "prefill/read/", {"document_id": i}, format="json").status_code == 200
    out = c.post(world.url + "prefill/finish/", {}, format="json").data
    flags = {f["kind"]: [] for f in out["flags"]}
    for f in out["flags"]:
        flags[f["kind"]].append(f["text"])
    text = " ".join(f["text"] for f in out["flags"])
    assert "TIN differs between documents" in text  # two TINs
    assert "Account …7890 on 2025-03-31" in text  # statement and confirmation disagree
    assert "Page 3 is missing" in text
    tins = [s for s in out["suggestions"] if s["target"] == "field:tin"]
    assert len(tins) == 2 and tins[0]["sources"][0]["document"] in READINGS
    # Nothing is used until confirmed; the accountant may edit before confirming.
    assert c.get(world.url).data["engagement"]["tin"] == ""
    r = c.post(world.url + f"suggestions/{tins[0]['id']}/decide/", {"decision": "confirm", "value": "114567890"}, format="json")
    assert r.status_code == 200 and r.data["state"]["engagement"]["tin"] == "114567890"
    assert "confirmation.pdf" in r.data["state"]["engagement"]["data"]["field_sources"]["tin"] or "statement.pdf" in r.data["state"]["engagement"]["data"]["field_sources"]["tin"]
    pay = next(s for s in out["suggestions"] if s["target"] == "payments")
    r = c.post(world.url + f"suggestions/{pay['id']}/decide/", {"decision": "confirm"}, format="json")
    payments = r.data["state"]["engagement"]["data"]["payments"]
    assert payments[-1]["amount"] == "1165.00" and "statement.pdf line 14" in payments[-1]["source"]
    assert r.data["state"]["computation"]["credits"] >= D("1165.00")  # flows through to the computation
    assert c.post(world.url + f"suggestions/{pay['id']}/decide/", {"decision": "confirm"}, format="json").status_code == 409
    # A flag is resolved with how; the audit trail keeps every step.
    flag = Flag.objects.filter(engagement__issue=world.issue, status="open").first()
    assert c.post(world.url + f"flags/{flag.id}/resolve/", {"resolution": ""}, format="json").status_code == 400
    assert c.post(world.url + f"flags/{flag.id}/resolve/", {"resolution": "Client sent page 3."}, format="json").status_code == 200
    actions = {e["action"] for e in c.get(world.url + "events/").data["events"]}
    assert {"prefill", "suggestion_confirmed", "flag_resolved"} <= actions
    # Read again: what was decided is not suggested twice; what is still waiting is replaced.
    c.post(world.url + "prefill/finish/", {}, format="json")
    assert not Suggestion.objects.filter(engagement__issue=world.issue, status="pending", target="payments").exists()


def test_the_clients_drive_folder_is_linked_and_copied(world, monkeypatch):  # noqa: F811
    import base64

    c = api(world.pat)
    calls = []

    def fake(path, body, timeout=180):
        calls.append(path)
        if path == "/v1/drive/list":
            if body["folder_id"] == "notshared123":
                raise ai.Refused("TASKO can't open this Drive folder yet. Share it (Viewer) with tasko@example.iam.")
            return {"account_email": "tasko@example.iam", "files": [{"id": "f1", "name": "TB 2025.xlsx", "version": "v1", "path": "", "web_url": "u"}]}
        if path == "/v1/drive/download":
            return {"name": "TB 2025.xlsx", "mime_type": "", "content_b64": base64.b64encode(b"data").decode()}
        if path == "/v1/drive/account":
            return {"account_email": "tasko@example.iam", "configured": True}
        raise AssertionError(path)

    monkeypatch.setattr(ai, "_call", fake)
    r = c.put(world.url + "drive/", {"url": "https://drive.google.com/drive/folders/notshared123"}, format="json")
    assert r.status_code == 400 and "tasko@example.iam" in r.data["detail"]
    r = c.put(world.url + "drive/", {"url": "https://drive.google.com/drive/folders/folderABCDEFGH"}, format="json")
    assert r.status_code == 200 and r.data["drive"]["folder_id"] == "folderABCDEFGH"
    r = c.post(world.url + "drive/sync/", {}, format="json")
    assert r.data["sync"]["added"] == 1 and r.data["documents"][0]["origin"] == "drive"
    r = c.post(world.url + "drive/sync/", {}, format="json")
    assert r.data["sync"] == {"added": 0, "updated": 0, "unchanged": 1, "skipped": [], "left": 0}


def test_the_house_format_has_the_policies_the_tax_note_and_the_company_details(world):  # noqa: F811
    c = api(world.pat)
    st = load_life_path(c, world.url, reporting_framework="full",
                        data={"directors": "Mr. A. Perera", "company_secretary": "ABC Secretaries", "shares_issued": "100,000 ordinary shares"})
    data = st["engagement"]["data"]
    assert (data["company_secretary"], data["shares_issued"]) == ("ABC Secretaries", "100,000 ordinary shares")
    notes = {n["key"]: n for n in st["statements"]["notes"]}
    titles = [p["title"] for p in notes["policies"]["policies"]]
    # the sample's policies, each with its standard under full SLFRS/LKAS
    assert "Revenue from contracts with customers (SLFRS 15)" in titles and "Leases (SLFRS 16)" in titles
    assert "Related parties and subsequent events (LKAS 24 and LKAS 10)" in titles and "Inventories (LKAS 2)" not in titles
    rec = notes["tax_reconciliation"]["rows"]
    assert rec[0]["amount"] == D("368039.00") and rec[-1]["amount"] == D("121248.00")
    assert any(r["label"].startswith("Tax at the standard rate of") for r in rec)
    report = st["statements"]["audit_report"]
    assert report["label"].startswith("DRAFT TEMPLATE") and "section 163(2)" in report["sections"][-1]["text"]
    pdf = c.get(world.url + "export/fs.pdf").content
    assert pdf[:4] == b"%PDF" and len(re.findall(rb"/Type /Page\b", pdf)) == 14  # cover, contents and 12 numbered pages


def test_a_partnership_keeps_books_and_is_taxed_at_the_partnership_rate(world):  # noqa: F811
    c = api(world.pat)
    st = load_life_path(c, world.url, entity_type="partnership", tax_type="PIT", legal_name="Perera & Silva", audited=False,
                        data={"directors": "Mr. A. Perera, Ms. B. Silva", "fs_scope": "full"})
    assert st["engagement"]["entity_type"] == "partnership" and st["financials"]["kind"] == "company"  # the books, from the TB
    comp = st["computation"]
    rate_line = next(ln for ln in comp["lines"] if ln["key"] == "standard")
    assert rate_line["rule"] == "partnership.standard_rate" and "6%" in rate_line["label"]
    assert any(a["text"] == "Business registration number is missing." for a in st["alerts"])
    notes = {n["key"]: n for n in st["statements"]["notes"]}
    assert "is a partnership" in notes["corporate"]["text"]
    assert all("the Company" not in p["text"] for p in notes["policies"]["policies"])
    assert c.get(world.url + "export/fs.pdf").content[:4] == b"%PDF"


def test_an_individual_with_a_trial_balance_gets_statements_from_the_books(world):  # noqa: F811
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "individual", "tax_type": "IIT", "legal_name": "Sample Proprietor", "fy_end": "2025-03-31",
                        "data": {"fs_scope": "income_statement", "income": [{"id": "i1", "category": "employment", "amount": "100000"}]}}, format="json")
    st = c.put(world.url + "tb/", {"rows": [{"code": a, "name": n, "amount": cy, "comparative": py, "heading": h}
                                            for a, n, cy, py, h in LIFE_PATH if h in ("revenue", "cost_of_sales", "admin_expenses")]}, format="json").data
    assert st["financials"]["kind"] == "company" and st["computation"]["lines"]  # the books for the statements; the individual computation stays
    assert any("add the business income" in a["text"] for a in st["alerts"])
    assert c.get(world.url + "export/fs.pdf").content[:4] == b"%PDF"
