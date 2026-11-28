"""Financial statements, worked out by code (AFIT, 22 Nov 2026).

Companies: the trial balance - each account mapped to a financial statement heading, current year and
comparative - with the approved accounting adjustments, as the statement of profit or loss and the statement of
financial position, the balance checks and unusual balances. Individuals: the statement of income and expenses by
income source. The AI may suggest a heading for an account; a person confirms it; the figures are only ever this
code's.

Amounts on a trial balance line are signed debit-positive (a credit balance is negative).
"""
import re
from decimal import Decimal

ZERO = Decimal("0")

# Every heading, its statement and its place. P&L headings are shown as income (+) or expense (-).
HEADINGS = {
    # profit or loss
    "revenue": ("pl", "Revenue", "income"),
    "cost_of_sales": ("pl", "Cost of sales", "expense"),
    "other_income": ("pl", "Other income", "income"),
    "admin_expenses": ("pl", "Administrative expenses", "expense"),
    "distribution_expenses": ("pl", "Selling and distribution expenses", "expense"),
    "finance_costs": ("pl", "Finance costs", "expense"),
    "income_tax_expense": ("pl", "Income tax expense", "expense"),
    "oci": ("pl", "Other comprehensive income", "income"),
    # financial position
    "ppe": ("bs", "Property, plant and equipment", "asset"),
    "intangibles": ("bs", "Intangible assets", "asset"),
    "investments": ("bs", "Investments", "asset"),
    "other_non_current_assets": ("bs", "Other non-current assets", "asset"),  # e.g. a long-term rent deposit
    "inventories": ("bs", "Inventories", "asset"),
    "trade_receivables": ("bs", "Trade and other receivables", "asset"),
    "other_current_assets": ("bs", "Other current assets", "asset"),
    "cash": ("bs", "Cash and cash equivalents", "asset"),
    "share_capital": ("bs", "Stated capital", "equity"),
    "reserves": ("bs", "Reserves", "equity"),
    "retained_earnings": ("bs", "Retained earnings", "equity"),
    # the year's dividends: a debit to equity (shown as a deduction from equity), closed to retained earnings
    "dividends": ("bs", "Dividends", "equity"),
    "borrowings_non_current": ("bs", "Non-current borrowings", "liability"),
    "deferred_tax": ("bs", "Deferred tax", "liability"),
    "borrowings_current": ("bs", "Short-term borrowings", "liability"),
    "trade_payables": ("bs", "Trade and other payables", "liability"),
    "tax_payable": ("bs", "Income tax payable", "liability"),
    "shareholder_current_account": ("bs", "Shareholder's current account", "liability"),  # amounts due to shareholders / directors
    "other_current_liabilities": ("bs", "Other current liabilities", "liability"),
}
PL_ORDER = ["revenue", "cost_of_sales", "other_income", "admin_expenses", "distribution_expenses", "finance_costs", "income_tax_expense", "oci"]
EXPENSE_HEADINGS = {k for k, v in HEADINGS.items() if v[2] == "expense"}
INCOME_HEADINGS = {k for k, v in HEADINGS.items() if v[2] == "income"}

