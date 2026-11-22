"""The Local Tax engine (AFIT, 22 Nov 2026): every figure by code, from the year's rules. The cases follow AFIT's
screens (ABC Trading (Pvt) Ltd, YA 2024/25) and the YA 2025/26 individual bands. The rates are the draft rules
(validated: False) - the tests pin the engine's arithmetic, not the law."""
from decimal import Decimal as D

import pytest

from apps.localtax.engine import fs, returns, reverse
from apps.localtax.engine.rules import MissingRules, Rules
from apps.localtax.engine.tax import band_tax, compute

ABC = {
    "entity_type": "company", "pbt": "9900000",
    "add_backs": [{"id": 1, "label": "Entertainment expenses", "amount": "250000"},
                  {"id": 2, "label": "Depreciation - excess over tax allowance", "amount": "180000"},
                  {"id": 3, "label": "Other disallowable expenses", "amount": "120000"}],
    "deductions": [], "capital_allowances": [{"id": 4, "label": "Capital allowances (tax)", "amount": "1850000"}],
    "qualifying_payments": "300000", "losses_bf": "1200000",
    "special_income": [{"id": 9, "label": "Qualifying export service income", "amount": "7100000", "rate_key": "qualifying_export_services"}],
    "payments": [{"id": 7, "type": "AIT", "amount": "200000", "reference": "WHT/AIT"}, {"id": 8, "type": "provisional", "amount": "800000"}],
}


def test_the_company_computation_matches_the_screens():
    r = compute(ABC, Rules("2024/25"))
    assert r["total_add_backs"] == D("550000.00") and r["taxable_income"] == D("7100000.00")
    assert r["income_tax"] == D("1065000.00") and r["credits"] == D("1000000.00") and r["payable"] == D("65000.00")
    labels = [ln["label"] for ln in r["lines"]]
    assert "Qualifying export service income: 7,100,000.00 × 15%" in labels and labels[-1] == "Final tax payable"
    assert r["unvalidated"] and any(x["rule"] == "company.special_rates.qualifying_export_services" for x in r["rules"])


def test_a_company_without_enough_special_income_pays_the_standard_rate_on_the_rest():
    r = compute({**ABC, "special_income": [{"id": 9, "label": "Export", "amount": "1000000", "rate_key": "qualifying_export_services"}]}, Rules("2024/25"))
    assert r["income_tax"] == D("150000.00") + D("6100000") * D("0.30")


def test_individual_bands_for_ya_2025_26():
    tax, used = band_tax(D("3200000"), Rules("2025/26").value("individual", "bands"))
    assert tax == D("672000.00") and [u["tax"] for u in used] == [D("60000.00"), D("90000.00"), D("120000.00"), D("150000.00"), D("252000.00")]
    r = compute({"entity_type": "individual", "income": [{"id": 1, "category": "employment", "amount": "5000000"}],
                 "payments": [{"id": 1, "type": "APIT", "amount": "500000"}]}, Rules("2025/26"))
    assert r["taxable_income"] == D("3200000.00") and r["income_tax"] == D("672000.00") and r["payable"] == D("172000.00")


def test_foreign_service_income_gets_the_15_percent_rate_only_when_its_conditions_are_met():
    base = {"entity_type": "individual", "income": [{"id": 1, "category": "foreign_service", "description": "IT services to a UK client",
                                                     "amount": "2000000", "foreign": {"service_used_outside": True, "received_in_fx_through_bank": True}}]}
    r = compute(base, Rules("2025/26"))
    assert r["income_tax"] == D("300000.00") and r["special_income"] == D("2000000.00")
    no_bank = {**base, "income": [{**base["income"][0], "foreign": {"service_used_outside": True, "received_in_fx_through_bank": False}}]}
    r2 = compute(no_bank, Rules("2025/26"))
    assert r2["special_income"] == D("0.00") and r2["income_tax"] == band_tax(D("200000"), Rules("2025/26").value("individual", "bands"))[0]
    # Not in the YA 2024/25 rules: normal rates, never 15% by default.
    assert compute(base, Rules("2024/25"))["special_income"] == D("0.00")


