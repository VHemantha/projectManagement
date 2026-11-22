"""The rest of a full set of financial statements, worked out by code from the mapped trial balance (AFIT, Phase 3):
the statement of changes in equity, the statement of cash flows (indirect method), the notes and the accounting
policies, and the draft auditor's report template.

Every amount comes from `fs.statements()`; nothing is typed in or produced by the AI. Where the trial balance
cannot show something directly (a purchase of equipment net of disposals, tax paid), the line says how it was
derived, and the cash flow is reconciled to the movement in cash, with any difference shown for the accountant.
The policies are standard wording for the framework chosen, to be tailored; the auditor's report is a labelled
template only - TASKO never issues an opinion.
"""
import re
from decimal import Decimal

from .fs import HEADINGS, PL_ORDER

ZERO = Decimal("0")
FRAMEWORK = {"full": "Sri Lanka Accounting Standards (SLFRS and LKAS) issued by CA Sri Lanka",
             "smes": "the Sri Lanka Accounting Standard for Small and Medium-sized Entities (SLFRS for SMEs) issued by CA Sri Lanka",
             "smaller": "the Sri Lanka Accounting Standard for Smaller Entities (SLASSE) issued by CA Sri Lanka"}
DEP = re.compile(r"depreciation", re.I)
AMORT = re.compile(r"amortis|amortiz", re.I)


def _bs(fin: dict, h: str, which: str = "amount") -> Decimal:
    v = (fin.get("bs") or {}).get(h) or {}
    return v.get(which) or ZERO


def _pl_lines(fin: dict) -> list[dict]:
    return [ln for row in (fin.get("pl") or {}).get("rows") or [] for ln in row.get("lines") or []
            if HEADINGS.get(row["heading"], ("", "", ""))[2] == "expense"]


def depreciation(fin: dict) -> tuple[Decimal, Decimal]:
    """(depreciation, amortisation) charged in profit or loss: the expense accounts named so."""
    dep = sum((ln["amount"] for ln in _pl_lines(fin) if DEP.search(ln.get("name") or "")), ZERO)
    amort = sum((ln["amount"] for ln in _pl_lines(fin) if AMORT.search(ln.get("name") or "")), ZERO)
    return dep, amort


def equity_changes(fin: dict) -> dict:
    """Stated capital, reserves and retained earnings from the start of the year to its end. The trial balance's
    retained earnings are the opening balance (the year's profit has not been closed into them)."""
    cur = fin["pl"]["current"]
    has_comp = fin.get("has_comparative")
    sc_open = _bs(fin, "share_capital", "comparative") if has_comp else _bs(fin, "share_capital")
    res_open = _bs(fin, "reserves", "comparative") if has_comp else _bs(fin, "reserves")
    re_open = _bs(fin, "retained_earnings")
    dividends = _bs(fin, "dividends")  # shown negative: a deduction from equity
    rows = [
        {"label": "Balance at the start of the year", "share_capital": sc_open, "reserves": res_open, "retained_earnings": re_open, "kind": "subtotal"},
        {"label": "Profit for the year", "share_capital": ZERO, "reserves": ZERO, "retained_earnings": cur["profit"]},
        {"label": "Other comprehensive income", "share_capital": ZERO, "reserves": cur["oci"], "retained_earnings": ZERO},
        {"label": "Issue of shares", "share_capital": _bs(fin, "share_capital") - sc_open, "reserves": ZERO, "retained_earnings": ZERO},
        {"label": "Other movements in reserves", "share_capital": ZERO, "reserves": _bs(fin, "reserves") - res_open, "retained_earnings": ZERO},
        {"label": "Dividends", "share_capital": ZERO, "reserves": ZERO, "retained_earnings": dividends},
    ]
    end = {k: sum((r[k] for r in rows), ZERO) for k in ("share_capital", "reserves", "retained_earnings")}
    rows.append({"label": "Balance at the end of the year", **end, "kind": "total"})
    for r in rows:
        r["total"] = r["share_capital"] + r["reserves"] + r["retained_earnings"]
    rows = [r for r in rows if r.get("kind") or r["total"] or r["share_capital"] or r["reserves"]]
    total = end["share_capital"] + end["reserves"] + end["retained_earnings"]
    notes = [] if has_comp else ["No comparative trial balance: the opening stated capital and reserves are taken as their closing balances."]
    return {"rows": rows, "check": {"label": "Closing equity agrees with the statement of financial position",
                                    "passed": total == fin["totals"]["equity"], "difference": total - fin["totals"]["equity"]}, "notes": notes}


