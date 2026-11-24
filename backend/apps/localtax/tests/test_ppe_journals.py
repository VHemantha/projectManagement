"""Team 3 > Local cards (AFIT, 24 Nov 2026):
- depreciation worked out month by month under the client's own policy, posted as one journal on approval, with the
  PPE note drawn from the same schedule;
- the journal register;
- a dummy trial balance made up from a story;
- comparatives read from last year's financial statements."""
from datetime import date
from decimal import Decimal as D

import pytest
from django.core.files.base import ContentFile

from apps.issues.models import Attachment
from apps.localtax import ai
from apps.localtax.engine import depreciation as DEP
from apps.localtax.models import Adjustment, ClientPolicy, TbLine

from .test_api import api, world  # noqa: F401 - the fixture
from .test_client_info import LIFE_PATH, load_life_path

pytestmark = pytest.mark.django_db
POLICY = [{"key": "computer_equipment", "label": "Computer equipment", "method": "straight_line", "rate": "0.25", "residual": "0"},
          {"key": "furniture_fittings", "label": "Furniture and fittings", "method": "straight_line", "rate": "0.10", "residual": "0"}]


# --- the engine ---------------------------------------------------------------------------------------------------

def test_depreciation_is_monthly_from_the_month_available_and_stops_at_disposal_and_residual():
    opening = {"computer_equipment": {"cost": D("1200000"), "accumulated": D("300000"), "source": ""},
               "furniture_fittings": {"cost": D("100000"), "accumulated": D("95000"), "source": ""}}
    additions = [{"description": "Laptop", "category": "computer_equipment", "available_date": "2025-06-15", "cost": "250000"},
                 {"description": "Office furniture", "category": "furniture_fittings", "available_date": "2025-09-10", "cost": "180000"}]
    disposals = [{"description": "Old server", "category": "computer_equipment", "date": "2025-10-05", "cost": "200000", "accumulated_bf": "150000",
                  "proceeds": "60000"}]
    s = DEP.schedule(POLICY, opening, additions, disposals, date(2026, 3, 31))
    cats = {c["key"]: c for c in s["categories"]}
    comp = cats["computer_equipment"]
    # opening pool (1,000,000 left after the disposal): 12 months at 25%
    # the laptop: June 2025 to March 2026 = 10 months; the server: April to September = 6 months, none in October
    laptop, = comp["additions"]
    server, = comp["disposals"]
    assert (laptop["months"], laptop["charge"]) == (10, D("52083.30"))  # 250,000 x 25% / 12 = 5,208.33 a month
    assert (server["months"], server["charge"]) == (6, D("25000.02"))
    assert server["accumulated_on_disposal"] == D("175000.02") and server["gain"] == D("35000.02")  # 60,000 - (200,000 - 175,000.02)
    # the opening pool: 1,000,000 x 25% / 12 = 20,833.33 a month, x 12 = 249,999.96 (each month rounded to the cent)
    assert comp["accumulated"]["charge"] == D("249999.96") + D("52083.30") + D("25000.02")
    assert comp["cost"] == {"opening": D("1200000"), "additions": D("250000.00"), "disposals": D("200000.00"), "closing": D("1250000.00")}
    furn = cats["furniture_fittings"]
    # the opening furniture has only 5,000 left to depreciate: the charge stops there (never below the residual value)
    assert furn["monthly"][0] == D("833.33") and sum(furn["monthly"], D(0)) == D("5000.00") + furn["additions"][0]["charge"]
    assert furn["additions"][0]["months"] == 7  # September to March
    assert sum(s["monthly"], D(0)) == s["totals"]["charge"]


# --- the workflow -------------------------------------------------------------------------------------------------

