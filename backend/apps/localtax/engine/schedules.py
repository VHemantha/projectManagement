"""Tax schedules, worked out by code (AFIT, Phase 3).

Capital allowances from the fixed asset register: for each asset, the year's allowance at its class's rate in the
year's rules (straight line on cost, never more than the unclaimed cost), and on a disposal the balancing charge or
allowance (proceeds against the tax written-down value). An asset whose class has no rate needs its allowance
entered, and is flagged.

Tax losses: the losses brought forward by year of origin, used oldest first against this year's income, and the
balance carried forward with any loss of this year.

Each schedule rests on rules from the year's file (with their references and validation state).
"""
from decimal import ROUND_HALF_UP, Decimal

from .fs import d
from .rules import Rules

ZERO = Decimal("0")


def q(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def capital_allowances(register: list[dict], rules: Rules, period_end: str = "") -> dict:
    rows, flags = [], []
    totals = {k: ZERO for k in ("cost", "claimed_bf", "allowance", "balancing_charge", "balancing_allowance", "wdv_cf")}
    for a in register or []:
        cost, claimed = d(a.get("cost")), d(a.get("ca_claimed_bf"))
        wdv_bf = max(cost - claimed, ZERO)
        cls = a.get("asset_class") or ""
        node = rules.rule("capital_allowances", cls) if cls else None
        rate = rules.value("capital_allowances", cls) if cls else None
        row = {"id": a.get("id"), "description": a.get("description") or cls, "asset_class": cls, "label": (node or {}).get("label", cls),
               "acquired": a.get("acquired") or "", "cost": cost, "claimed_bf": claimed, "wdv_bf": wdv_bf, "rate": rate, "ref": (node or {}).get("ref", ""),
               "allowance": ZERO, "balancing_charge": ZERO, "balancing_allowance": ZERO, "disposed": a.get("disposed") or "", "proceeds": d(a.get("proceeds"))}
        if a.get("disposed"):
            rules.rule("capital_allowances", "balancing")
            diff = row["proceeds"] - wdv_bf
            row["balancing_charge"], row["balancing_allowance"] = (q(diff), ZERO) if diff > 0 else (ZERO, q(-diff))
            row["wdv_cf"] = ZERO
        else:
            if a.get("allowance") not in (None, ""):
                row["allowance"] = min(d(a.get("allowance")), wdv_bf)
                row["manual"] = True
            elif rate is None:
                flags.append({"severity": "review", "text": f"No capital allowance rate for “{row['description']}” ({cls or 'no class'}): enter its allowance."})
            else:
                row["allowance"] = min(q(cost * rate), wdv_bf)
            row["wdv_cf"] = wdv_bf - row["allowance"]
        row["claimed_cf"] = claimed + row["allowance"]
        for k in totals:
            totals[k] += row[k] if k != "claimed_bf" else claimed
        rows.append(row)
    return {"rows": rows, "totals": totals, "flags": flags}


def losses(history: list[dict], losses_bf, utilised, loss_for_year, year: str) -> dict:
    """{"rows": [{ya, bf, utilised, cf}], "totals"}: oldest loss used first. Without a history, one line for the
    total brought forward."""
    items = [{"ya": h.get("ya") or "", "amount": d(h.get("amount"))} for h in history or [] if d(h.get("amount"))]
    if not items and d(losses_bf):
        items = [{"ya": "Brought forward", "amount": d(losses_bf)}]
    items.sort(key=lambda i: i["ya"])
    left, rows = d(utilised), []
    for i in items:
        use = min(i["amount"], left)
        left -= use
        rows.append({"ya": i["ya"], "bf": i["amount"], "utilised": use, "cf": i["amount"] - use})
    if d(loss_for_year):
        rows.append({"ya": year, "bf": ZERO, "utilised": ZERO, "cf": d(loss_for_year), "current": True})
    totals = {k: sum((r[k] for r in rows), ZERO) for k in ("bf", "utilised", "cf")}
    return {"rows": rows, "totals": totals}
