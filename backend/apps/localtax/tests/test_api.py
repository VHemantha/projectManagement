"""The Local Tax workflow's API (AFIT, 22 Nov 2026): only Team 3 > Local's cards; the questionnaire, trial
balance, statements, computation, reverse analysis and draft return connected; only approved, evidenced
adjustments reach the figures; every change in the audit trail; exports; Local_Tax_AI's answers checked."""
import io
from decimal import Decimal as D

import pytest
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.issues.models import Issue
from apps.localtax import ai
from apps.localtax.models import AiMessage, TaxEngagement
from apps.orgs.models import Organization
from apps.precheck.tests.test_direction_drafting import make_job
from apps.teams.models import Team, TeamMembership

pytestmark = pytest.mark.django_db

TB = [  # ABC Trading (Pvt) Ltd, as AFIT's screens (debit +)
    {"code": "4000", "name": "Sales", "amount": "-50000000", "comparative": "-46200000"},
    {"code": "5000", "name": "Cost of sales", "amount": "32500000", "comparative": "29800000"},
    {"code": "4900", "name": "Other income", "amount": "-750000", "comparative": "-680000"},
    {"code": "6100", "name": "Administrative expenses - salaries", "amount": "4800000", "comparative": "4350000"},
    {"code": "6500", "name": "Advertising and selling", "amount": "2350000", "comparative": "2150000"},
    {"code": "7000", "name": "Loan interest", "amount": "1200000", "comparative": "1050000"},
    {"code": "1000", "name": "Bank - Commercial Bank", "amount": "23900000", "comparative": "0"},
    {"code": "3000", "name": "Stated capital", "amount": "-14000000", "comparative": "0"},
]


def person(name, **kw):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title(), **kw)


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def world():
    from apps.projects.models import ProjectMembership

    pat, lee, olga = person("pat"), person("lee"), person("olga")
    issue = make_job(olga, "Local", "LOCAL", summary="ABC Trading (Pvt) Ltd - YA 2024/25")  # Olga owns the project
    ProjectMembership.objects.create(project=issue.project, user=pat, role=ProjectMembership.Role.MEMBER)  # Pat prepares
    team = Team.objects.create(name="Team 3", organization=Organization.get_solo())
    client = issue.project.client
    client.team, client.workflow = team, "local_tax"
    client.save()
    TeamMembership.objects.create(team=team, user=lee, role=TeamMembership.Role.LEAD)
    other = make_job(pat, "RWCA", "RWCA", summary="Some other client")

    class W:
        pass

    w = W()
    w.pat, w.lee, w.issue, w.other = pat, lee, issue, other
    w.url = f"/api/local-tax/tasks/{issue.key}/"
    return w


def test_only_team_3_local_cards_have_the_workflow(world):
    assert api(world.pat).get(f"/api/local-tax/tasks/{world.other.key}/").status_code == 404
    assert api(world.pat).get(f"/api/issues/{world.other.key}/").data["workflow"] == ""
    assert api(world.pat).get(f"/api/issues/{world.issue.key}/").data["workflow"] == "local_tax"
    r = api(world.pat).get(world.url)
    assert r.status_code == 200 and r.data["engagement"]["legal_name"] == "ABC Trading (Pvt) Ltd - YA 2024/25"
    assert set(r.data["engagement"]["stages"]) == {"questionnaire", "fs", "computation", "return"}


def test_the_migration_marks_only_local_in_team_3():
    from importlib import import_module

    mark = import_module("apps.clients.migrations.0005_local_tax_workflow").mark
    org = Organization.get_solo()
    t3, t1 = Team.objects.create(name="Team 3", organization=org), Team.objects.create(name="Team 1", organization=org)
    local = Client.objects.create(organization=org, name="Local", team=t3)
    elsewhere = Client.objects.create(organization=org, name="Local", team=t1)
    rwca = Client.objects.create(organization=org, name="RWCA", team=t3)
    from django.apps import apps as django_apps

    mark(django_apps, None)
    assert [c.workflow for c in Client.objects.filter(pk__in=[local.pk, elsewhere.pk, rwca.pk]).order_by("pk")] == ["local_tax", "", ""]