def test_the_depreciation_is_approved_into_one_journal_and_the_ppe_note_agrees_with_the_tb(world):  # noqa: F811
    c, lead = api(world.pat), api(world.lee)
    st = load_life_path(c, world.url)
    ppe = st["ppe"]
    cats = {a["code"]: a["category"] for a in ppe["accounts"]}
    assert cats == {"1510": "office_equipment", "1520": "furniture_fittings", "1530": "computer_equipment",
                    "1511": "office_equipment", "1521": "furniture_fittings", "1531": "computer_equipment"}
    assert not ppe["policy_about"]["saved"] and ppe["status"] == "not_approved"
    # the client's own policy, kept with the client for later years
    r = c.put(world.url + "ppe/policy/", {"policy": [
        {"key": "office_equipment", "label": "Office equipment", "method": "straight_line", "rate": "25", "residual": "0"},
        {"key": "furniture_fittings", "label": "Furniture and fittings", "method": "straight_line", "rate": "25", "residual": "0"},
        {"key": "computer_equipment", "label": "Computer equipment", "method": "straight_line", "rate": "20", "residual": "0"}]}, format="json")
    assert r.status_code == 200, r.data
    assert ClientPolicy.objects.get(client=world.issue.project.client).depreciation[0]["rate"] == "0.25"
    # the year's additions (Life Path's furniture and computers grew in the year)
    c.patch(world.url, {"data": {"ppe": {"additions": [
        {"description": "Office furniture", "category": "furniture_fittings", "purchase_date": "2024-09-01", "available_date": "2024-10-01",
         "cost": "572406"},
        {"description": "Laptops", "category": "computer_equipment", "purchase_date": "2024-06-10", "available_date": "2024-06-15", "cost": "80000"}]}}},
            format="json")
    assert c.post(world.url + "ppe/approve/").status_code == 403  # a preparer can't approve
    r = lead.post(world.url + "ppe/approve/")
    assert r.status_code == 200, r.data
    ppe = r.data["ppe"]
    assert ppe["status"] == "approved" and ppe["journal_ref"] == "JE-DEP"
    assert all(x["agrees"] for x in ppe["reconciliation"]), ppe["reconciliation"]
    auto = Adjustment.objects.get(engagement__issue=world.issue, target="auto:depreciation")
    assert auto.status == "approved" and sum(D(ln["amount"]) for ln in auto.lines) == 0
    charge = D(ppe["schedule"]["totals"]["charge"])
    dep_line = next(ln for ln in r.data["financials"]["tb"] if ln["code"] == "6040")
    assert D(dep_line["amount"]) == charge  # the expense is the schedule's charge
    # approving again replaces the journal: still one, never posted twice
    assert lead.post(world.url + "ppe/approve/").status_code == 200
    assert Adjustment.objects.filter(engagement__issue=world.issue, target="auto:depreciation").count() == 1
    # a change after approval is flagged until approved again
    st = c.patch(world.url, {"data": {"ppe": {"additions": []}}}, format="json").data
    assert st["ppe"]["status"] == "changed" and any("changed since it was approved" in a["text"] for a in st["alerts"])
    assert c.get(world.url + "export/fs.pdf").content[:4] == b"%PDF"


def test_journals_are_numbered_approved_reversed_and_kept_in_the_register(world):  # noqa: F811
    c, lead = api(world.pat), api(world.lee)
    load_life_path(c, world.url)
    r = c.post(world.url + "adjustments/", {"kind": "journal", "label": "Accrue audit fee", "reason": "Audit fee for the year not yet billed",
                                            "entry_date": "2025-03-31", "lines": [{"code": "6090", "amount": "60000"}, {"code": "2020", "amount": "-60000"}]},
               format="json")
    assert r.status_code == 200, r.data
    je = next(j for j in r.data["journals"]["journals"] if j["label"] == "Accrue audit fee")
    assert je["ref"] == "JE-001" and je["entry_date"] == "2025-03-31" and je["status"] == "proposed"
    assert lead.post(world.url + f"adjustments/{je['id']}/decide/", {"decision": "approve"}, format="json").status_code == 200
    reg = c.get(world.url).data["journals"]
    assert {a["code"]: a["journals"] for a in reg["accounts"]} == {"6090": "60000.00", "2020": "-60000.00"}
    # an approved journal is reversed, not edited
    assert c.patch(world.url + f"adjustments/{je['id']}/", {"reason": "changed my mind"}, format="json").status_code == 409
    r = c.post(world.url + f"adjustments/{je['id']}/reverse/", {"reason": "Billed after the year end - not an accrual"}, format="json")
    assert r.status_code == 200, r.data
    rev = next(j for j in r.data["journals"]["journals"] if j["reverses"] == je["id"])
    assert rev["ref"] == "JE-001-R" and [ln["amount"] for ln in rev["lines"]] == ["-60000.00", "60000.00"]
    assert c.post(world.url + f"adjustments/{je['id']}/reverse/", {"reason": "again please"}, format="json").status_code == 409
    second = c.post(world.url + "adjustments/", {"kind": "journal", "reason": "Reclassify prepayment", "lines": [
        {"code": "1220", "amount": "1000"}, {"code": "6090", "amount": "-1000"}]}, format="json").data
    assert any(j["ref"] == "JE-002" for j in second["journals"]["journals"])
    xlsx = c.get(world.url + "export/journals.xlsx")
    assert xlsx.status_code == 200 and c.get(world.url + "export/journals.pdf").content[:4] == b"%PDF"


