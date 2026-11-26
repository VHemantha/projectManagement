"""A client's change request made through the AI Assistant's chat (AFIT, 26 Nov 2026): Local_Tax_AI proposes the
changes, code checks them and works out every amount, and nothing changes until the accountant applies each one - a
journal or a tax adjustment only as a proposal, approved like any other."""
from decimal import Decimal as D

import pytest

from apps.localtax import ai
from apps.localtax.models import Adjustment, EngagementEvent

from .test_api import api, world  # noqa: F401 - the fixture

pytestmark = pytest.mark.django_db

TB = [{"code": "1100", "name": "Cash at bank", "amount": "500000", "heading": "cash"},
      {"code": "2110", "name": "Accruals", "amount": "-50000", "heading": "trade_payables"},
      {"code": "3000", "name": "Stated capital", "amount": "-1000000", "heading": "share_capital"},
      {"code": "4000", "name": "Sales", "amount": "-1450000", "heading": "revenue"},
      {"code": "6100", "name": "Rent", "amount": "1000000", "heading": "admin_expenses"},
      {"code": "6900", "name": "Sundry expenses", "amount": "1000000", "heading": "admin_expenses"}]


def company(c, url):
    assert c.patch(url, {"entity_type": "company", "fy_end": "2025-03-31", "legal_name": "ABC Trading (Pvt) Ltd",
                         "address": "1 Main Street, Kandy"}, format="json").status_code == 200
    assert c.put(url + "tb/", {"rows": TB}, format="json").status_code == 200


def ask(c, url, monkeypatch, changes, question="The client asked for some changes."):
    seen = {}

    def fake(path, body, timeout=180):
        seen.update(path=path, body=body)
        return {"answer": "Here is what I would change.", "points": [], "uncertain": False, "what_if": None, "changes": changes}

    monkeypatch.setattr(ai, "_call", fake)
    r = c.post(url + "ai/chat/", {"question": question}, format="json")
    assert r.status_code == 200, r.data
    return r.data["message"], seen


def apply(c, url, msg, n, decision="apply"):
    return c.post(f"{url}messages/{msg['id']}/changes/{n}/", {"decision": decision}, format="json")