def test_the_four_stages_connect_from_the_questionnaire_to_the_draft_return(world):
    c = api(world.pat)
    r = c.patch(world.url, {"entity_type": "company", "year_of_assessment": "2024/25", "fy_end": "2025-03-31", "tin": "114567890",
                            "nic_or_reg": "PV 123456", "legal_name": "ABC Trading (Pvt) Ltd", "activity": "Trading of electrical and electronic items.",
                            "expected_tax": "70000", "expected_basis": "remaining",
                            "data": {"payments": [{"type": "AIT", "amount": "200000", "reference": "WHT/AIT"}, {"type": "provisional", "amount": "800000"}],
                                     "qualifying_payments": "300000", "losses_bf": "1200000"}}, format="json")
    assert r.status_code == 200, r.data
    assert r.data["engagement"]["stages"]["questionnaire"]["status"] == "in_progress"
    r = c.put(world.url + "tb/", {"rows": TB}, format="json")
    fin = r.data["financials"]
    assert fin["pl"]["current"]["gross_profit"] == D("17500000.00") and fin["pbt"] == D("9900000.00")
    assert all(ch["passed"] for ch in fin["checks"]), fin["checks"]
    r = c.patch(world.url, {"data": {"computation": {
        "add_backs": [{"label": "Entertainment expenses", "amount": "250000"}, {"label": "Depreciation - excess over tax allowance", "amount": "180000"},
                      {"label": "Other disallowable expenses", "amount": "120000"}],
        "capital_allowances": [{"label": "Capital allowances (tax)", "amount": "1850000"}],
        "special_income": [{"label": "Qualifying export service income", "amount": "7100000", "rate_key": "qualifying_export_services"}]}}}, format="json")
    comp = r.data["computation"]
    assert comp["taxable_income"] == D("7100000.00") and comp["income_tax"] == D("1065000.00") and comp["payable"] == D("65000.00")
    assert r.data["engagement"]["stages"]["computation"]["status"] == "in_progress"
    rev = r.data["reverse"]
    assert rev["expected"] == D("70000.00") and rev["variance"] == D("-5000.00") and rev["scenarios"]
    ret = r.data["return"]
    assert next(f for s in ret["sections"] for f in s["fields"] if f["code"] == "T3")["value"] == D("65000.00")
    assert {m["code"] for m in ret["missing"]} == {"X1", "X2"}
    events = c.get(world.url + "events/").data["events"]
    assert {"edited", "trial_balance", "created"} <= {e["action"] for e in events}