def test_a_dummy_trial_balance_is_made_from_a_story_and_labelled_so(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "legal_name": "Story Bakery (Pvt) Ltd", "fy_end": "2025-03-31"}, format="json")
    reply = {"accounts": [{"code": "4000", "name": "Sales", "heading": "revenue", "amount": "-30000000", "comparative": "-26000000"},
                          {"code": "5000", "name": "Cost of sales", "heading": "cost_of_sales", "amount": "18000000", "comparative": "16000000"},
                          {"code": "1520", "name": "Computer equipment - cost", "heading": "ppe", "amount": "900000", "comparative": "900000"},
                          {"code": "1010", "name": "Cash at bank", "heading": "cash", "amount": "11500000", "comparative": "9000000"},
                          {"code": "3000", "name": "Stated capital", "heading": "share_capital", "amount": "-1000000", "comparative": "-1000000"}],
             "assumptions": ["One shop in Colombo."], "notes": []}
    monkeypatch.setattr(ai, "_call", lambda path, body, timeout=180: reply)
    r = c.post(world.url + "ai/tb-story/", {"story": "A family bakery in Colombo with sales of about 30 million, growing 15% this year."}, format="json")
    assert r.status_code == 200, r.data
    rows = r.data["rows"]
    # made to balance by code, in each column, and said so
    assert sum(D(x["amount"]) for x in rows) == 0 and sum(D(x["comparative"]) for x in rows) == 0
    assert any("Retained earnings adjusted" in n for n in r.data["notes"])
    assert c.put(world.url + "tb/", {"rows": rows, "source": "story"}, format="json").status_code == 400  # the story goes with it
    st = c.put(world.url + "tb/", {"rows": rows, "source": "story", "story": r.data["story"]}, format="json").data
    assert st["engagement"]["data"]["tb_source"]["kind"] == "story" and st["financials"]["checks"][0]["passed"]
    assert c.get(world.url + "export/fs.pdf").content[:4] == b"%PDF"


def test_last_years_statements_become_this_years_comparatives_once_confirmed(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    rows = [{"code": a, "name": n, "amount": cy, "heading": h} for a, n, cy, py, h in LIFE_PATH]  # no prior-year column
    c.patch(world.url, {"entity_type": "company", "legal_name": "Life Path", "fy_end": "2025-03-31"}, format="json")
    c.put(world.url + "tb/", {"rows": rows}, format="json")
    att = Attachment.objects.create(issue=world.issue, file=ContentFile(b"%PDF-1.4", name="fs-2024.pdf"), filename="fs-2024.pdf", uploaded_by=world.pat)
    read = {"kind": "prior_fs", "summary": "Life Path FS 2024", "gaps": [], "year_of_assessment": "", "lines": [
        {"description": "Consultancy fees", "amount": "23362000", "category": "revenue", "code": "", "comparative": "", "date": "", "cite": "Note 1"},
        {"description": "Trade receivable", "amount": "230000", "category": "trade_receivables", "code": "", "comparative": "", "date": "", "cite": "Note 9"},
        {"description": "Stated capital", "amount": "100000", "category": "share_capital", "code": "", "comparative": "", "date": "", "cite": "SOFP"},
        {"description": "Retained earnings", "amount": "283577", "category": "retained_earnings", "code": "", "comparative": "", "date": "", "cite": "SOFP"},
        {"description": "Insurance claim receivable", "amount": "5000", "category": "trade_receivables", "code": "", "comparative": "", "date": "",
         "cite": "Note 9"},
        {"description": "Office equipment | cost", "amount": "541000", "category": "ppe_note", "code": "", "comparative": "", "date": "", "cite": "Note 7"},
        {"description": "Office equipment | accumulated depreciation", "amount": "171267", "category": "ppe_note", "code": "", "comparative": "",
         "date": "", "cite": "Note 7"}]}
    monkeypatch.setattr(ai, "_call", lambda path, body, timeout=180: read)
    r = c.post(world.url + "prior-fs/", {"attachment_id": att.id}, format="json")
    assert r.status_code == 200, r.data
    ex = r.data["extraction"]
    props = {p["index"]: p for p in ex["data"]["proposals"]}
    assert (props[0]["action"], props[0]["code"]) == ("match", "4000")
    assert (props[1]["action"], props[1]["code"]) == ("match", "1210")  # a close name
    assert props[4]["action"] == "new" and props[5]["action"] == "ppe"
    st = c.post(world.url + f"extractions/{ex['id']}/decide/", {"decision": "confirm", "use_as": "comparatives",
                                                                 "mapping": ex["data"]["proposals"]}, format="json").data
    tb = {ln.code: ln for ln in TbLine.objects.filter(engagement__issue=world.issue)}
    assert tb["4000"].comparative == D("-23362000.00") and tb["1210"].comparative == D("230000.00") and tb["3000"].comparative == D("-100000.00")
    # retained earnings: last year's closing less last year's profit (here only the revenue line was confirmed)
    assert tb["3100"].comparative == D("-283577.00") + D("23362000.00")
    assert any(ln.name == "Insurance claim receivable" and ln.amount == 0 and ln.comparative == D("5000.00") for ln in tb.values())
    assert st["engagement"]["data"]["ppe"]["opening"]["office_equipment"] == {
        "cost": "541000", "accumulated": "171267", "source": "Last year's financial statements (fs-2024.pdf), PPE note"}
