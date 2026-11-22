"""The income tax computation, worked out by code (AFIT, 22 Nov 2026), for one year of assessment's rules.

`compute(inputs, rules)` takes the engagement's figures as plain data and returns every line of the computation
with its amount, the rule it rests on and any flag for review. Nothing here is the AI's. The same function is
what the reverse calculation (reverse.py) re-runs with one figure changed, so a scenario is always the complete
computation - progressive bands, special rates, credits - and never one rate divided into a target.

Inputs, companies:
  {"entity_type": "company", "pbt": amount, "add_backs": [{id, label, amount, note}],
   "deductions": [{id, label, amount, note}], "capital_allowances": [{id, label, asset_class, cost, amount}],
   "qualifying_payments": amount, "losses_bf": amount,
   "special_income": [{id, label, amount, rate_key}], "payments": [{id, type, amount, creditable}]}
Inputs, individuals:
  {"entity_type": "individual", "residency": "resident"|"non_resident",
   "income": [{id, category, description, amount, lkr_amount, treatment, foreign: {...}, expenses: [{amount, classification}]}],
   "qualifying_payments": amount, "losses_bf": amount, "payments": [...]}
"""
from decimal import ROUND_HALF_UP, Decimal

from . import schedules as SC
from .fs import d
from .rules import Rules

ZERO = Decimal("0")
CENT = Decimal("0.01")
FINAL_WHT_CATEGORIES = {"dividend"}
CREDITABLE_DEFAULT = {"APIT": True, "AIT": True, "WHT": True, "provisional": True, "foreign_tax_credit": True, "other": True, "final_wht": False}


def pct(rate: Decimal) -> str:
    """0.15 -> "15", 0.065 -> "6.5"."""
    return format((Decimal(rate) * 100).normalize(), "f")