def cash_flows(fin: dict) -> dict:
    """The statement of cash flows, indirect method, from the movement between the comparative and current balances."""
    if not fin.get("has_comparative"):
        return {"available": False, "reason": "The statement of cash flows needs the comparative (prior year) balances: add them to the trial balance."}
    cur = fin["pl"]["current"]

    def mv(h):  # increase in the balance shown
        return _bs(fin, h) - _bs(fin, h, "comparative")

    dep, amort = depreciation(fin)
    op = [("Profit before tax", cur["pbt"], ""), ("Depreciation", dep, "Expense accounts named depreciation"),
          ("Amortisation", amort, "Expense accounts named amortisation"), ("Finance costs", cur["finance_costs"], ""),
          ("(Increase) / decrease in inventories", -mv("inventories"), ""),
          ("(Increase) / decrease in trade and other receivables", -mv("trade_receivables"), ""),
          ("(Increase) / decrease in other current assets", -mv("other_current_assets"), ""),
          ("Increase / (decrease) in trade and other payables", mv("trade_payables"), ""),
          ("Increase / (decrease) in other current liabilities", mv("other_current_liabilities"), "")]
    generated = sum((a for _, a, _ in op), ZERO)
    tax_paid = _bs(fin, "tax_payable", "comparative") + cur["income_tax_expense"] - _bs(fin, "tax_payable") - mv("deferred_tax")
    op_after = [("Interest paid", -cur["finance_costs"], "Taken as the finance costs charged"),
                ("Income tax paid", -tax_paid, "Opening tax payable + tax expense - closing tax payable - deferred tax movement")]
    operating = generated + sum((a for _, a, _ in op_after), ZERO)
    inv = [("Purchase of property, plant and equipment (net of disposals)", -(mv("ppe") + dep), "Movement in PPE + depreciation"),
           ("Deposits paid", -mv("other_non_current_assets"), ""),
           ("Purchase of intangible assets (net)", -(mv("intangibles") + amort), "Movement in intangibles + amortisation"),
           ("(Increase) / decrease in investments", -mv("investments"), "")]
    investing = sum((a for _, a, _ in inv), ZERO)
    fin_rows = [("Proceeds from the issue of shares", mv("share_capital"), ""),
                ("Net movement in borrowings", mv("borrowings_non_current") + mv("borrowings_current"), "Including any overdraft in current borrowings"),
                ("Net movement in shareholder's current account", mv("shareholder_current_account"), ""),
                ("Dividends paid", _bs(fin, "dividends"), "")]
    financing = sum((a for _, a, _ in fin_rows), ZERO)
    net = operating + investing + financing
    opening, closing = _bs(fin, "cash", "comparative"), _bs(fin, "cash")

    def rows(items):
        return [{"label": lb, "amount": a, "note": n} for lb, a, n in items if a or not n]

    sections = [
        {"key": "operating", "title": "Cash flows from operating activities", "rows": rows(op), "subtotal": ("Cash generated from operations", generated),
         "after": rows(op_after), "total": ("Net cash from operating activities", operating)},
        {"key": "investing", "title": "Cash flows from investing activities", "rows": rows(inv), "total": ("Net cash used in investing activities", investing)},
        {"key": "financing", "title": "Cash flows from financing activities", "rows": rows(fin_rows), "total": ("Net cash from financing activities", financing)},
    ]
    for s in sections:
        s["subtotal"] = {"label": s["subtotal"][0], "amount": s["subtotal"][1]} if s.get("subtotal") else None
        s["total"] = {"label": s["total"][0], "amount": s["total"][1]}
    diff = opening + net - closing
    return {"available": True, "sections": sections, "net_change": net, "opening_cash": opening, "closing_cash": closing,
            "check": {"label": "Opening cash + net change = closing cash", "passed": diff == ZERO, "difference": diff},
            "notes": ["Derived from the balance movements (indirect method): check the derived lines against the ledgers."] +
                     ([f"A difference of {diff:,.2f}: a non-cash movement (e.g. a revaluation or a reserve transfer) to reflect."] if diff else [])}


