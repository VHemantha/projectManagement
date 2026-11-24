"""Depreciation and the property, plant and equipment note, worked out by code (AFIT, 24 Nov 2026).

The steps, as AFIT set them out:
1. The opening balances. For each asset category: the opening cost and accumulated depreciation, from the trial
   balance's prior-year column or the prior-year financial statements. The accountant may edit them.
2. The client's depreciation policy. For each category: its method (straight-line or reducing balance), annual rate
   and residual value. It is kept with the client, so later years use it too.
3. The year's additions and disposals, each with its dates. AI may read them from invoices or a fixed asset register;
   a person confirms each.
4. The depreciation, month by month:
   - an asset is depreciated for the whole month it becomes available for use, and for every month after;
   - it is not depreciated in the month it is disposed of, or after;
   - no asset is depreciated below its residual value, so a fully depreciated asset is charged nothing.
5. On approval, one journal (JE-DEP) brings the trial balance to the schedule. Each category's accumulated
   depreciation is set to the schedule's closing balance, and so is the cost (disposals not yet recorded are taken
   out). The depreciation expense is set to the year's charge. What is left is the gain or loss on disposal.
   Approving again replaces the journal, so depreciation is never posted twice.
6. The PPE note, from the same schedule. Its closing balances are checked against the trial balance after the
   journal.

Amounts on trial balance lines are signed debit-positive. The schedule's own amounts are positive (cost, and
accumulated depreciation as a positive balance).
"""
import hashlib
import json
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0")
CENT = Decimal("0.01")
METHODS = {"straight_line": "Straight-line", "reducing_balance": "Reducing balance"}

# The categories TASKO knows, with illustrative rates (the client's policy replaces them) and how to recognise each
# from an account's or an asset's name. Order matters: the first pattern that matches wins.
DEFAULT_CATEGORIES = [
    {"key": "land", "label": "Land", "method": "straight_line", "rate": "0", "residual": "0", "pattern": r"\bland\b"},
    {"key": "buildings", "label": "Buildings", "method": "straight_line", "rate": "0.05", "residual": "0",
     "pattern": r"building|premises|property|warehouse|factory|office space"},
    {"key": "motor_vehicles", "label": "Motor vehicles", "method": "straight_line", "rate": "0.20", "residual": "0",
     "pattern": r"motor|vehicle|\bcars?\b|\bvans?\b|lorr|truck|bike|three.?wheel|\bjeep|\bbus\b"},
    {"key": "furniture_fittings", "label": "Furniture and fittings", "method": "straight_line", "rate": "0.10", "residual": "0",
     "pattern": r"furniture|fitting|fixture|chair|desk|table|cupboard|partition"},
    {"key": "computer_equipment", "label": "Computer equipment", "method": "straight_line", "rate": "0.25", "residual": "0",
     "pattern": r"computer|laptop|notebook|desktop|server|printer|\bit equipment|monitor|tablet|ipad|router|\bups\b"},
    {"key": "plant_machinery", "label": "Plant and machinery", "method": "straight_line", "rate": "0.10", "residual": "0",
     "pattern": r"plant|machiner|machine|generator|tools?\b|equipment - factory"},
    {"key": "office_equipment", "label": "Office equipment", "method": "straight_line", "rate": "0.20", "residual": "0",
     "pattern": r"equipment|air.?condition|\ba/?c\b|photocop|telephone|phone|camera|projector|fan\b"},
]
ACCUMULATED = re.compile(r"accum|acc\.?\s*dep|provision for dep|depreciation", re.I)
DEPRECIATION_EXPENSE = re.compile(r"depreciation", re.I)
EXPENSE_CODE, DISPOSAL_CODE = "DEP-EXP", "PPE-DISP"


def d(v) -> Decimal:
    if v in (None, ""):
        return ZERO
    try:
        return Decimal(str(v).replace(",", ""))
    except Exception:  # noqa: BLE001 - an unreadable figure counts as nothing (validation reports it)
        return ZERO


def q(v: Decimal) -> Decimal:
    return v.quantize(CENT, rounding=ROUND_HALF_UP)