def test_only_an_approved_evidenced_correction_changes_the_figures(world):
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "expected_tax": "70000", "expected_basis": "remaining",
                        "data": {"payments": [{"type": "provisional", "amount": "1000000"}],
                                 "computation": {"capital_allowances": [{"id": "ca1", "label": "Capital allowances (tax)", "amount": "1850000"}],
                                                 "special_income": [{"label": "Export", "amount": "7100000", "rate_key": "qualifying_export_services"}]}}},
            format="json")
    c.put(world.url + "tb/", {"rows": TB}, format="json")
    before = c.get(world.url).data["computation"]["payable"]
    # A hypothetical: nothing stored.
    eff = c.post(world.url + "reverse/effect/", {"lever": "capital_allowances:ca1", "proposed": "1800000"}, format="json").data
    assert eff["hypothetical"] and eff["original"] == D("1850000.00") and eff["tax_after"] > eff["tax_before"]
    assert c.get(world.url).data["computation"]["payable"] == before
    # A tax-only correction, proposed: still not in the figures.
    r = c.post(world.url + "adjustments/", {"kind": "reverse", "target": "capital_allowances:ca1", "proposed": "1800000",
                                            "reason": "Fixed asset register shows a disposal in March."}, format="json")
    assert r.status_code == 200, r.data
    adj = r.data["adjustments"][0]
    assert adj["status"] == "proposed" and adj["original"] == "1850000.00" and adj["difference"] == "-50000.00"
    assert r.data["computation"]["payable"] == before
    # Only a reviewer, lead or admin approves; a correction needs its evidence first.
    assert c.post(world.url + f"adjustments/{adj['id']}/decide/", {"decision": "approve"}, format="json").status_code == 403
    lead = api(world.lee)
    no_evidence = lead.post(world.url + f"adjustments/{adj['id']}/decide/", {"decision": "approve"}, format="json")
    assert no_evidence.status_code == 400 and "evidence" in no_evidence.data["detail"]
    c.patch(world.url + f"adjustments/{adj['id']}/", {"evidence_note": "FAR 2025, disposal of delivery van"}, format="json")
    ok = lead.post(world.url + f"adjustments/{adj['id']}/decide/", {"decision": "approve", "note": "Agreed to the FAR."}, format="json")
    # 50,000 more taxable income, above the 7.1m qualifying export income: at the standard 30%, not 15%.
    assert ok.status_code == 200 and ok.data["computation"]["payable"] == before + D("15000.00")
    assert ok.data["financials"]["pbt"] == D("9900000.00")  # tax-only: the accounting profit is unchanged
    assert ok.data["adjustments"][0]["history"][0]["reason"] == "Fixed asset register shows a disposal in March."


def test_an_accounting_correction_is_a_balanced_journal_and_moves_the_statements(world):
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company"}, format="json")
    c.put(world.url + "tb/", {"rows": TB}, format="json")
    bad = c.post(world.url + "adjustments/", {"kind": "journal", "reason": "Accrue the audit fee.", "lines": [{"code": "6100", "amount": "100000"}]},
                 format="json")
    assert bad.status_code == 400
    r = c.post(world.url + "adjustments/", {"kind": "journal", "label": "Audit fee accrual", "reason": "Accrue the audit fee.",
                                            "lines": [{"code": "6100", "amount": "100000"}, {"code": "2100", "name": "Accrued expenses", "amount": "-100000"}]},
               format="json")
    adj = r.data["adjustments"][0]
    r = api(world.lee).post(world.url + f"adjustments/{adj['id']}/decide/", {"decision": "approve"}, format="json")
    assert r.data["financials"]["pbt"] == D("9800000.00") and all(ch["passed"] for ch in r.data["financials"]["checks"])
    assert any(ln["code"] == "2100" and ln["heading"] == "trade_payables" for ln in r.data["financials"]["tb"])


def test_stages_are_approved_in_order_by_a_reviewer_and_reopen_on_a_change(world):
    c, lead = api(world.pat), api(world.lee)
    c.patch(world.url, {"entity_type": "company", "tin": "1", "fy_end": "2025-03-31", "activity": "Trading", "nic_or_reg": "PV 1"}, format="json")
    assert c.post(world.url + "stages/questionnaire/", {"status": "ready_for_review"}, format="json").status_code == 200
    assert c.post(world.url + "stages/questionnaire/", {"status": "approved"}, format="json").status_code == 403
    assert lead.post(world.url + "stages/fs/", {"status": "approved"}, format="json").status_code == 409  # questionnaire first
    assert lead.post(world.url + "stages/questionnaire/", {"status": "approved"}, format="json").status_code == 200
    r = c.patch(world.url, {"activity": "Trading of electrical items."}, format="json")
    assert r.data["engagement"]["stages"]["questionnaire"]["status"] == "in_progress"


