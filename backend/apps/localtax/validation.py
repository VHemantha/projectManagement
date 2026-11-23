"""What the accountant (or a confirmed AI extraction) may store in an engagement, checked and normalised on the
way in (AFIT, 22 Nov 2026): every list item's fields, numbers as exact text, choices from their lists. Anything
else is refused with a plain message for the field."""
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from .services import ASSET_KINDS, EXPENSE_CLASSES, INCOME_CATEGORIES, LIABILITY_KINDS, PAYMENT_TYPES, TREATMENTS

MAX_ITEMS = 300
BASIC_TEXT = {"legal_name": 200, "client_name": 200, "tin": 30, "nic_or_reg": 40, "address": 500, "activity": 1000}
CHOICES = {"entity_type": ("individual", "company", "partnership"), "residency": ("resident", "non_resident"), "tax_type": ("CIT", "IIT", "PIT"),
           "reporting_framework": ("full", "smes", "smaller"), "expected_basis": ("total", "remaining")}


class Invalid(ValueError):
    def __init__(self, errors: dict):
        super().__init__(errors)
        self.errors = errors


def _text(v, limit: int) -> str:
    return " ".join(str(v or "").split())[:limit]


def _money(v, field: str, errors: dict, key: str) -> str:
    if v in (None, ""):
        return ""
    try:
        return str(Decimal(str(v).replace(",", "")).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError):
        errors[key] = f"{field}: give a number."
        return ""


def _rate(v, errors: dict, key: str) -> str:
    if v in (None, ""):
        return ""
    try:
        r = Decimal(str(v))
    except (InvalidOperation, ValueError):
        errors[key] = "Exchange rate: give a number."
        return ""
    return str(r)


def _id(v) -> str:
    return str(v)[:40] if v not in (None, "") else uuid.uuid4().hex[:10]


def _date(v, errors: dict, key: str) -> str:
    if v in (None, ""):
        return ""
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        errors[key] = "Give a date."
        return ""


def _items(raw, name: str, errors: dict, clean) -> list:
    if not isinstance(raw, list):
        errors[name] = "Give a list."
        return []
    if len(raw) > MAX_ITEMS:
        errors[name] = f"At most {MAX_ITEMS} lines."
        return []
    return [clean(item if isinstance(item, dict) else {}, f"{name}.{n}") for n, item in enumerate(raw)]


def _choice(v, allowed, default):
    return v if v in allowed else default


def income_item(i: dict, key: str, errors: dict) -> dict:
    f = i.get("foreign") if isinstance(i.get("foreign"), dict) else {}
    foreign = {"country": _text(f.get("country"), 80), "currency": _text(f.get("currency"), 3).upper(),
               "foreign_amount": _money(f.get("foreign_amount"), "Foreign amount", errors, f"{key}.foreign_amount"),
               "rate": _rate(f.get("rate"), errors, f"{key}.rate"), "service_used_outside": bool(f.get("service_used_outside")),
               "received_in_fx_through_bank": bool(f.get("received_in_fx_through_bank")),
               "foreign_tax_paid": _money(f.get("foreign_tax_paid"), "Foreign tax paid", errors, f"{key}.foreign_tax_paid")}
    out = {"id": _id(i.get("id")), "category": _choice(i.get("category"), INCOME_CATEGORIES, "other"), "description": _text(i.get("description"), 300),
           "amount": _money(i.get("amount"), "Amount", errors, f"{key}.amount"), "treatment": _choice(i.get("treatment"), TREATMENTS, "auto"),
           "source": _text(i.get("source"), 200),
           "expenses": [{"id": _id(e.get("id")), "description": _text(e.get("description"), 300),
                         "amount": _money(e.get("amount"), "Expense", errors, f"{key}.expenses.{n}"),
                         "classification": _choice(e.get("classification"), EXPENSE_CLASSES, "clarify")}
                        for n, e in enumerate(i.get("expenses") or []) if isinstance(e, dict)][:MAX_ITEMS]}
    if out["category"] in ("foreign_service", "foreign_other") or any(foreign[k] for k in ("country", "currency", "foreign_amount")):
        out["foreign"] = foreign
        if foreign["foreign_amount"] and foreign["rate"]:
            # The LKR equivalent is worked out, not typed: foreign amount × exchange rate.
            out["lkr_amount"] = str((Decimal(foreign["foreign_amount"]) * Decimal(foreign["rate"])).quantize(Decimal("0.01")))
            out["amount"] = out["lkr_amount"]
    return out