# --- 1. the policy and the categories ------------------------------------------------------------------------------

def default_policy() -> list[dict]:
    return [{k: c[k] for k in ("key", "label", "method", "rate", "residual")} for c in DEFAULT_CATEGORIES]


def category_of(name: str, policy: list[dict]) -> str:
    """The category an account or asset belongs to, from its name: the client's own categories first (by their
    label), then TASKO's patterns; "" when nothing matches."""
    n = (name or "").lower()
    keys = {c["key"] for c in policy}
    for c in policy:
        words = [w for w in re.findall(r"[a-z]{4,}", c["label"].lower()) if w not in ("and", "with", "other")]
        if words and all(w[:6] in n for w in words[:2]):
            return c["key"]
    for c in DEFAULT_CATEGORIES:
        if c["key"] in keys and re.search(c["pattern"], n):
            return c["key"]
    return ""


def classify(tb: list[dict], policy: list[dict], overrides: dict) -> list[dict]:
    """Each PPE account of the trial balance: its category and whether it holds cost or accumulated depreciation.
    A person's (or the AI's, once accepted) choice in `overrides` wins over the rule."""
    out = []
    for ln in tb:
        if ln.get("heading") != "ppe":
            continue
        o = overrides.get(str(ln["code"])) or {}
        role = o.get("role") or ("accumulated" if ACCUMULATED.search(ln.get("name") or "") else "cost")
        cat = o.get("category") if o.get("category") is not None else category_of(re.sub(ACCUMULATED, " ", ln.get("name") or ""), policy)
        out.append({"code": str(ln["code"]), "name": ln.get("name") or "", "category": cat, "role": role, "by": o.get("by") or "rule",
                    "amount": d(ln.get("amount")), "comparative": d(ln.get("comparative")) if ln.get("comparative") is not None else None})
    return out


# --- 2. the opening balances ---------------------------------------------------------------------------------------

def openings(accounts: list[dict], policy: list[dict], overrides: dict, has_comparative: bool) -> dict:
    """For each category: the opening cost and accumulated depreciation (positive). They come from the trial balance's
    prior-year column, unless the accountant (or the prior-year statements) gave them."""
    out = {}
    for c in policy:
        k = c["key"]
        cost = sum((a["comparative"] or ZERO for a in accounts if a["category"] == k and a["role"] == "cost"), ZERO)
        acc = -sum((a["comparative"] or ZERO for a in accounts if a["category"] == k and a["role"] == "accumulated"), ZERO)
        o = overrides.get(k) or {}
        source = "Trial balance, prior-year column" if has_comparative else ""
        if o.get("cost") not in (None, "") or o.get("accumulated") not in (None, ""):
            cost = d(o.get("cost")) if o.get("cost") not in (None, "") else cost
            acc = d(o.get("accumulated")) if o.get("accumulated") not in (None, "") else acc
            source = o.get("source") or "Entered by the accountant"
        out[k] = {"cost": q(cost), "accumulated": q(acc), "source": source}
    return out


# --- 4. the schedule ------------------------------------------------------------------------------------------------

def year_start(fy_end: date) -> date:
    try:
        return fy_end.replace(year=fy_end.year - 1) + timedelta(days=1)
    except ValueError:  # 29 February
        return fy_end - timedelta(days=365)


def month_index(start: date, when: date) -> int:
    """0 for the year's first month ... 11 for its last; below 0 before the year, 12 or more after it."""
    return (when.year - start.year) * 12 + when.month - start.month