POLICY_TEXT = [
    ("revenue", "Revenue", "Revenue is recognised when control of goods or services passes to the customer, at the amount of consideration "
                           "the entity expects to be entitled to, net of trade discounts and taxes collected for the Government (VAT, SSCL)."),
    ("ppe", "Property, plant and equipment", "Property, plant and equipment are stated at cost less accumulated depreciation and any impairment. "
                                             "Depreciation is charged on a straight-line basis over the assets' estimated useful lives. [State the rates or useful lives used.]"),
    ("intangibles", "Intangible assets", "Intangible assets are stated at cost less accumulated amortisation and impairment, amortised over their useful lives."),
    ("inventories", "Inventories", "Inventories are measured at the lower of cost and net realisable value. Cost is determined on the "
                                   "[first-in, first-out / weighted average] basis."),
    ("trade_receivables", "Financial instruments", "Trade and other receivables are measured at amortised cost less an allowance for expected credit "
                                                    "losses. Trade and other payables are measured at amortised cost."),
    ("borrowings", "Borrowings", "Borrowings are recognised initially at fair value net of transaction costs and subsequently at amortised cost; "
                                 "interest is charged to profit or loss using the effective interest method."),
    ("tax", "Income tax", "The income tax expense comprises current and deferred tax. Current tax is provided in accordance with the Inland Revenue "
                          "Act No. 24 of 2017 and its amendments, at the rates enacted at the reporting date."),
    ("employee", "Employee benefits", "Contributions to the Employees' Provident Fund and Employees' Trust Fund are charged to profit or loss as "
                                      "incurred. The retirement gratuity is provided for in accordance with the Payment of Gratuity Act No. 12 of 1983."),
    ("cash", "Cash and cash equivalents", "Cash and cash equivalents comprise cash in hand and at bank and short-term deposits with maturities of three "
                                          "months or less, net of bank overdrafts repayable on demand."),
]


def policies(fin: dict, engagement: dict) -> list[dict]:
    """The basis of preparation and the policies the entity's balances call for: standard wording, to tailor."""
    framework = FRAMEWORK.get(engagement.get("reporting_framework") or "smes", FRAMEWORK["smes"])
    present = {h for h, v in (fin.get("bs") or {}).items() if v.get("amount") or v.get("comparative")}
    present |= {r["heading"] for r in (fin.get("pl") or {}).get("rows") or []}
    names = " ".join(ln.get("name") or "" for ln in fin.get("tb") or fin.get("lines") or [])
    out = [{"key": "basis", "title": "Basis of preparation",
            "text": f"The financial statements have been prepared in accordance with {framework}, on the historical cost basis and on the going "
                    "concern basis. They are presented in Sri Lanka Rupees (LKR), the entity's functional currency. [Confirm the going concern "
                    "assessment.]"}]
    for key, title, text in POLICY_TEXT:
        wanted = {"borrowings": bool(present & {"borrowings_current", "borrowings_non_current"}), "tax": True,
                  "employee": bool(re.search(r"epf|etf|gratuity|retirement", names, re.I))}.get(key, key in present)
        if wanted:
            out.append({"key": key, "title": title, "text": text})
    custom = (engagement.get("data") or {}).get("policy_text") or {}
    return [{**p, "text": custom[p["key"]], "standard": False} if custom.get(p["key"]) else {**p, "standard": True} for p in out]