def test_the_trial_balance_is_read_from_an_excel_file_and_a_persons_mapping_is_kept(world):
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company"}, format="json")
    wb = Workbook()
    ws = wb.active
    ws.append(["ABC Trading - Trial balance 31 March 2025"])
    ws.append(["Code", "Account", "Debit", "Credit", "Prior year"])
    for r in TB:
        a = D(r["amount"])
        ws.append([r["code"], r["name"], float(a) if a > 0 else None, float(-a) if a < 0 else None, float(D(r["comparative"]))])
    ws.append(["", "Total", 64750000, 64750000])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    buf.name = "TB.xlsx"
    r = c.post(world.url + "tb/upload/", {"file": buf}, format="multipart")
    assert r.status_code == 200, r.data
    assert len(r.data["financials"]["tb"]) == 8 and r.data["financials"]["pbt"] == D("9900000.00")
    c.patch(world.url + "tb/4900/", {"heading": "revenue"}, format="json")
    buf.seek(0)
    r = c.post(world.url + "tb/upload/", {"file": buf}, format="multipart")
    assert next(ln for ln in r.data["financials"]["tb"] if ln["code"] == "4900")["heading"] == "revenue"


def test_the_documents_export_as_pdf_and_excel(world):
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "legal_name": "ABC Trading (Pvt) Ltd"}, format="json")
    c.put(world.url + "tb/", {"rows": TB}, format="json")
    for doc in ("fs", "computation", "return"):
        pdf = c.get(world.url + f"export/{doc}.pdf")
        assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    xlsx = c.get(world.url + "export/computation.xlsx")
    ws = load_workbook(io.BytesIO(xlsx.content)).active
    values = [r[0] for r in ws.iter_rows(values_only=True) if r[0]]
    assert "Accounting profit before tax" in values and "Final tax payable" in values


def test_local_tax_ai_answers_are_checked_and_a_what_if_uses_the_engine(world, monkeypatch):
    c = api(world.pat)
    c.patch(world.url, {"entity_type": "company", "data": {"computation": {"add_backs": [{"id": "a1", "label": "Entertainment", "amount": "250000"}]}}},
            format="json")
    c.put(world.url + "tb/", {"rows": TB}, format="json")
    sent = {}

    def fake(path, body, timeout=180):
        sent[path] = body
        if path == "/v1/chat":
            return {"answer": "If entertainment add-backs fall by 100,000, the tax falls - see the figures below.", "points": ["Hypothetical."],
                    "what_if": {"lever": "add_backs:a1", "proposed": "150000"}}
        if path == "/v1/map-tb":
            return {"suggestions": [{"code": "4900", "heading": "other_income", "reason": "Sundry income"},
                                    {"code": "9999", "heading": "revenue"}, {"code": "4000", "heading": "not_a_heading"}]}
        return {}

    monkeypatch.setattr(ai, "_call", fake)
    r = c.post(world.url + "ai/chat/", {"question": "What if entertainment expenses change by Rs. 100,000?"}, format="json")
    msg = r.data["message"]
    assert msg["role"] == "ai" and msg["data"]["what_if"]["hypothetical"] is True
    assert D(msg["data"]["what_if"]["tax_before"]) - D(msg["data"]["what_if"]["tax_after"]) == D("30000.00")  # 100,000 at 30%, by the engine
    assert sent["/v1/chat"]["context"]["engagement"]["entity_type"] == "company"
    assert AiMessage.objects.filter(engagement__issue=world.issue).count() == 2  # kept: the conversation carries on
    assert [m["role"] for m in c.get(world.url + "messages/").data["messages"]] == ["person", "ai"]
    s = c.post(world.url + "ai/map-tb/", {}, format="json").data
    assert s["suggestions"] == [{"code": "4900", "heading": "other_income", "reason": "Sundry income"}]  # unknown codes and headings dropped


def test_someone_who_cannot_open_the_card_gets_nothing(world):
    stranger = person("zed")
    from apps.precheck.services import can_open_job

    if not can_open_job(stranger, world.issue):
        assert api(stranger).get(world.url).status_code == 403
    assert not TaxEngagement.objects.exclude(issue=world.issue).exists() and Issue.objects.filter(pk=world.other.pk).exists()