def months(start: date) -> list[str]:
    out, y, m = [], start.year, start.month
    for _ in range(12):
        out.append(f"{y}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def _monthly(cost: Decimal, accumulated: Decimal, residual: Decimal, rate: Decimal, method: str, active: list[bool]) -> tuple[list[Decimal], bool]:
    """The charge for each of the 12 months an asset (or the opening pool) is active, never taking it below its
    residual value. Straight-line: cost x rate / 12 a month. Reducing balance: the net book value at the start of
    the year (or the cost, for an addition) x rate / 12 a month."""
    room = max(cost - residual - accumulated, ZERO)
    fully = room <= 0 and cost > 0
    base = cost if method == "straight_line" else max(cost - accumulated, ZERO)
    per_month = base * rate / 12
    out = []
    for on in active:
        charge = min(per_month, room) if on else ZERO
        charge = q(charge)
        room -= charge
        out.append(charge)
    return out, fully


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def schedule(policy: list[dict], opening: dict, additions: list[dict], disposals: list[dict], fy_end: date | None) -> dict:
    """The year's depreciation schedule: by category, the cost and accumulated depreciation from the opening balance
    to the closing one, the charge month by month, and each addition and disposal with its own charge."""
    if fy_end is None:
        return {"available": False, "reason": "Enter the financial year end in Client Info: the months depend on it.", "categories": [], "flags": []}
    start = year_start(fy_end)
    flags, cats = [], []
    known = {c["key"] for c in policy}
    for a in additions:
        if a.get("category") not in known:
            flags.append({"severity": "blocking", "text": f"Addition “{a.get('description') or 'asset'}”: choose its category."})
    for x in disposals:
        if x.get("category") not in known:
            flags.append({"severity": "blocking", "text": f"Disposal “{x.get('description') or 'asset'}”: choose its category."})
    totals = {k: ZERO for k in ("cost_open", "additions", "disposals_cost", "cost_close", "acc_open", "charge", "acc_disposals", "acc_close", "proceeds",
                                "gain")}
    monthly_total = [ZERO] * 12
    for c in policy:
        k, rate, residual_pct, method = c["key"], d(c.get("rate")), d(c.get("residual")), c.get("method") or "straight_line"
        op = opening.get(k) or {"cost": ZERO, "accumulated": ZERO, "source": ""}
        cat_adds = [a for a in additions if a.get("category") == k]
        cat_disp = [x for x in disposals if x.get("category") == k]
        if not (op["cost"] or op["accumulated"] or cat_adds or cat_disp):
            continue
        monthly = [ZERO] * 12
        # the opening assets, less those disposed of (each disposal is depreciated on its own until it goes)
        pool_cost = op["cost"] - sum((d(x.get("cost")) for x in cat_disp), ZERO)
        pool_acc = op["accumulated"] - sum((d(x.get("accumulated_bf")) for x in cat_disp), ZERO)
        if pool_cost < 0:
            flags.append({"severity": "blocking", "text": f"{c['label']}: the disposals' cost is more than the opening cost - check the opening "
                                                          "balance and the disposals."})
            pool_cost, pool_acc = ZERO, ZERO
        pool, fully = _monthly(pool_cost, pool_acc, q(pool_cost * residual_pct), rate, method, [True] * 12)
        monthly = [m + p for m, p in zip(monthly, pool)]
        add_rows = []
        for a in cat_adds:
            cost = d(a.get("cost"))
            avail = _date(a.get("available_date")) or _date(a.get("purchase_date"))
            if avail is None:
                flags.append({"severity": "blocking", "text": f"Addition “{a.get('description') or 'asset'}”: enter the date it became available for use."})
                first = 12
            else:
                first = month_index(start, avail)
                if first < 0:
                    flags.append({"severity": "review", "text": f"Addition “{a.get('description') or 'asset'}” was available for use before the year "
                                                                "began: is it an opening asset?"})
                    first = 0
                if first > 11:
                    flags.append({"severity": "review", "text": f"Addition “{a.get('description') or 'asset'}” is available for use after the year end: "
                                                                "it is not depreciated this year."})
            charges, _ = _monthly(cost, ZERO, q(cost * residual_pct), rate, method, [i >= first for i in range(12)])
            monthly = [m + ch for m, ch in zip(monthly, charges)]
            add_rows.append({**a, "cost": q(cost), "months": sum(1 for ch in charges if ch), "charge": q(sum(charges, ZERO))})
        disp_rows = []
        for x in cat_disp:
            cost, acc_bf, proceeds = d(x.get("cost")), d(x.get("accumulated_bf")), d(x.get("proceeds"))
            when = _date(x.get("date"))
            if when is None:
                flags.append({"severity": "blocking", "text": f"Disposal “{x.get('description') or 'asset'}”: enter the date it was disposed of."})
                last = 0
            else:
                last = min(max(month_index(start, when), 0), 12)  # depreciated in the months before the disposal
            charges, _ = _monthly(cost, acc_bf, q(cost * residual_pct), rate, method, [i < last for i in range(12)])
            monthly = [m + ch for m, ch in zip(monthly, charges)]
            charge = q(sum(charges, ZERO))
            acc_out = acc_bf + charge
            nbv = cost - acc_out
            disp_rows.append({**x, "cost": q(cost), "accumulated_bf": q(acc_bf), "proceeds": q(proceeds), "months": sum(1 for ch in charges if ch),
                              "charge": charge, "accumulated_on_disposal": q(acc_out), "nbv": q(nbv), "gain": q(proceeds - nbv)})
        charge = q(sum(monthly, ZERO))
        additions_cost = q(sum((r["cost"] for r in add_rows), ZERO))
        disposals_cost = q(sum((r["cost"] for r in disp_rows), ZERO))
        acc_disposals = q(sum((r["accumulated_on_disposal"] for r in disp_rows), ZERO))
        cost_close = op["cost"] + additions_cost - disposals_cost
        acc_close = op["accumulated"] + charge - acc_disposals
        row = {"key": k, "label": c["label"], "method": method, "rate": str(rate), "residual": str(residual_pct),
               "cost": {"opening": op["cost"], "additions": additions_cost, "disposals": disposals_cost, "closing": q(cost_close)},
               "accumulated": {"opening": op["accumulated"], "charge": charge, "disposals": acc_disposals, "closing": q(acc_close)},
               "nbv": {"opening": q(op["cost"] - op["accumulated"]), "closing": q(cost_close - acc_close)},
               "monthly": monthly, "fully_depreciated": fully and not cat_adds, "opening_source": op.get("source", ""),
               "additions": add_rows, "disposals": disp_rows}
        if fully and pool_cost > 0:
            flags.append({"severity": "info", "text": f"{c['label']}: the opening assets are fully depreciated - no charge on them this year."})
        if acc_close > cost_close + 1:
            flags.append({"severity": "blocking", "text": f"{c['label']}: the accumulated depreciation is more than the cost - check the opening balances."})
        cats.append(row)
        for key, v in (("cost_open", op["cost"]), ("additions", additions_cost), ("disposals_cost", disposals_cost), ("cost_close", cost_close),
                       ("acc_open", op["accumulated"]), ("charge", charge), ("acc_disposals", acc_disposals), ("acc_close", acc_close),
                       ("proceeds", sum((r["proceeds"] for r in disp_rows), ZERO)), ("gain", sum((r["gain"] for r in disp_rows), ZERO))):
            totals[key] += v
        monthly_total = [a + b for a, b in zip(monthly_total, monthly)]
    return {"available": True, "start": start.isoformat(), "end": fy_end.isoformat(), "months": months(start), "categories": cats,
            "monthly": monthly_total, "totals": {k: q(v) for k, v in totals.items()}, "flags": flags,
            "convention": "A full month's depreciation in the month an asset becomes available for use; none in the month it is disposed of."}


# --- 5. the journal -------------------------------------------------------------------------------------------------

def journal(sched: dict, accounts: list[dict], tb: list[dict], policy: list[dict], proceeds_code: str = "") -> dict:
    """The journal that brings the trial balance (before this journal) to the schedule: {"lines", "explain", "residual"}.
    Each line {code, name, amount (debit +), heading}."""
    labels = {c["key"]: c["label"] for c in policy}
    by_code = {str(ln["code"]): ln for ln in tb}
    lines, explain = [], []

    def add(code, name, amount, heading):
        amount = q(amount)
        if amount:
            lines.append({"code": code, "name": name, "amount": str(amount), "heading": heading})

    for cat in sched.get("categories") or []:
        k = cat["key"]
        for role, target in (("cost", cat["cost"]["closing"]), ("accumulated", -cat["accumulated"]["closing"])):
            accs = [a for a in accounts if a["category"] == k and a["role"] == role]
            now = sum((d(by_code.get(a["code"], {}).get("amount")) for a in accs), ZERO)
            delta = target - now
            if not delta:
                continue
            if accs:
                code, name = accs[0]["code"], accs[0]["name"]
            else:
                code = f"PPE-{k.upper()[:10]}-{'ACC' if role == 'accumulated' else 'COST'}"
                name = f"{labels.get(k, k)} - {'accumulated depreciation' if role == 'accumulated' else 'cost'}"
            add(code, name, delta, "ppe")
    exp = [ln for ln in tb if ln.get("heading") in ("admin_expenses", "cost_of_sales", "distribution_expenses") and DEPRECIATION_EXPENSE.search(ln.get("name") or "")]
    already = sum((d(ln.get("amount")) for ln in exp), ZERO)
    charge = sched["totals"]["charge"] if sched.get("totals") else ZERO
    if exp:
        add(str(exp[0]["code"]), exp[0]["name"], charge - already, exp[0].get("heading") or "admin_expenses")
    else:
        add(EXPENSE_CODE, "Depreciation", charge, "admin_expenses")
    if already:
        explain.append(f"The trial balance already has depreciation expense of {already:,.2f}: only the difference to the year's charge "
                       f"({charge:,.2f}) is posted.")
    proceeds = sched["totals"]["proceeds"] if sched.get("totals") else ZERO
    if proceeds_code and proceeds:
        p = by_code.get(proceeds_code)
        add(proceeds_code, p["name"] if p else "Disposal proceeds", proceeds, p.get("heading") if p else "other_income")
        explain.append(f"The disposal proceeds ({proceeds:,.2f}) are moved out of {proceeds_code} into the gain or loss on disposal.")
    residual = -sum((d(ln["amount"]) for ln in lines), ZERO)
    if residual:
        add(DISPOSAL_CODE, "Gain / (loss) on disposal of property, plant and equipment", residual, "other_income" if residual < 0 else "admin_expenses")
        expected = -(sched["totals"]["gain"] if sched.get("totals") else ZERO)
        if sched.get("categories") and not any(c["disposals"] for c in sched["categories"]):
            explain.append(f"With no disposals, {abs(residual):,.2f} is left to balance the journal: the trial balance's own depreciation and "
                           "accumulated depreciation, or its cost and the additions, do not agree. Check them before approving.")
        elif proceeds_code and abs(residual - expected) >= 1:
            explain.append(f"The gain or loss on disposal works out at {-residual:,.2f}, not {-expected:,.2f} from the disposals: check the trial "
                           "balance's PPE accounts and the proceeds account.")
    return {"lines": lines, "explain": explain, "residual": q(residual), "charge": charge}


def fingerprint(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, default=str, sort_keys=True).encode()).hexdigest()[:16]