def notes(fin: dict, engagement: dict, comp: dict | None = None) -> list[dict]:
    """The notes: corporate information, the policies, then one numbered note per heading with its accounts
    (current and comparative), the income tax reconciliation and the matters only the accountant can complete."""
    out = [{"no": 1, "key": "corporate", "title": "Corporate information", "text":
            f"{engagement.get('legal_name') or '[Entity]'} ({engagement.get('nic_or_reg') or '[registration no.]'}) is a company incorporated and "
            f"domiciled in Sri Lanka. Registered office: {engagement.get('address') or '[address]'}. Principal activity: "
            f"{engagement.get('activity') or '[activity]'}."},
           {"no": 2, "key": "policies", "title": "Basis of preparation and significant accounting policies", "policies": policies(fin, engagement)}]
    n = 3
    income_only = fin.get("scope") == "income_statement"
    order = [h for h in PL_ORDER] + ([] if income_only else [h for h, v in HEADINGS.items() if v[0] == "bs"])
    rows_by_heading = {r["heading"]: r for r in (fin.get("pl") or {}).get("rows") or []}
    for h in order:
        if h in rows_by_heading:
            row = rows_by_heading[h]
            lines, total, total_c = row["lines"], row["amount"], row["comparative"]
        else:
            v = (fin.get("bs") or {}).get(h)
            if not v or not (v["amount"] or v["comparative"]):
                continue
            lines, total, total_c = v["lines"], v["amount"], v["comparative"]
        if not lines:
            continue
        sign = -1 if HEADINGS[h][2] in ("income", "equity", "liability") else 1
        out.append({"no": n, "key": h, "title": HEADINGS[h][1], "total": total, "total_comparative": total_c,
                    "lines": [{"code": ln["code"], "name": ln["name"], "amount": sign * ln["amount"],
                               "comparative": sign * ln["comparative"] if ln.get("comparative") is not None else None} for ln in lines]})
        n += 1
    if comp:
        accounting = (fin.get("pl") or {}).get("current", {}).get("income_tax_expense") or ZERO
        out.append({"no": n, "key": "tax_reconciliation", "title": "Income tax - reconciliation", "rows": [
            {"label": "Profit before tax", "amount": comp.get("pbt")},
            {"label": "Add: disallowable expenses and adjustments", "amount": comp.get("total_add_backs")},
            {"label": "Less: allowable deductions, allowances and losses", "amount": -(comp.get("total_deductions") or ZERO)},
            {"label": "Taxable income (per the tax computation)", "amount": comp.get("taxable_income")},
            {"label": "Income tax on taxable income", "amount": comp.get("income_tax")},
            {"label": "Income tax expense in profit or loss", "amount": accounting},
            {"label": "Difference (deferred tax / under- or over-provision)", "amount": accounting - (comp.get("income_tax") or ZERO)}]})
        n += 1
    for key, title in (("events", "Events after the reporting period"), ("contingencies", "Contingent liabilities and commitments"),
                       ("related", "Related party transactions")):
        written = ((engagement.get("data") or {}).get("note_text") or {}).get(key)
        out.append({"no": n, "key": key, "title": title, "text": written or "[To be completed by the accountant.]", "to_complete": not written,
                    "editable": True})
        n += 1
    return out


def audit_report(engagement: dict, year_end: str) -> dict:
    """The draft independent auditor's report, structured on SLAuS 700 (Revised): a labelled template with every
    judgement left for the auditor. Never an opinion."""
    name = engagement.get("legal_name") or "[Entity]"
    framework = FRAMEWORK.get(engagement.get("reporting_framework") or "smes", FRAMEWORK["smes"])
    return {"label": "DRAFT TEMPLATE - NOT AN AUDIT OPINION", "title": "Independent Auditor's Report", "addressee": f"To the shareholders of {name}",
            "sections": [
                {"title": "Report on the audit of the financial statements", "text": ""},
                {"title": "Opinion", "text": f"[To be completed by the auditor after the audit.] We have audited the financial statements of {name}, which "
                                             f"comprise the statement of financial position as at {year_end}, and the statement of profit or loss and other "
                                             "comprehensive income, statement of changes in equity and statement of cash flows for the year then ended, "
                                             "and notes to the financial statements, including a summary of significant accounting policies. "
                                             f"[Opinion wording - unmodified / qualified / adverse / disclaimer - chosen by the auditor under {framework}.]"},
                {"title": "Basis for opinion", "text": "[To be completed by the auditor.] We conducted our audit in accordance with Sri Lanka Auditing "
                                                       "Standards (SLAuSs). Our responsibilities are described in the Auditor's responsibilities section. "
                                                       "We are independent of the Company in accordance with the Code of Ethics issued by CA Sri Lanka."},
                {"title": "Key audit matters", "text": "[If applicable - the auditor's judgement.]"},
                {"title": "Other information", "text": "[If applicable.]"},
                {"title": "Responsibilities of management and those charged with governance", "text":
                    f"Management is responsible for the preparation of financial statements that give a true and fair view in accordance with {framework} "
                    "and the Companies Act No. 07 of 2007, and for such internal control as management determines is necessary."},
                {"title": "Auditor's responsibilities for the audit of the financial statements", "text": "[Standard SLAuS 700 wording - to be completed by the auditor.]"},
                {"title": "Report on other legal and regulatory requirements", "text": "[Section 163(2) of the Companies Act No. 07 of 2007 - to be completed by the auditor.]"},
            ],
            "signature": "[Auditor's name / firm], Chartered Accountants\n[Place]\n[Date]"}