def test_the_agent_sees_what_a_request_may_change_and_its_changes_are_checked(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    msg, seen = ask(c, world.url, monkeypatch, [
        {"type": "field", "target": "address", "value": "12 Galle Road, Colombo 3", "reason": "The client moved."},
        {"type": "journal", "target": "Rent corrected to the lease", "value": "6100 | =1200000; 2110 | balance", "reason": "Rent was 1.2 million."},
        {"type": "note", "target": "events", "value": "No events after the reporting period.", "reason": "The client confirmed none."},
        {"type": "heading", "target": "6900", "value": "distribution_expenses", "reason": "Sundry costs are selling costs."},
        {"type": "field", "target": "entity_type", "value": "partnership", "reason": ""},  # not a field the chat may change
        {"type": "journal", "target": "x", "value": "9999 | 100; 2110 | balance", "reason": ""},  # an account the TB doesn't have
        {"type": "note", "target": "made_up", "value": "x", "reason": ""},
    ])
    ctx = seen["body"]["context"]
    assert ctx["client_info"]["address"] == "1 Main Street, Kandy" and set(ctx["notes_editable"]) == {"events", "contingencies", "related"}
    assert "revenue" in ctx["policy_keys"]
    changes = msg["data"]["changes"]
    assert [ch["type"] for ch in changes] == ["field", "journal", "note", "heading"]
    assert (changes[0]["from"], changes[0]["to"]) == ("1 Main Street, Kandy", "12 Galle Road, Colombo 3")
    # The journal's amounts are code's: the difference from the current balance, and the balancing line.
    assert [(ln["code"], ln["amount"]) for ln in changes[1]["lines"]] == [("6100", "200000.00"), ("2110", "-200000.00")]
    assert (changes[1]["lines"][0]["was"], changes[1]["lines"][0]["sets"]) == ("1000000.00", "1200000.00")
    assert changes[3]["from"] == "Administrative expenses" and changes[3]["to"] == "Selling and distribution expenses"
    assert len(msg["data"]["changes_dropped"]) == 3 and any("9999" in d for d in msg["data"]["changes_dropped"])
    # Nothing has changed yet.
    st = c.get(world.url).data
    assert st["engagement"]["address"] == "1 Main Street, Kandy" and not st["adjustments"]


def test_the_accountant_applies_each_change_and_a_journal_waits_for_approval(world, monkeypatch):  # noqa: F811
    c, lead = api(world.pat), api(world.lee)
    company(c, world.url)
    msg, _ = ask(c, world.url, monkeypatch, [
        {"type": "field", "target": "address", "value": "12 Galle Road, Colombo 3", "reason": "The client moved."},
        {"type": "journal", "target": "Rent corrected to the lease", "value": "6100 | =1200000; 2110 | balance", "reason": "Rent was 1.2 million."},
        {"type": "policy", "target": "revenue", "value": "Revenue is recognised when goods are delivered.", "reason": "One revenue stream."},
        {"type": "heading", "target": "6900", "value": "distribution_expenses", "reason": "Selling costs."},
        {"type": "note", "target": "related", "value": "The directors lent the company Rs. 1 million, interest free.", "reason": "Director's loan."},
    ])
    r = apply(c, world.url, msg, 0)
    assert r.status_code == 200 and r.data["engagement"]["address"] == "12 Galle Road, Colombo 3"
    assert apply(c, world.url, msg, 0).status_code == 409  # applied once only
    # The journal is proposed, not posted: the statements change only once a reviewer approves it.
    r = apply(c, world.url, msg, 1)
    assert r.status_code == 200
    (je,) = [a for a in r.data["adjustments"] if a["kind"] == "journal"]
    assert je["status"] == "proposed" and je["ref"].startswith("JE-") and je["reason"].startswith("Client request (via the AI Assistant)")
    rent = lambda st: next(ln for ln in st["financials"]["tb"] if ln["code"] == "6100")["amount"]  # noqa: E731
    assert D(str(rent(r.data))) == D("1000000")
    assert lead.post(f"{world.url}adjustments/{je['id']}/decide/", {"decision": "approve"}, format="json").status_code == 200
    assert D(str(rent(c.get(world.url).data))) == D("1200000")
    assert apply(c, world.url, msg, 2).status_code == 200
    assert apply(c, world.url, msg, 3).status_code == 200
    r = apply(c, world.url, msg, 4)
    eng = r.data["engagement"]
    assert eng["data"]["policy_text"]["revenue"] == "Revenue is recognised when goods are delivered."
    assert eng["data"]["note_text"]["related"].startswith("The directors lent")
    assert next(ln for ln in r.data["financials"]["tb"] if ln["code"] == "6900")["heading"] == "distribution_expenses"
    stored = c.get(world.url + "messages/").data["messages"][-1]["data"]["changes"]
    assert [ch["status"] for ch in stored] == ["applied"] * 5 and stored[1]["result"].startswith(je["ref"])
    assert EngagementEvent.objects.filter(engagement__issue=world.issue, action="client_change_applied").count() == 5


def test_a_journal_is_worked_out_again_when_the_balances_moved_and_a_change_can_be_dismissed(world, monkeypatch):  # noqa: F811
    c, lead = api(world.pat), api(world.lee)
    company(c, world.url)
    msg, _ = ask(c, world.url, monkeypatch, [
        {"type": "journal", "target": "Rent corrected", "value": "6100 | =1200000; 2110 | balance", "reason": "Rent was 1.2 million."},
        {"type": "field", "target": "tin", "value": "123456789", "reason": "The client's TIN."},
    ])
    # Meanwhile another journal moves the rent by 50,000 and is approved.
    c.post(world.url + "adjustments/", {"kind": "journal", "reason": "Rent accrual", "lines": [
        {"code": "6100", "amount": "50000"}, {"code": "2110", "amount": "-50000"}]}, format="json")
    other = Adjustment.objects.get(engagement__issue=world.issue)
    lead.post(f"{world.url}adjustments/{other.id}/decide/", {"decision": "approve"}, format="json")
    r = apply(c, world.url, msg, 0)
    assert r.status_code == 409 and "worked out again" in r.data["detail"]
    fresh = c.get(world.url + "messages/").data["messages"][-1]["data"]["changes"][0]
    assert [(ln["code"], ln["amount"]) for ln in fresh["lines"]] == [("6100", "150000.00"), ("2110", "-150000.00")]
    assert apply(c, world.url, msg, 0).status_code == 200  # the accountant has seen the new amounts
    assert apply(c, world.url, msg, 1, "dismiss").status_code == 200
    assert c.get(world.url).data["engagement"]["tin"] != "123456789"
    assert apply(c, world.url, msg, 1).status_code == 409


def test_a_tax_line_is_a_proposed_tax_adjustment_and_an_accounting_line_needs_a_journal(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    levers = c.get(world.url).data["levers"]
    tax = next((lv for lv in levers if lv["scope"] == "tax"), None)
    acct = next(lv for lv in levers if lv["scope"] == "accounting")
    changes = [{"type": "tax_adjustment", "target": acct["key"], "value": "1", "reason": "x"}]
    if tax:
        changes.insert(0, {"type": "tax_adjustment", "target": tax["key"], "value": "25,000", "reason": "Donation receipt found."})
    msg, _ = ask(c, world.url, monkeypatch, changes)
    assert any("journal" in d for d in msg["data"]["changes_dropped"])
    if tax:
        r = apply(c, world.url, msg, 0)
        (adj,) = r.data["adjustments"]
        assert (adj["kind"], adj["status"], D(str(adj["proposed"]))) == ("tax", "proposed", D("25000"))


def test_a_question_gives_no_changes_and_others_cards_are_out_of_reach(world, monkeypatch):  # noqa: F811
    c = api(world.pat)
    company(c, world.url)
    msg, _ = ask(c, world.url, monkeypatch, [], question="What is the tax payable?")
    assert "changes" not in msg["data"]
    assert c.post(f"{world.url}messages/{msg['id']}/changes/0/", {"decision": "apply"}, format="json").status_code == 404
    from apps.localtax.tests.test_api import person

    stranger = person("sam")
    assert api(stranger).post(f"{world.url}messages/{msg['id']}/changes/0/", {"decision": "apply"}, format="json").status_code in (403, 404)