def q(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


def line(key: str, label: str, amount, *, kind: str = "", note: str = "", rule: str = "", ref: str = "", source: str = "", level: int = 0) -> dict:
    return {"key": key, "label": label, "amount": q(d(amount)) if amount is not None else None, "kind": kind, "note": note, "rule": rule,
            "ref": ref, "source": source, "level": level}


def band_tax(taxable: Decimal, bands: list) -> tuple[Decimal, list[dict]]:
    """Tax on income through progressive bands [[width or None, rate], ...]: (tax, the bands used)."""
    left, tax, used = max(taxable, ZERO), ZERO, []
    for width, rate in bands:
        if left <= 0:
            break
        part = left if width is None else min(left, Decimal(str(width)))
        t = q(part * Decimal(str(rate)))
        used.append({"width": None if width is None else Decimal(str(width)), "rate": Decimal(str(rate)), "income": part, "tax": t})
        tax += t
        left -= part
    return tax, used


def _credits(payments: list[dict]) -> tuple[list[dict], list[dict]]:
    """(creditable payments, final withholding taxes - shown, never credited)."""
    creditable, final = [], []
    for p in payments or []:
        amount = d(p.get("amount"))
        if not amount:
            continue
        is_creditable = p.get("creditable")
        if is_creditable is None:
            is_creditable = CREDITABLE_DEFAULT.get(p.get("type", "other"), True)
        (creditable if is_creditable else final).append({**p, "amount": amount})
    return creditable, final


def compute(inputs: dict, rules: Rules) -> dict:
    if inputs.get("entity_type") == "individual":
        return _individual(inputs, rules)
    return _company(inputs, rules)


def _finish(lines, flags, tax, taxable, creditable, final, rules: Rules, extra: dict) -> dict:
    credits = sum((p["amount"] for p in creditable), ZERO)
    lines.append(line("credits_head", "Less: tax credits and payments", None, kind="head"))
    for p in creditable:
        lines.append(line(f"credit_{p.get('id', '')}", f"{p.get('type', 'Credit')}{(' - ' + p['reference']) if p.get('reference') else ''}", -p["amount"],
                          level=1, source=p.get("reference", "")))
    for p in final:
        lines.append(line(f"final_{p.get('id', '')}", f"{p.get('type', 'Final WHT')} (final withholding - not credited)", None, level=1,
                          note=f"{p['amount']:,.2f} deducted at source as a final tax: not a credit."))
    lines.append(line("total_credits", "Total tax credits and payments", -credits, kind="subtotal"))
    payable = q(tax - credits)
    lines.append(line("payable", "Final tax payable" if payable >= 0 else "Tax refundable", payable, kind="total"))
    return {"lines": lines, "taxable_income": q(taxable), "income_tax": q(tax), "credits": q(credits), "payable": payable,
            "flags": flags, "rules": rules.report(), "unvalidated": rules.unvalidated, **extra}


def _company(inputs: dict, rules: Rules) -> dict:
    lines, flags = [], []
    pbt = d(inputs.get("pbt"))
    lines.append(line("pbt", "Accounting profit before tax", pbt, kind="total"))
    lines.append(line("add_head", "Add: disallowable expenses and adjustments", None, kind="head"))
    add_total = ZERO
    for a in inputs.get("add_backs") or []:
        amount = d(a.get("amount"))
        add_total += amount
        lines.append(line(f"add_{a.get('id', '')}", a.get("label", "Add back"), amount, level=1, note=a.get("note", ""), source=a.get("source", "")))
    far = SC.capital_allowances(inputs.get("fixed_assets") or [], rules) if inputs.get("fixed_assets") else None
    if far:
        flags += far["flags"]
        for r in far["rows"]:
            if r["balancing_charge"]:
                add_total += r["balancing_charge"]
                lines.append(line(f"bc_{r['id']}", f"Balancing charge - {r['description']} (disposed)", r["balancing_charge"], level=1,
                                  rule="capital_allowances.balancing", source="Fixed asset register"))
    lines.append(line("total_add", "Total add backs", add_total, kind="subtotal"))
    lines.append(line("ded_head", "Less: allowable deductions", None, kind="head"))
    ded_total = ZERO
    for a in inputs.get("deductions") or []:
        amount = d(a.get("amount"))
        ded_total += amount
        lines.append(line(f"ded_{a.get('id', '')}", a.get("label", "Deduction"), -amount, level=1, note=a.get("note", ""), source=a.get("source", "")))
    for ca in inputs.get("capital_allowances") or []:
        amount = d(ca.get("amount")) if ca.get("amount") not in (None, "") else None
        rule_key = ca.get("asset_class") or ""
        if amount is None:
            rate = rules.value("capital_allowances", rule_key) if rule_key else None
            if rate is None:
                flags.append({"severity": "review", "text": f"No capital allowance rate for “{ca.get('label') or rule_key}”: enter the allowance."})
                amount = ZERO
            else:
                amount = q(d(ca.get("cost")) * rate)
        ded_total += amount
        ref = (rules.rule("capital_allowances", rule_key) or {}).get("ref", "") if rule_key else ""
        lines.append(line(f"ca_{ca.get('id', '')}", f"Capital allowance - {ca.get('label') or rule_key}", -amount, level=1, rule=f"capital_allowances.{rule_key}",
                          ref=ref))
    for r in (far or {}).get("rows") or []:
        if r["allowance"]:
            ded_total += r["allowance"]
            lines.append(line(f"far_{r['id']}", f"Capital allowance - {r['description']}", -r["allowance"], level=1,
                              rule=f"capital_allowances.{r['asset_class']}", ref=r["ref"], source="Fixed asset register"))
        if r["balancing_allowance"]:
            ded_total += r["balancing_allowance"]
            lines.append(line(f"ba_{r['id']}", f"Balancing allowance - {r['description']} (disposed)", -r["balancing_allowance"], level=1,
                              rule="capital_allowances.balancing", source="Fixed asset register"))
    statutory = pbt + add_total - ded_total
    qp = min(d(inputs.get("qualifying_payments")), max(statutory, ZERO))
    if qp:
        ded_total += qp
        lines.append(line("qualifying", "Qualifying payments", -qp, level=1, rule="individual.qualifying_payment_cap"))
    available = max(pbt + add_total - ded_total, ZERO)
    losses = min(d(inputs.get("losses_bf")), available)
    if d(inputs.get("losses_bf")):
        rules.rule("losses", "restriction")
        ded_total += losses
        lines.append(line("losses", "Tax losses brought forward (utilised)", -losses, level=1, rule="losses.restriction",
                          note=f"{d(inputs.get('losses_bf')) - losses:,.2f} carried forward." if d(inputs.get("losses_bf")) > losses else ""))
    lines.append(line("total_ded", "Total deductions", -ded_total, kind="subtotal"))
    taxable = pbt + add_total - ded_total + d(inputs.get("_taxable_shift"))
    loss = ZERO
    if taxable < 0:
        loss, taxable = -taxable, ZERO
        flags.append({"severity": "info", "text": f"A tax loss of {loss:,.2f} for the year: carried forward."})
    lines.append(line("taxable", "Taxable income", taxable, kind="total"))

    standard = rules.value("company", "standard_rate")
    if standard is None:
        flags.append({"severity": "blocking", "text": "No standard corporate rate in the year's rules: the tax can't be worked out."})
        standard = ZERO
    lines.append(line("rate_head", "Income tax", None, kind="head"))
    left, tax = taxable, ZERO
    for s in inputs.get("special_income") or []:
        rate_node = rules.rule("company", "special_rates", s.get("rate_key", "")) or {}
        rate = rules.value("company", "special_rates", s.get("rate_key", ""))
        part = min(d(s.get("amount")), left)
        if rate is None:
            flags.append({"severity": "review", "text": f"No rate in the year's rules for “{s.get('label') or s.get('rate_key')}”: taxed at the standard rate."})
            continue
        t = q(part * rate)
        tax += t
        left -= part
        lines.append(line(f"special_{s.get('id', '')}", f"{s.get('label') or rate_node.get('label', '')}: {part:,.2f} × {pct(rate)}%", t, level=1,
                          rule=f"company.special_rates.{s.get('rate_key')}", ref=rate_node.get("ref", "")))
    if left > 0 or not inputs.get("special_income"):
        t = q(left * standard)
        tax += t
        lines.append(line("standard", f"Standard rate: {left:,.2f} × {pct(standard)}%", t, level=1, rule="company.standard_rate",
                          ref=(rules.rule("company", "standard_rate") or {}).get("ref", "")))
    lines.append(line("income_tax", "Income tax", tax, kind="subtotal"))
    creditable, final = _credits(inputs.get("payments"))
    return _finish(lines, flags, tax, taxable, creditable, final, rules, {"loss_for_year": q(loss), "pbt": q(pbt),
                                                                          "total_add_backs": q(add_total), "total_deductions": q(ded_total),
                                                                          "capital_allowance_schedule": far,
                                                                          "loss_schedule": SC.losses(inputs.get("loss_history"), inputs.get("losses_bf"),
                                                                                                     losses, loss, rules.year)})


INCOME_LABELS = {"employment": "Employment income", "business": "Business / professional income", "rent": "Rental income",
                 "interest": "Interest income", "dividend": "Dividend income", "foreign_service": "Foreign service income",
                 "foreign_other": "Other foreign-source income", "investment_gain": "Gains from investment assets", "other": "Other income"}


def income_treatment(inc: dict, rules: Rules, residency: str = "resident") -> tuple[str, str]:
    """(treatment, why): taxable, exempt, final_wht or special_rate. A person's choice is kept; else by rule."""
    chosen = inc.get("treatment") or "auto"
    if chosen != "auto":
        return chosen, "Set by the accountant."
    cat = inc.get("category", "other")
    if cat in FINAL_WHT_CATEGORIES and residency == "resident":
        rules.rule("withholding", "dividend_final")
        return "final_wht", "Dividends to a resident: final withholding tax at source."
    if cat == "foreign_service":
        f = inc.get("foreign") or {}
        rate = rules.value("individual", "special_rates", "foreign_service")
        if rate is None:
            return "taxable", "No special rate for foreign service income in this year's rules: taxed at the normal rates."
        if f.get("service_used_outside") and f.get("received_in_fx_through_bank"):
            return "special_rate", f"Qualifying foreign service income: maximum rate {pct(rate)}% (conditions confirmed)."
        return "taxable", "Foreign service income without the statutory conditions confirmed: taxed at the normal rates."
    return "taxable", ""


def _individual(inputs: dict, rules: Rules) -> dict:
    lines, flags = [], []
    residency = inputs.get("residency", "resident")
    normal_by_cat: dict[str, Decimal] = {}
    special, exempt, final = [], [], []
    for inc in inputs.get("income") or []:
        gross = d(inc.get("lkr_amount") if inc.get("lkr_amount") not in (None, "") else inc.get("amount"))
        if not gross:
            continue
        expenses = inc.get("expenses") or []
        allowable = sum((d(e.get("amount")) for e in expenses if e.get("classification") == "allowable"), ZERO)
        if any(e.get("classification") == "clarify" for e in expenses):
            flags.append({"severity": "review", "text": f"Expenses for “{inc.get('description') or INCOME_LABELS.get(inc.get('category'), '')}” need "
                                                        "clarifying before they are deducted."})
        cat = inc.get("category", "other")
        if cat == "employment" and allowable:
            flags.append({"severity": "review", "text": "Expenses are not normally deductible from employment income: check them."})
        net = gross - allowable
        if cat == "rent":
            rate = rules.value("individual", "rent_relief_rate")
            if rate is not None:
                net -= q(gross * rate)
        treatment, why = income_treatment(inc, rules, residency)
        item = {**inc, "gross": gross, "net": net, "treatment": treatment, "why": why}
        if treatment == "exempt":
            exempt.append(item)
        elif treatment == "final_wht":
            final.append(item)
        elif treatment == "special_rate":
            special.append(item)
        else:
            normal_by_cat[cat] = normal_by_cat.get(cat, ZERO) + net
    lines.append(line("inc_head", "Assessable income", None, kind="head"))
    assessable = ZERO
    for cat, amount in normal_by_cat.items():
        assessable += amount
        lines.append(line(f"inc_{cat}", INCOME_LABELS.get(cat, cat), amount, level=1,
                          note="After 25% rent relief." if cat == "rent" and rules.value("individual", "rent_relief_rate") is not None else ""))
    lines.append(line("assessable", "Total assessable income", assessable, kind="subtotal"))
    qp = min(d(inputs.get("qualifying_payments")), max(assessable, ZERO))
    losses = min(d(inputs.get("losses_bf")), max(assessable - qp, ZERO))
    if qp:
        lines.append(line("qualifying", "Qualifying payments", -qp, level=1, rule="individual.qualifying_payment_cap"))
    if losses:
        rules.rule("losses", "restriction")
        lines.append(line("losses", "Tax losses brought forward", -losses, level=1, rule="losses.restriction"))
    relief = rules.value("individual", "personal_relief") or ZERO
    if not rules.value("individual", "personal_relief") and residency == "resident":
        flags.append({"severity": "review", "text": "No personal relief in the year's rules."})
    relief = relief if residency == "resident" else ZERO
    before_relief = max(assessable - qp - losses, ZERO)
    lines.append(line("relief", "Personal relief", -min(relief, before_relief), level=1, rule="individual.personal_relief",
                      ref=(rules.rule("individual", "personal_relief") or {}).get("ref", "")))
    taxable_normal = max(before_relief - relief, ZERO) + d(inputs.get("_taxable_shift"))
    taxable_normal = max(taxable_normal, ZERO)
    lines.append(line("taxable", "Taxable income (normal rates)", taxable_normal, kind="total"))
    bands = rules.value("individual", "bands") or []
    if not bands:
        flags.append({"severity": "blocking", "text": "No tax bands in the year's rules: the tax can't be worked out."})
    tax, used = band_tax(taxable_normal, bands)
    lines.append(line("band_head", "Tax at the progressive rates", None, kind="head", ref=(rules.rule("individual", "bands") or {}).get("ref", "")))
    for n, b in enumerate(used, start=1):
        width = "balance" if b["width"] is None else f"{b['width']:,.0f}"
        lines.append(line(f"band_{n}", f"{b['income']:,.2f} ({width}) × {pct(b['rate'])}%", b["tax"], level=1, rule="individual.bands"))
    special_total, special_tax = ZERO, ZERO
    for s in special:
        rate = rules.value("individual", "special_rates", "foreign_service") or ZERO
        t = q(max(s["net"], ZERO) * rate)
        special_total += max(s["net"], ZERO)
        special_tax += t
        lines.append(line(f"special_{s.get('id', '')}", f"{s.get('description') or 'Qualifying foreign service income'}: {max(s['net'], ZERO):,.2f} × {pct(rate)}%",
                          t, level=1, rule="individual.special_rates.foreign_service", note=s["why"],
                          ref=(rules.rule("individual", "special_rates", "foreign_service") or {}).get("ref", "")))
    tax += special_tax
    lines.append(line("income_tax", "Income tax", tax, kind="subtotal"))
    for label, items in (("Exempt income (not taxed)", exempt), ("Income subject to final withholding tax (not taxed again)", final)):
        if items:
            lines.append(line(f"sep_{label[:6]}", label, None, kind="head"))
            for it in items:
                lines.append(line(f"sep_{it.get('id', '')}", it.get("description") or INCOME_LABELS.get(it.get("category"), ""), it["gross"], level=1,
                                  kind="memo", note=it["why"]))
    creditable, final_wht = _credits(inputs.get("payments"))
    return _finish(lines, flags, tax, taxable_normal + special_total, creditable, final_wht, rules,
                   {"loss_schedule": SC.losses(inputs.get("loss_history"), inputs.get("losses_bf"), losses, ZERO, rules.year),
                    "assessable_income": q(assessable), "special_income": q(special_total),
                    "exempt_income": q(sum((i["gross"] for i in exempt), ZERO)), "final_wht_income": q(sum((i["gross"] for i in final), ZERO))})
