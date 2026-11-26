"""The Local Tax workflow, Phases 2-4 (AFIT): documents read into confirmable records (general ledger, prior return,
fixed asset register); the full set of statements (changes in equity, cash flows, notes, policies, the draft audit
report); the capital allowance and loss schedules and the return's schedules; and the tax professional's review of
the rules and the return's field references, which the computation then rests on."""
from decimal import Decimal as D

import pytest
from django.contrib.auth.models import Group

from apps.localtax import ai
from apps.localtax.engine import depth as DP
from apps.localtax.engine import fs as FS
from apps.localtax.engine import schedules as SC
from apps.localtax.engine.rules import Rules
from apps.localtax.engine.tax import compute
from apps.localtax.models import Extraction
from apps.localtax.services import VALIDATORS_GROUP

from .test_api import api, person, world  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

# A consistent pair of years (debit +): the comparative column is last year's trial balance.
TB2 = [
    ("4000", "Sales", "-50000", "-40000"), ("5000", "Cost of sales", "30000", "25000"), ("6200", "Depreciation", "2000", "1000"),
    ("7000", "Loan interest", "500", "0"), ("8000", "Income tax expense", "4000", "3000"), ("3900", "Dividends paid", "1000", "0"),
    ("1500", "Plant and machinery", "13000", "10000"), ("1200", "Trade receivables", "7000", "5000"), ("1000", "Bank", "20500", "6000"),
    ("2000", "Trade creditors", "-5000", "-4000"), ("2100", "Income tax payable", "-3000", "-2000"), ("3000", "Stated capital", "-12000", "-10000"),
    ("2500", "Long-term loan", "-3000", "0"), ("3100", "Retained earnings", "-5000", "6000"),
]


def fin2():
    lines = [{"code": c, "name": n, "amount": D(a), "comparative": D(p), "heading": FS.suggest_heading(n, D(a))} for c, n, a, p in TB2]
    return FS.statements(lines)


def test_the_statement_of_changes_in_equity_and_the_cash_flows_reconcile():
    fin = fin2()
    assert all(c["passed"] for c in fin["checks"]), fin["checks"]
    eq = DP.equity_changes(fin)
    end = eq["rows"][-1]
    assert eq["check"]["passed"] and end["total"] == D("29500.00") and end["retained_earnings"] == D("17500.00")
    cf = DP.cash_flows(fin)
    assert cf["available"] and cf["check"]["passed"], cf["check"]
    totals = {s["key"]: s["total"]["amount"] for s in cf["sections"]}
    assert totals == {"operating": D("15500.00"), "investing": D("-5000.00"), "financing": D("4000.00")}
    assert cf["net_change"] == D("14500.00") and cf["opening_cash"] == D("6000.00")
    # Without comparatives the cash flow says what it needs instead of guessing.
    no_comp = FS.statements([{**ln, "comparative": None} for ln in [{"code": c, "name": n, "amount": D(a), "heading": FS.suggest_heading(n)}
                                                                      for c, n, a, _ in TB2]])
    assert DP.cash_flows(no_comp)["available"] is False


def test_the_notes_carry_the_accounts_the_policies_and_what_only_the_accountant_can_write():
    fin = fin2()
    eng = {"legal_name": "ABC", "reporting_framework": "smes", "data": {"policy_text": {"ppe": "Our own PPE wording."},
                                                                         "note_text": {"events": "None."}}}
    notes = DP.notes(fin, eng, None)
    by_key = {n["key"]: n for n in notes}
    assert by_key["revenue"]["total"] == D("50000.00") and by_key["revenue"]["lines"][0]["amount"] == D("50000.00")
    policies = {p["key"]: p for p in by_key["policies"]["policies"]}
    assert "SLFRS for SMEs" in policies["basis"]["text"] and policies["ppe"]["text"] == "Our own PPE wording." and not policies["ppe"]["standard"]
    assert "inventories" not in policies  # no inventory on the trial balance
    assert by_key["events"]["text"] == "None." and by_key["contingencies"]["to_complete"]
    report = DP.audit_report(eng, "31 March 2025")
    assert report["label"].startswith("DRAFT TEMPLATE") and any("SLAuS" in s["text"] for s in report["sections"])