def test_final_withholding_and_exempt_income_are_shown_apart_and_never_credited():
    r = compute({"entity_type": "individual", "income": [
        {"id": 1, "category": "business", "amount": "4000000", "expenses": [{"amount": "1000000", "classification": "allowable"},
                                                                          {"amount": "50000", "classification": "disallowable"}]},
        {"id": 2, "category": "dividend", "amount": "300000"},
        {"id": 3, "category": "other", "amount": "100000", "treatment": "exempt"}],
        "payments": [{"id": 1, "type": "final_wht", "amount": "45000"}, {"id": 2, "type": "WHT", "amount": "20000"}]}, Rules("2024/25"))
    assert r["assessable_income"] == D("3000000.00") and r["final_wht_income"] == D("300000.00") and r["exempt_income"] == D("100000.00")
    assert r["credits"] == D("20000.00")  # the final WHT is shown, not credited
    assert any("final withholding - not credited" in ln["label"] for ln in r["lines"])


def test_the_reverse_calculation_uses_the_complete_computation_not_one_rate():
    out = reverse.analyse(ABC, Rules("2024/25"), "70000", "remaining")
    assert out["calculated"] == D("65000.00") and out["variance"] == D("-5000.00")
    # 15% covers the qualifying 7.1m; income above it is at 30% - so 7,116,666.67, not 70,000 / 15%.
    assert abs(out["required_taxable_income"] - D("7116666.67")) <= D("0.02")
    caps = next(s for s in out["scenarios"] if s["label"] == "Capital allowances (tax)")
    assert caps["feasible"] and abs(caps["change"] - D("-16666.67")) <= D("0.02")
    eff = reverse.effect(ABC, Rules("2024/25"), caps["key"], caps["proposed"], "70000", "remaining")
    assert eff["hypothetical"] and abs(eff["remaining_variance"]) <= D("0.10") and eff["original"] == D("1850000.00")


def test_an_unreachable_expected_tax_is_said_to_be_unsupported():
    out = reverse.analyse(ABC, Rules("2024/25"), "-5000000", "remaining")
    assert out["required_taxable_income"] is None and "can't be reached" in out["unsupported"]


def test_a_year_without_rules_is_refused_not_guessed():
    with pytest.raises(MissingRules):
        Rules("2019/20")


def test_the_financial_statements_from_a_mapped_trial_balance():
    tb = [{"code": "4000", "name": "Sales", "amount": "-50000000", "comparative": "-46200000"},
          {"code": "5000", "name": "Cost of sales", "amount": "32500000", "comparative": "29800000"},
          {"code": "6100", "name": "Salaries", "amount": "4800000", "comparative": "4350000"},
          {"code": "1500", "name": "Bank - Commercial Bank", "amount": "13700000", "comparative": "12050000"},
          {"code": "3000", "name": "Stated capital", "amount": "-1000000", "comparative": "-1000000"}]
    for ln in tb:
        ln["heading"] = fs.suggest_heading(ln["name"])
    assert [ln["heading"] for ln in tb] == ["revenue", "cost_of_sales", "admin_expenses", "cash", "share_capital"]
    s = fs.statements(tb)
    assert s["pl"]["current"]["gross_profit"] == D("17500000.00") and s["pbt"] == D("12700000.00")
    assert s["pl"]["comparative"]["revenue"] == D("46200000.00")
    assert all(c["passed"] for c in s["checks"]), s["checks"]
    adjusted = fs.apply_adjustments(tb, [{"lines": [{"code": "6100", "amount": "100000"}, {"code": "1500", "amount": "-100000"}]}])
    assert fs.statements(adjusted)["pbt"] == D("12600000.00")


def test_the_draft_return_flags_missing_mandatory_fields():
    comp = compute(ABC, Rules("2024/25"))
    r = returns.build({"entity_type": "company", "legal_name": "ABC Trading (Pvt) Ltd", "tin": "114567890", "year_of_assessment": "2024/25"}, None, comp)
    missing = {m["code"] for m in r["missing"]}
    assert {"B3", "B6", "X1", "X2"} <= missing and "B1" not in missing and r["validated"] is False
    tax = next(s for s in r["sections"] if s["key"] == "tax")
    assert tax["fields"][2]["value"] == D("65000.00")