# A first heading from the account's name, by rule (the AI may suggest better; a person confirms).
KEYWORDS = [
    ("income_tax_expense", r"income tax expense|tax expense|deferred tax expense"),
    ("dividends", r"dividends? (paid|declared|payable to share)|interim dividend|final dividend"),
    ("cost_of_sales", r"cost of (sales|goods)|purchases|opening stock|closing stock|direct cost"),
    ("finance_costs", r"interest (expense|paid)|bank charges|finance (cost|charge)|loan interest|lease interest"),
    ("distribution_expenses", r"advertis|marketing|selling|distribution|freight out|commission paid|delivery"),
    ("other_income", r"interest income|dividend income|other income|gain on|rent income|rental income|sundry income|exchange gain"),
    ("revenue", r"\bsales\b|revenue|turnover|fees? (earned|income)|service income"),
    ("ppe", r"accumulated depreciation|acc\.? dep|provision for depreciation"),
    ("intangibles", r"accumulated amortis"),
    ("depreciation", r"depreciation|amortis"),
    ("admin_expenses", r"salar|wage|rent\b|electric|water|telephone|insurance|repair|audit|legal|professional|travel|entertain|"
                       r"printing|stationery|postage|subscription|depreciation|amortis|office|staff|epf|etf|gratuity|vehicle running|donation|general expense"),
    ("ppe", r"land|building|plant|machinery|equipment|furniture|fixture|motor vehicle|computer|accumulated depreciation|property"),
    ("intangibles", r"goodwill|software|intangible|licen[cs]e"),
    ("investments", r"investment|fixed deposit|shares in|treasury"),
    ("inventories", r"inventor|stock\b|stock in trade|work in progress"),
    ("other_non_current_assets", r"rent(al)? deposit|refundable deposit|security deposit|long[- ]term deposit"),
    ("trade_receivables", r"debtor|receivable|advance|deposit paid|prepayment|pre-payment|staff loan"),
    # an overdraft is a short-term borrowing, even when it is named "Bank overdraft" (AFIT, 28 Nov 2026)
    ("borrowings_current", r"overdraft|\bo/?d\b"),
    ("cash", r"\bcash\b|bank|petty cash|current account|savings"),
    ("share_capital", r"stated capital|share capital|capital account"),
    ("reserves", r"reserve"),
    ("retained_earnings", r"retained|accumulated (profit|loss)|profit and loss account"),
    ("shareholder_current_account", r"shareholder|director'?s? (current|loan) account|due to (a )?director|amount due to (share|direct)"),
    ("tax_payable", r"income tax payable|tax payable|provision for tax"),
    ("deferred_tax", r"deferred tax"),
    ("borrowings_current", r"overdraft|short[- ]term loan"),
    ("borrowings_non_current", r"long[- ]term loan|term loan|loan|borrowing|lease liabilit"),
    ("trade_payables", r"creditor|payable|accrued|accrual|provision"),
]


def suggest_heading(name: str, amount: Decimal | None = None) -> str:
    n = (name or "").lower()
    for heading, pattern in KEYWORDS:
        if re.search(pattern, n):
            return "admin_expenses" if heading == "depreciation" else heading
    if amount is not None:
        return "admin_expenses" if amount > 0 else "other_income"
    return ""


def d(v) -> Decimal:
    if v in (None, ""):
        return ZERO
    return Decimal(str(v)).quantize(Decimal("0.01"))


def apply_adjustments(lines: list[dict], adjustments: list[dict]) -> list[dict]:
    """The TB with the approved accounting adjustments (journals and corrections) posted: each adjustment line
    moves an account's current-year amount; an account the TB does not have is added."""
    out = [{**ln, "amount": d(ln.get("amount")), "original": d(ln.get("amount")), "adjusted": False} for ln in lines]
    by_code = {ln["code"]: ln for ln in out}
    for adj in adjustments:
        for jl in adj.get("lines") or []:
            code = str(jl.get("code", "")).strip()
            if not code:
                continue
            if code not in by_code:
                ln = {"code": code, "name": jl.get("name") or code, "amount": ZERO, "original": ZERO, "comparative": None,
                      "heading": jl.get("heading") or suggest_heading(jl.get("name") or code), "adjusted": True}
                out.append(ln)
                by_code[code] = ln
            by_code[code]["amount"] += d(jl.get("amount"))
            by_code[code]["adjusted"] = True
    return out