def test_capital_allowances_come_from_the_fixed_asset_register_with_balancing_charges():
    r = Rules("2024/25")
    far = SC.capital_allowances([
        {"id": "a", "description": "Lathe", "asset_class": "plant_machinery", "cost": "1000000", "ca_claimed_bf": "900000"},
        {"id": "b", "description": "Van", "asset_class": "motor_vehicles", "cost": "500000", "ca_claimed_bf": "300000", "disposed": "2025-01-10",
         "proceeds": "350000"},
        {"id": "c", "description": "Laptops", "asset_class": "computers_software", "cost": "400000"},
        {"id": "d", "description": "Brand", "asset_class": "intangibles", "cost": "90000"}], r)
    rows = {x["id"]: x for x in far["rows"]}
    assert rows["a"]["allowance"] == D("100000.00")  # never more than the unclaimed cost
    assert rows["b"]["balancing_charge"] == D("150000.00") and rows["b"]["allowance"] == 0
    assert rows["c"]["allowance"] == D("100000.00") and rows["c"]["wdv_cf"] == D("300000.00")
    assert rows["d"]["allowance"] == 0 and any("Brand" in f["text"] for f in far["flags"])
    comp = compute({"entity_type": "company", "pbt": "5000000", "fixed_assets": [
        {"id": "a", "description": "Lathe", "asset_class": "plant_machinery", "cost": "1000000", "ca_claimed_bf": "900000"},
        {"id": "b", "description": "Van", "asset_class": "motor_vehicles", "cost": "500000", "ca_claimed_bf": "300000", "disposed": "2025-01-10",
         "proceeds": "350000"}]}, Rules("2024/25"))
    assert comp["taxable_income"] == D("5050000.00")  # 5,000,000 + 150,000 charge - 100,000 allowance
    assert {ln["key"] for ln in comp["lines"]} >= {"bc_b", "far_a"}


def test_losses_are_used_oldest_first_and_carried_forward():
    ls = SC.losses([{"ya": "2022/23", "amount": "500"}, {"ya": "2021/22", "amount": "300"}], "0", D("600"), D("0"), "2024/25")
    assert [(r["ya"], r["utilised"], r["cf"]) for r in ls["rows"]] == [("2021/22", D("300"), D("0")), ("2022/23", D("300"), D("200"))]
    assert ls["totals"]["cf"] == D("200")


def test_a_professionals_correction_of_a_rule_is_what_the_computation_uses():
    plain = compute({"entity_type": "company", "pbt": "1000000"}, Rules("2024/25"))
    reviewed = compute({"entity_type": "company", "pbt": "1000000"}, Rules("2024/25", {
        "company.standard_rate": {"status": "corrected", "value": 0.28, "ref": "Amendment Act", "by": "Tax Pro"}}))
    assert plain["income_tax"] == D("300000.00") and reviewed["income_tax"] == D("280000.00")
    used = {r["rule"]: r for r in reviewed["rules"]}
    assert used["company.standard_rate"]["validated"] and not plain["rules"][0]["validated"]


# --- the API --------------------------------------------------------------------------------------------------------

def test_only_a_validator_reviews_the_rules_and_the_review_reaches_the_card(world):  # noqa: F811
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "year_of_assessment": "2024/25", "data": {"computation": {"pbt_manual": "1000000"}}}, format="json")
    reg = c.get("/api/local-tax/rules/2024-25/review/").data
    assert reg["total"] > 10 and reg["validated"] == 0 and reg["can_validate"] is False
    body = {"rule": "company.standard_rate", "action": "correct", "value": "0.28", "ref": "Inland Revenue (Amendment) Act", "note": "Rate changed."}
    assert c.post("/api/local-tax/rules/2024-25/review/", body, format="json").status_code == 403
    pro = person("tess")
    pro.groups.add(Group.objects.get_or_create(name=VALIDATORS_GROUP)[0])
    p = api(pro)
    assert p.post("/api/local-tax/rules/2024-25/review/", {**body, "value": "28"}, format="json").status_code == 400  # a rate is a fraction
    assert p.post("/api/local-tax/rules/2024-25/review/", {**body, "ref": ""}, format="json").status_code == 400  # the law relied on
    r = p.post("/api/local-tax/rules/2024-25/review/", body, format="json")
    assert r.status_code == 200 and r.data["validated"] == 1
    rule = next(x for x in r.data["rules"] if x["rule"] == "company.standard_rate")
    assert rule["value"] == 0.28 and rule["file_value"] == 0.30 and rule["reviewed_by"] == "Tess"
    assert c.get(world.url).data["computation"]["income_tax"] == D("280000.00")
    # Withdrawn: back to the file's (unvalidated) value; the history is kept.
    r = p.post("/api/local-tax/rules/2024-25/review/", {"rule": "company.standard_rate", "action": "withdraw"}, format="json")
    assert next(x for x in r.data["rules"] if x["rule"] == "company.standard_rate")["history"][0]["active"] is False
    assert c.get(world.url).data["computation"]["income_tax"] == D("300000.00")
    # A return field's RAMIS reference, for a family of numbered lines too.
    r = p.post("/api/local-tax/rules/2024-25/fields/", {"entity_type": "company", "code": "T3", "official": "Cage 1250"}, format="json")
    assert r.status_code == 200
    field = next(f for s in c.get(world.url).data["return"]["sections"] for f in s["fields"] if f["code"] == "T3")
    assert field["validated"] and field["official"] == "Cage 1250"