def update(payload: dict) -> tuple[dict, dict]:
    """(model fields, data sections) from a PATCH, or Invalid with the errors by field."""
    errors: dict = {}
    fields: dict = {}
    for f, limit in BASIC_TEXT.items():
        if f in payload:
            fields[f] = str(payload.get(f) or "").strip()[:limit] if f in ("address", "activity") else _text(payload.get(f), limit)
    for f, allowed in CHOICES.items():
        if f in payload:
            if payload[f] not in allowed:
                errors[f] = "Choose one of: " + ", ".join(allowed) + "."
            else:
                fields[f] = payload[f]
    if "year_of_assessment" in payload:
        from .engine.rules import years

        if payload["year_of_assessment"] not in years():
            errors["year_of_assessment"] = "There are no tax rules for that year yet: choose " + " or ".join(years()) + "."
        else:
            fields["year_of_assessment"] = payload["year_of_assessment"]
    if "fy_end" in payload:
        v = _date(payload.get("fy_end"), errors, "fy_end")
        fields["fy_end"] = date.fromisoformat(v) if v else None
    if "audited" in payload:
        fields["audited"] = bool(payload["audited"])
    if "expected_tax" in payload:
        v = _money(payload.get("expected_tax"), "Expected tax payment", errors, "expected_tax")
        fields["expected_tax"] = Decimal(v) if v else None

    data: dict = {}
    raw = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    if "income" in raw:
        data["income"] = _items(raw["income"], "income", errors, lambda i, k: income_item(i, k, errors))
    if "assets" in raw:
        data["assets"] = _items(raw["assets"], "assets", errors, lambda i, k: {
            "id": _id(i.get("id")), "kind": _choice(i.get("kind"), ASSET_KINDS, "other"), "description": _text(i.get("description"), 300),
            "value": _money(i.get("value"), "Value", errors, f"{k}.value"), "ownership": _text(i.get("ownership"), 120),
            "acquired": _date(i.get("acquired"), errors, f"{k}.acquired"), "notes": _text(i.get("notes"), 500), "source": _text(i.get("source"), 300)})
    if "liabilities" in raw:
        data["liabilities"] = _items(raw["liabilities"], "liabilities", errors, lambda i, k: {
            "id": _id(i.get("id")), "kind": _choice(i.get("kind"), LIABILITY_KINDS, "other"), "description": _text(i.get("description"), 300),
            "value": _money(i.get("value"), "Value", errors, f"{k}.value"), "lender": _text(i.get("lender"), 120), "notes": _text(i.get("notes"), 500),
            "source": _text(i.get("source"), 300)})
    if "payments" in raw:
        data["payments"] = _items(raw["payments"], "payments", errors, lambda i, k: {
            "id": _id(i.get("id")), "type": _choice(i.get("type"), PAYMENT_TYPES, "other"), "amount": _money(i.get("amount"), "Amount", errors, f"{k}.amount"),
            "date": _date(i.get("date"), errors, f"{k}.date"), "reference": _text(i.get("reference"), 80), "source": _text(i.get("source"), 300),
            # Final withholding is never a credit; the others may be marked not creditable.
            "creditable": False if i.get("type") == "final_wht" else (None if i.get("creditable") is None else bool(i.get("creditable")))})
    if "fixed_assets" in raw:
        # The fixed asset register (Phase 3): the capital allowance schedule is worked out from it.
        data["fixed_assets"] = _items(raw["fixed_assets"], "fixed_assets", errors, lambda i, k: {
            "id": _id(i.get("id")), "description": _text(i.get("description"), 200), "asset_class": _text(i.get("asset_class"), 40),
            "acquired": _date(i.get("acquired"), errors, f"{k}.acquired"), "cost": _money(i.get("cost"), "Cost", errors, f"{k}.cost"),
            "ca_claimed_bf": _money(i.get("ca_claimed_bf"), "Allowances claimed before", errors, f"{k}.ca_claimed_bf"),
            "allowance": _money(i.get("allowance"), "Allowance", errors, f"{k}.allowance"),
            "disposed": _date(i.get("disposed"), errors, f"{k}.disposed"), "proceeds": _money(i.get("proceeds"), "Proceeds", errors, f"{k}.proceeds"),
            "source": _text(i.get("source"), 200)})
    if "bank_balances" in raw:
        # Bank balances confirmed from statements / confirmations (companies): reconciled to the trial balance's bank accounts.
        data["bank_balances"] = _items(raw["bank_balances"], "bank_balances", errors, lambda i, k: {
            "id": _id(i.get("id")), "bank": _text(i.get("bank"), 120), "account": _text(i.get("account"), 60), "date": _date(i.get("date"), errors, f"{k}.date"),
            "balance": _money(i.get("balance"), "Balance", errors, f"{k}.balance"), "source": _text(i.get("source"), 300)})
    if "directors" in raw:
        data["directors"] = _text(raw["directors"], 500)
    if "company_secretary" in raw:
        data["company_secretary"] = _text(raw["company_secretary"], 300)
    if "shares_issued" in raw:
        # e.g. "100,000 ordinary shares": the stated capital note's wording
        data["shares_issued"] = _text(raw["shares_issued"], 120)
    if "fs_scope" in raw:
        # What the client needs: an income statement only, or the full set of financial statements.
        if raw["fs_scope"] not in ("income_statement", "full"):
            errors["fs_scope"] = "Choose the income statement only or the full set of financial statements."
        else:
            data["fs_scope"] = raw["fs_scope"]
    if "loss_history" in raw:
        data["loss_history"] = _items(raw["loss_history"], "loss_history", errors, lambda i, k: {
            "id": _id(i.get("id")), "ya": _text(i.get("ya"), 9), "amount": _money(i.get("amount"), "Loss", errors, f"{k}.amount"),
            "source": _text(i.get("source"), 200)})
    for f, label in (("qualifying_payments", "Qualifying payments"), ("losses_bf", "Tax losses brought forward")):
        if f in raw:
            data[f] = _money(raw[f], label, errors, f)
    if "expected_skipped" in raw:
        data["expected_skipped"] = bool(raw["expected_skipped"])
    if "computation" in raw:
        c = raw["computation"] if isinstance(raw["computation"], dict) else {}
        line = lambda i, k: {"id": _id(i.get("id")), "label": _text(i.get("label"), 200), "amount": _money(i.get("amount"), "Amount", errors, f"{k}.amount"),  # noqa: E731
                             "note": _text(i.get("note"), 500), "source": _text(i.get("source"), 200)}
        comp = {}
        for name in ("add_backs", "deductions"):
            if name in c:
                comp[name] = _items(c[name], f"computation.{name}", errors, line)
        if "capital_allowances" in c:
            comp["capital_allowances"] = _items(c["capital_allowances"], "computation.capital_allowances", errors, lambda i, k: {
                "id": _id(i.get("id")), "label": _text(i.get("label"), 200), "asset_class": _text(i.get("asset_class"), 40),
                "cost": _money(i.get("cost"), "Cost", errors, f"{k}.cost"), "amount": _money(i.get("amount"), "Allowance", errors, f"{k}.amount")})
        if "special_income" in c:
            comp["special_income"] = _items(c["special_income"], "computation.special_income", errors, lambda i, k: {
                "id": _id(i.get("id")), "label": _text(i.get("label"), 200), "amount": _money(i.get("amount"), "Amount", errors, f"{k}.amount"),
                "rate_key": _text(i.get("rate_key"), 60)})
        if "pbt_manual" in c:
            comp["pbt_manual"] = _money(c["pbt_manual"], "Profit before tax", errors, "computation.pbt_manual")
        data["computation"] = comp
    if "prior_year" in raw:
        # Figures read from the prior year's return / computation (Phase 2), kept for reference and comparison.
        py = raw["prior_year"] if isinstance(raw["prior_year"], dict) else {}
        data["prior_year"] = {"ya": _text(py.get("ya"), 9), "source": _text(py.get("source"), 200), "items": [
            {"label": _text(it.get("label"), 200), "amount": _money(it.get("amount"), "Amount", errors, f"prior_year.{n}")}
            for n, it in enumerate(py.get("items") or []) if isinstance(it, dict)][:100]}
    if "policy_text" in raw:
        # The accountant's wording of an accounting policy (Phase 3), by policy key; "" goes back to the standard wording.
        pt = raw["policy_text"] if isinstance(raw["policy_text"], dict) else {}
        data["policy_text"] = {str(k)[:30]: str(v or "").strip()[:4000] for k, v in list(pt.items())[:30] if str(v or "").strip()}
    if "note_text" in raw:
        # The notes only the accountant can write (events after the reporting period, contingencies, related parties).
        nt = raw["note_text"] if isinstance(raw["note_text"], dict) else {}
        data["note_text"] = {str(k)[:30]: str(v or "").strip()[:4000] for k, v in list(nt.items())[:30] if str(v or "").strip()}
    if "return_overrides" in raw:
        ro = raw["return_overrides"] if isinstance(raw["return_overrides"], dict) else {}
        data["return_overrides"] = {str(k)[:10]: (str(v)[:500] if v is not None else None) for k, v in list(ro.items())[:200]}
    if errors:
        raise Invalid(errors)
    return fields, data
