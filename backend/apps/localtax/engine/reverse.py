"""Reverse tax calculation (AFIT, 22 Nov 2026): when the client gave an expected tax payment, compare it with the
tax calculated from the evidence and work out what would have to be different to reach it.

Everything here re-runs the complete computation (tax.compute) - progressive bands, special rates, deductions,
credits - and solves for the figure by bisection; it never divides the expected tax by one assumed rate. Where
several accounts could explain the difference, each is a separate scenario: the answer is not made to look
unique. A scenario is hypothetical: nothing here changes a figure; only an approved, evidenced adjustment does.
"""
import copy
from decimal import Decimal

from .fs import d
from .rules import Rules
from .tax import compute, q

ZERO = Decimal("0")
TOLERANCE = Decimal("0.5")


def basis_value(result: dict, basis: str) -> Decimal:
    """The figure the client's expectation is about: the total liability (income tax) or what remains payable."""
    return result["income_tax"] if basis == "total" else result["payable"]


def _solve(f, target: Decimal, lo: Decimal, hi: Decimal, increasing: bool) -> Decimal | None:
    """x in [lo, hi] with f(x) == target (f monotonic), or None when the target is outside f's range."""
    flo, fhi = f(lo), f(hi)
    low_v, high_v = (flo, fhi) if increasing else (fhi, flo)
    if not (low_v - TOLERANCE <= target <= high_v + TOLERANCE):
        return None
    for _ in range(200):  # to well under a cent of the figure, whatever the tax rate's slope
        if hi - lo <= Decimal("0.001"):
            break
        mid = (lo + hi) / 2
        if (f(mid) < target) == increasing:
            lo = mid
        else:
            hi = mid
    return q((lo + hi) / 2)


def required_taxable_income(inputs: dict, rules: Rules, expected: Decimal, basis: str) -> Decimal | None:
    """The taxable income at which the complete computation gives the expected tax (others held as they are)."""
    base = compute(inputs, rules.fresh())

    def f(taxable: Decimal) -> Decimal:
        trial = {**inputs, "_taxable_shift": taxable - base["taxable_income"] + d(inputs.get("_taxable_shift"))}
        return basis_value(compute(trial, rules.fresh()), basis)

    hi = max(base["taxable_income"] * 4, Decimal("10000000"))
    while f(hi) < expected and hi < Decimal("1e13"):
        hi *= 4
    return _solve(f, expected, ZERO, hi, increasing=True)


def levers(inputs: dict, accounts: list[dict] | None = None) -> list[dict]:
    """The figures that could explain a difference: each with where it sits in the inputs and its direction.
    Companies: the P&L accounts (via profit before tax), add backs, deductions, capital allowances, qualifying
    payments, losses and credits. Individuals: each income and expense line, qualifying payments, losses and
    credits. `accounts`: the mapped P&L accounts, for companies."""
    out = []
    if inputs.get("entity_type") == "individual":
        for i, inc in enumerate(inputs.get("income") or []):
            field = "lkr_amount" if inc.get("lkr_amount") not in (None, "") else "amount"
            out.append({"key": f"income:{inc.get('id', i)}", "label": inc.get("description") or inc.get("category", "Income"), "group": "Income",
                        "path": ["income", i, field], "amount": d(inc.get(field)), "scope": "accounting"})
            for j, e in enumerate(inc.get("expenses") or []):
                out.append({"key": f"expense:{inc.get('id', i)}:{e.get('id', j)}", "label": e.get("description") or "Expense", "group": "Expenses",
                            "path": ["income", i, "expenses", j, "amount"], "amount": d(e.get("amount")), "scope": "accounting"})
    else:
        for acc in accounts or []:
            out.append({"key": f"account:{acc['code']}", "label": f"{acc['code']} {acc['name']}", "group": acc.get("group", "Accounts"),
                        "path": ["pbt"], "sign": 1 if acc.get("kind") == "income" else -1, "amount": d(acc.get("amount")),
                        "scope": "accounting", "code": acc["code"]})
        for name, group in (("add_backs", "Add backs"), ("deductions", "Deductions"), ("capital_allowances", "Capital allowances")):
            for i, a in enumerate(inputs.get(name) or []):
                if name == "capital_allowances" and a.get("amount") in (None, ""):
                    continue  # a computed allowance changes with its cost, not here
                out.append({"key": f"{name}:{a.get('id', i)}", "label": a.get("label", group), "group": group,
                            "path": [name, i, "amount"], "amount": d(a.get("amount")), "scope": "tax"})
    for name, label in (("qualifying_payments", "Qualifying payments"), ("losses_bf", "Tax losses brought forward")):
        out.append({"key": name, "label": label, "group": "Reliefs", "path": [name], "amount": d(inputs.get(name)), "scope": "tax"})
    for i, p in enumerate(inputs.get("payments") or []):
        out.append({"key": f"payment:{p.get('id', i)}", "label": f"{p.get('type', 'Credit')} {p.get('reference', '')}".strip(), "group": "Tax credits",
                    "path": ["payments", i, "amount"], "amount": d(p.get("amount")), "scope": "tax"})
    return out