# --- 6. the reconciliation -------------------------------------------------------------------------------------------

def reconcile(sched: dict, accounts: list[dict], adjusted_tb: list[dict]) -> list[dict]:
    """Each category's closing cost and accumulated depreciation against the trial balance after the journals."""
    by_code = {str(ln["code"]): d(ln.get("amount")) for ln in adjusted_tb}
    codes = {a["code"]: a for a in accounts}
    out = []
    for cat in sched.get("categories") or []:
        k = cat["key"]
        tb_cost = sum((v for c, v in by_code.items() if (codes.get(c) or {}).get("category") == k and codes[c]["role"] == "cost"
                       or c == f"PPE-{k.upper()[:10]}-COST"), ZERO)
        tb_acc = -sum((v for c, v in by_code.items() if (codes.get(c) or {}).get("category") == k and codes[c]["role"] == "accumulated"
                       or c == f"PPE-{k.upper()[:10]}-ACC"), ZERO)
        out.append({"key": k, "label": cat["label"], "schedule_cost": cat["cost"]["closing"], "tb_cost": q(tb_cost),
                    "schedule_accumulated": cat["accumulated"]["closing"], "tb_accumulated": q(tb_acc),
                    "agrees": abs(tb_cost - cat["cost"]["closing"]) < 1 and abs(tb_acc - cat["accumulated"]["closing"]) < 1})
    return out