def statements(lines: list[dict], scope: str = "full") -> dict:
    """Profit or loss and financial position from mapped TB lines: {"pl", "bs", "pbt", "profit", "checks", "unmapped"}.
    `scope` "income_statement": the client needs the income statement only - the trial balance may hold just the
    income and expense accounts, so it is not checked to balance and the financial position is not prepared."""
    cur = {k: ZERO for k in HEADINGS}
    comp = {k: ZERO for k in HEADINGS}
    has_comp = any(ln.get("comparative") not in (None, "") for ln in lines)
    detail: dict[str, list] = {k: [] for k in HEADINGS}
    unmapped, total, total_comp = [], ZERO, ZERO
    for ln in lines:
        amount, c = d(ln.get("amount")), d(ln.get("comparative"))
        total += amount
        total_comp += c
        h = ln.get("heading") or ""
        if h not in HEADINGS:
            unmapped.append({"code": ln.get("code"), "name": ln.get("name"), "amount": amount})
            continue
        cur[h] += amount
        comp[h] += c
        detail[h].append({"code": ln.get("code"), "name": ln.get("name"), "amount": amount, "comparative": c if has_comp else None,
                          "adjusted": bool(ln.get("adjusted"))})

    def shown(h: str, v: Decimal) -> Decimal:
        # income and equity/liabilities are credit balances: shown positive
        kind = HEADINGS[h][2]
        return -v if kind in ("income", "equity", "liability") else v

    def pl(values: dict) -> dict:
        rev, cos = -values["revenue"], values["cost_of_sales"]
        gross = rev - cos
        operating = gross + (-values["other_income"]) - values["admin_expenses"] - values["distribution_expenses"]
        pbt = operating - values["finance_costs"]
        profit = pbt - values["income_tax_expense"]
        return {"revenue": rev, "cost_of_sales": cos, "gross_profit": gross, "other_income": -values["other_income"],
                "admin_expenses": values["admin_expenses"], "distribution_expenses": values["distribution_expenses"],
                "finance_costs": values["finance_costs"], "pbt": pbt, "income_tax_expense": values["income_tax_expense"],
                "profit": profit, "oci": -values["oci"], "total_comprehensive_income": profit + (-values["oci"])}

    p_cur, p_comp = pl(cur), (pl(comp) if has_comp else None)
    bs = {}
    for h, (statement, label, kind) in HEADINGS.items():
        if statement == "bs":
            bs[h] = {"label": label, "kind": kind, "amount": shown(h, cur[h]), "comparative": shown(h, comp[h]) if has_comp else None,
                     "lines": detail[h]}
    assets = sum((v["amount"] for v in bs.values() if v["kind"] == "asset"), ZERO)
    # The TB's retained earnings are the opening balance: the year's profit closes into them.
    equity = sum((v["amount"] for v in bs.values() if v["kind"] == "equity"), ZERO) + p_cur["total_comprehensive_income"]
    liabilities = sum((v["amount"] for v in bs.values() if v["kind"] == "liability"), ZERO)
    checks = [
        {"label": "Trial balance balances (debits = credits)", "passed": total == ZERO, "difference": total},
        {"label": "Assets = equity + liabilities", "passed": assets == equity + liabilities, "difference": assets - equity - liabilities},
        {"label": "Every account is mapped to a heading", "passed": not unmapped, "difference": sum((u["amount"] for u in unmapped), ZERO)},
    ]
    if scope == "income_statement":
        checks = checks[2:]
        unmapped = [u for u in unmapped if u["amount"]]
    unusual = []
    for h, v in bs.items():
        if v["kind"] == "asset" and v["amount"] < 0 and h != "ppe":
            unusual.append(f"{v['label']} has a credit balance ({v['amount']:,.2f}): check the classification.")
        if v["kind"] == "liability" and v["amount"] < 0:
            unusual.append(f"{v['label']} has a debit balance ({-v['amount']:,.2f}): check the classification.")
    if scope == "income_statement":
        unusual = []
    elif cur["cash"] < 0:
        unusual.append("Cash and cash equivalents are overdrawn: consider presenting the overdraft as a current borrowing.")
    pl_rows = []
    for h in PL_ORDER:
        if detail[h] or cur[h]:
            pl_rows.append({"heading": h, "label": HEADINGS[h][1], "kind": HEADINGS[h][2], "amount": p_cur[h if h != "oci" else "oci"],
                            "comparative": p_comp[h] if p_comp else None, "lines": detail[h]})
    return {"pl": {"rows": pl_rows, "current": p_cur, "comparative": p_comp}, "bs": bs,
            "totals": {"assets": assets, "equity": equity, "liabilities": liabilities}, "pbt": p_cur["pbt"], "profit": p_cur["profit"],
            "checks": checks, "unmapped": unmapped, "unusual": unusual, "has_comparative": has_comp, "scope": scope}


def individual_statement(income: list[dict]) -> dict:
    """Individuals: income and its related expenses by source, the net by source and the totals."""
    sources, total_income, total_exp = [], ZERO, ZERO
    for inc in income:
        amount = d(inc.get("lkr_amount") if inc.get("lkr_amount") not in (None, "") else inc.get("amount"))
        expenses = [{"description": e.get("description", ""), "amount": d(e.get("amount")), "classification": e.get("classification") or "clarify"}
                    for e in inc.get("expenses") or []]
        exp_total = sum((e["amount"] for e in expenses), ZERO)
        sources.append({"id": inc.get("id"), "category": inc.get("category", "other"), "description": inc.get("description", ""), "income": amount,
                        "expenses": expenses, "expenses_total": exp_total, "net": amount - exp_total})
        total_income += amount
        total_exp += exp_total
    return {"sources": sources, "total_income": total_income, "total_expenses": total_exp, "net": total_income - total_exp}