def test_approving_figures_on_unvalidated_rules_needs_an_acknowledgement(world):  # noqa: F811
    c, lead = api(world.pat), api(world.lee)
    c.patch(world.url, {"entity_type": "company", "legal_name": "ABC", "tin": "1", "nic_or_reg": "PV1", "fy_end": "2025-03-31", "activity": "Trade",
                        "data": {"computation": {"pbt_manual": "1000000"}}}, format="json")
    c.put(world.url + "tb/", {"rows": [{"code": "4000", "name": "Sales", "amount": "-100"}, {"code": "1000", "name": "Bank", "amount": "100"}]},
          format="json")
    for s in ("questionnaire", "fs"):
        assert lead.post(world.url + f"stages/{s}/", {"status": "approved"}, format="json").status_code == 200
    r = lead.post(world.url + "stages/computation/", {"status": "approved"}, format="json")
    assert r.status_code == 409 and r.data["needs_acknowledgement"] and "company.standard_rate" in r.data["unvalidated"]
    r = lead.post(world.url + "stages/computation/", {"status": "approved", "acknowledge_unvalidated": True}, format="json")
    assert r.status_code == 200
    assert "approved_with_unvalidated_rules" in {e["action"] for e in c.get(world.url + "events/").data["events"]}


def test_the_card_shows_the_full_statements_and_the_schedules(world):  # noqa: F811
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "audited": True, "fy_end": "2025-03-31", "data": {
        "loss_history": [{"ya": "2022/23", "amount": "1000"}],
        "fixed_assets": [{"description": "Lathe", "asset_class": "plant_machinery", "cost": "10000"}]}}, format="json")
    rows = [{"code": c_, "name": n, "amount": a, "comparative": p} for c_, n, a, p in TB2]
    st = c.put(world.url + "tb/", {"rows": rows}, format="json").data
    dp = st["statements"]
    assert dp["cash_flows"]["check"]["passed"] and dp["equity"]["check"]["passed"] and st["report"]["kind"] == "audit"
    comp = st["computation"]
    assert comp["capital_allowance_schedule"]["totals"]["allowance"] == D("2000.00")
    assert comp["loss_schedule"]["totals"]["utilised"] == D("1000.00")
    keys = {s["key"] for s in st["return"]["sections"]}
    assert {"sch_ca", "sch_losses"} <= keys
    pdf = c.get(world.url + "export/fs.pdf")
    xlsx = c.get(world.url + "export/computation.xlsx")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF" and xlsx.status_code == 200


def test_documents_read_by_ai_become_records_only_once_confirmed(world, monkeypatch):  # noqa: F811
    from django.core.files.base import ContentFile

    from apps.issues.models import Attachment

    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company"}, format="json")
    att = Attachment.objects.create(issue=world.issue, file=ContentFile(b"x", name="far.pdf"), filename="far.pdf", uploaded_by=world.pat)
    replies = {
        "fixed_assets": {"kind": "fixed_assets", "summary": "", "gaps": [], "year_of_assessment": "",
                         "lines": [{"description": "Lathe", "amount": "10000", "category": "plant_machinery", "comparative": "2000", "date": "2023-04-01",
                                    "cite": "row 2"}]},
        "prior_return": {"kind": "prior_return", "summary": "", "gaps": [], "year_of_assessment": "2023/24",
                         "lines": [{"description": "Losses carried forward", "amount": "75000", "category": "losses_cf", "cite": "cage 900"},
                                   {"description": "Taxable income", "amount": "0", "category": "taxable_income", "cite": "cage 400"}]},
        "general_ledger": {"kind": "general_ledger", "summary": "", "gaps": [], "year_of_assessment": "",
                           "lines": [{"code": "4000", "description": "Sales - inv 1", "amount": "-60"}, {"code": "4000", "description": "Sales - inv 2", "amount": "-40"},
                                     {"code": "1000", "description": "Bank - receipts", "amount": "100"}]},
    }
    for kind, reply in replies.items():
        monkeypatch.setattr(ai, "_call", lambda path, body, timeout=180, reply=reply: reply)
        ex = c.post(world.url + "ai/extract/", {"attachment_id": att.id, "kind": kind}, format="json").data["extraction"]
        assert Extraction.objects.get(pk=ex["id"]).status == "pending"
        r = c.post(world.url + f"extractions/{ex['id']}/decide/", {"decision": "confirm", "use_as": kind}, format="json")
        assert r.status_code == 200, r.data
    data = r.data["engagement"]["data"]
    assert data["fixed_assets"][0]["ca_claimed_bf"] == "2000.00" and data["fixed_assets"][0]["source"].startswith("far.pdf")
    assert data["loss_history"] == [{"id": data["loss_history"][0]["id"], "ya": "2023/24", "amount": "75000.00", "source": "far.pdf cage 900"}]
    assert data["prior_year"]["ya"] == "2023/24"
    tb = {ln["code"]: ln["amount"] for ln in r.data["financials"]["tb"]}
    assert tb == {"1000": D("100.00"), "4000": D("-100.00")}  # the ledger summed by account