def _set(inputs: dict, lever: dict, new_amount: Decimal) -> dict:
    data = copy.deepcopy(inputs)
    if lever["path"] == ["pbt"]:  # a P&L account: profit before tax moves with it (income +, expense -)
        data["pbt"] = d(data.get("pbt")) + lever["sign"] * (new_amount - lever["amount"])
        return data
    node = data
    for p in lever["path"][:-1]:
        node = node[p]
    node[lever["path"][-1]] = str(new_amount)
    return data


def with_change(inputs: dict, lever: dict, new_amount: Decimal) -> dict:
    return _set(inputs, lever, new_amount)


def scenarios(inputs: dict, rules: Rules, expected: Decimal, basis: str, accounts: list[dict] | None = None) -> list[dict]:
    """For each lever on its own: the amount that would give the expected tax, or why it can't."""
    out = []
    for lever in levers(inputs, accounts):
        def f(x: Decimal, lever=lever) -> Decimal:
            return basis_value(compute(_set(inputs, lever, x), rules.fresh()), basis)

        current = lever["amount"]
        hi = max(abs(current) * 10, Decimal("100000000"))
        lo = ZERO
        increasing = f(hi) >= f(lo)
        if f(hi) == f(lo):
            out.append({**_public(lever), "feasible": False, "reason": "Changing this line alone does not change the tax."})
            continue
        x = _solve(f, expected, lo, hi, increasing)
        if x is None:
            out.append({**_public(lever), "feasible": False, "reason": "No amount for this line alone gives the expected tax."})
            continue
        out.append({**_public(lever), "feasible": True, "proposed": x, "change": q(x - current)})
    out.sort(key=lambda s: (not s["feasible"], abs(s.get("change") or 0)))
    return out


def _public(lever: dict) -> dict:
    return {k: lever[k] for k in ("key", "label", "group", "amount", "scope")}


def analyse(inputs: dict, rules: Rules, expected, basis: str = "total", accounts: list[dict] | None = None) -> dict | None:
    """The reverse tax analysis, or None without an expected tax."""
    if expected in (None, ""):
        return None
    expected = d(expected)
    result = compute(inputs, rules.fresh())
    calculated = basis_value(result, basis)
    required = required_taxable_income(inputs, rules, expected, basis)
    out = {"expected": expected, "basis": basis, "calculated": calculated, "variance": q(calculated - expected),
           "taxable_income": result["taxable_income"], "required_taxable_income": required,
           "taxable_income_difference": q(result["taxable_income"] - required) if required is not None else None,
           "scenarios": scenarios(inputs, rules, expected, basis, accounts) if abs(calculated - expected) > TOLERANCE else []}
    if required is None:
        out["unsupported"] = ("No taxable income gives the expected tax with the credits recorded: the expected payment can't be reached "
                              "from the information available.")
    return out


def effect(inputs: dict, rules: Rules, lever_key: str, proposed, expected=None, basis: str = "total", accounts: list[dict] | None = None) -> dict:
    """What one proposed change does: original and proposed amount, revised profit, taxable income, tax and the
    remaining variance. Hypothetical until approved."""
    lever = next((lv for lv in levers(inputs, accounts) if lv["key"] == lever_key), None)
    if lever is None:
        raise KeyError(lever_key)
    before = compute(inputs, rules.fresh())
    after_inputs = _set(inputs, lever, d(proposed))
    after = compute(after_inputs, rules.fresh())
    out = {"lever": _public(lever), "original": lever["amount"], "proposed": d(proposed), "difference": q(d(proposed) - lever["amount"]),
           "profit_before": d(inputs.get("pbt")) if inputs.get("entity_type") != "individual" else None,
           "profit_after": d(after_inputs.get("pbt")) if inputs.get("entity_type") != "individual" else None,
           "taxable_before": before["taxable_income"], "taxable_after": after["taxable_income"], "tax_before": basis_value(before, basis),
           "tax_after": basis_value(after, basis), "hypothetical": True}
    if expected not in (None, ""):
        out["remaining_variance"] = q(basis_value(after, basis) - d(expected))
    return out
