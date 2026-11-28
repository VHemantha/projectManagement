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


OVERDRAFT = re.compile(r"overdraft|\bo/?d\b", re.I)


def overdraft(fin: dict, which: str = "amount") -> Decimal:
    """Bank overdrafts (short-term borrowings named as overdrafts), as a positive amount owed. For the statement of cash
    flows they are part of cash and cash equivalents (LKAS 7.8), not financing (AFIT, 28 Nov 2026)."""
    lines = ((fin.get("bs") or {}).get("borrowings_current") or {}).get("lines") or []
    return -sum(((ln.get(which) or ZERO) for ln in lines if OVERDRAFT.search(ln.get("name") or "")), ZERO)


def cash_flows(fin: dict) -> dict:
    """The statement of cash flows, indirect method, from the movement between the comparative and current balances."""
    if not fin.get("has_comparative"):
        return {"available": False, "reason": "The statement of cash flows needs the comparative (prior year) balances: add them to the trial balance."}
    cur = fin["pl"]["current"]

    def mv(h):  # increase in the balance shown
        return _bs(fin, h) - _bs(fin, h, "comparative")

    dep, amort = depreciation(fin)
    od, od_prior = overdraft(fin), overdraft(fin, "comparative")
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
                ("Net movement in borrowings", mv("borrowings_non_current") + mv("borrowings_current") - (od - od_prior),
                 "Bank overdrafts excluded: they are part of cash and cash equivalents"),
                ("Net movement in shareholder's current account", mv("shareholder_current_account"), ""),
                ("Dividends paid", _bs(fin, "dividends"), "")]
    financing = sum((a for _, a, _ in fin_rows), ZERO)
    net = operating + investing + financing
    # cash and cash equivalents: cash at bank and in hand less bank overdrafts
    opening, closing = _bs(fin, "cash", "comparative") - od_prior, _bs(fin, "cash") - od

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
            "cash_components": {"cash": _bs(fin, "cash"), "overdraft": od, "cash_comparative": _bs(fin, "cash", "comparative"),
                                "overdraft_comparative": od_prior},
            "check": {"label": "Opening cash + net change = closing cash", "passed": diff == ZERO, "difference": diff},
            "notes": ["Derived from the balance movements (indirect method): check the derived lines against the ledgers."] +
                     ([f"A difference of {diff:,.2f}: a non-cash movement (e.g. a revaluation or a reserve transfer) to reflect."] if diff else [])}


# The accounting policies, as AFIT's house format sets them out: (key, title, standard reference under full SLFRS/LKAS,
# when it applies, wording). Bracketed text is for the accountant to tailor.
POLICY_TEXT = [
    ("judgements", "Judgements, estimates and going concern", "", "always",
     "Management considers expected cash flows and financing available for at least twelve months from the reporting date. Material "
     "uncertainties are disclosed when identified. Estimates affect asset lives, expected credit losses and tax. Estimates are reviewed when new "
     "information becomes available. Changes in estimates are recognised prospectively."),
    ("revenue", "Revenue from contracts with customers", "SLFRS 15", "revenue",
     "The Company recognises revenue when it satisfies a performance obligation by transferring the promised goods or services to the customer, "
     "at the amount of consideration it expects to be entitled to. [Describe each revenue stream and whether it is recognised over time or at a "
     "point in time.] Transaction prices exclude taxes collected on behalf of third parties. Amounts billed before performance are contract "
     "liabilities. Receivables are recognised when entitlement is unconditional."),
    ("expenses", "Cost of sales and operating expenses", "", "always",
     "Direct costs of providing the Company's goods and services are included in cost of sales as they are delivered. Other expenses are "
     "recognised on an accrual basis and classified by function. Interest income is recognised using the effective interest method when applicable."),
    ("ppe", "Property, plant and equipment", "LKAS 16", "ppe",
     "Property, plant and equipment is measured at cost less accumulated depreciation and impairment. Cost includes directly attributable "
     "expenditure. Depreciation begins when assets are available for use and is charged on a straight-line basis over their estimated useful "
     "lives [state the useful lives or rates by class]. Useful lives, residual values and methods are reviewed annually. Disposal gains or losses "
     "are the difference between net proceeds and carrying amount and are recognised in profit or loss."),
    ("intangibles", "Intangible assets", "LKAS 38", "intangibles",
     "Intangible assets are measured at cost less accumulated amortisation and impairment, and amortised on a straight-line basis over their "
     "estimated useful lives [state the useful lives]."),
    ("impairment", "Impairment of non-financial assets", "LKAS 36", "long_lived",
     "Assets are assessed for impairment indicators at each reporting date. If indicators exist, recoverable amount is the higher of value in use "
     "and fair value less costs of disposal. Impairment is recorded for any excess carrying amount. A reversal is limited to the carrying amount "
     "that would have existed without the impairment."),
    ("inventories", "Inventories", "LKAS 2", "inventories",
     "Inventories are measured at the lower of cost and net realisable value. Cost is determined on the [first-in, first-out / weighted average] basis."),
    ("trade_receivables", "Financial instruments and cash", "SLFRS 9, SLFRS 7 and LKAS 7", "always",
     "Receivables and refundable deposits held to collect solely principal and interest are measured at amortised cost, subject to impairment. "
     "Trade receivables without a significant financing component are initially measured at transaction price. Lifetime expected credit losses are "
     "estimated for trade receivables using historical experience adjusted for current and forward-looking information. Trade payables and "
     "shareholder advances are measured at amortised cost. Cash and cash equivalents comprise cash in hand and demand deposits, plus highly liquid "
     "short-term placements with insignificant risk of changes in value held to meet short-term commitments."),
    ("borrowings", "Borrowings", "SLFRS 9", "borrowings",
     "Borrowings are recognised initially at fair value net of transaction costs and subsequently at amortised cost; interest is charged to profit "
     "or loss using the effective interest method."),
    ("tax", "Income tax", "LKAS 12", "always",
     "Current tax is measured at the amount expected to be paid or recovered under the Inland Revenue Act No. 24 of 2017 and its amendments, using "
     "the rates enacted or substantively enacted at the reporting date. Deferred tax is recognised on temporary differences, subject to the "
     "applicable exceptions, using the rates expected when assets are recovered or liabilities settled. Deferred tax assets are recognised to the "
     "extent that sufficient taxable profit is probable. Tax follows the underlying item into profit or loss, other comprehensive income or equity."),
    ("leases", "Leases", "SLFRS 16", "always",
     "At commencement the Company recognises a right-of-use asset and a lease liability measured at the present value of unpaid lease payments. "
     "The asset is subsequently depreciated and assessed for impairment. The liability is increased by interest, reduced by payments and remeasured "
     "when required. [Short-term and low-value leases for which the exemption is elected are expensed on a straight-line basis.]"),
    ("employee", "Employee benefits", "LKAS 19", "always",
     "Short-term benefits are expensed as employees provide services. Contributions to the Employees' Provident Fund and the Employees' Trust Fund "
     "are expensed as incurred. The retirement gratuity, where an obligation exists under the Payment of Gratuity Act No. 12 of 1983, is measured "
     "using the projected unit credit method, with remeasurements recognised in other comprehensive income."),
    ("foreign_currency", "Foreign currency", "LKAS 21", "always",
     "Transactions are translated at the exchange rate on the transaction date. Monetary balances are translated at the closing rate. Exchange "
     "differences generally enter profit or loss. Historical-cost non-monetary items use the transaction-date rate."),
    ("provisions", "Provisions and contingencies", "LKAS 37", "always",
     "A provision is recognised for a present obligation from a past event when an outflow is probable and the amount can be reliably estimated. "
     "Contingent liabilities are disclosed unless an outflow is remote. Contingent assets are disclosed when an inflow is probable and recognised "
     "only when virtually certain."),
    ("related", "Related parties and subsequent events", "LKAS 24 and LKAS 10", "always",
     "Material related-party transactions, outstanding balances and key management compensation are disclosed. Subsequent events providing evidence "
     "of conditions at the reporting date are adjusted. Material non-adjusting events are disclosed with their estimated effect, where practicable."),
]


def policies(fin: dict, engagement: dict) -> list[dict]:
    """The basis of preparation and the policies the entity's balances call for: standard wording, to tailor. Under
    full SLFRS/LKAS each title carries its standard, as in AFIT's house format."""
    fw_key = engagement.get("reporting_framework") or "smes"
    framework = FRAMEWORK.get(fw_key, FRAMEWORK["smes"])
    present = {h for h, v in (fin.get("bs") or {}).items() if v.get("amount") or v.get("comparative")}
    present |= {r["heading"] for r in (fin.get("pl") or {}).get("rows") or []}
    out = [{"key": "basis", "title": "Basis of preparation and material accounting policy information", "ref": "",
            "text": f"These financial statements have been prepared in accordance with {framework}, on the historical cost basis and on the going "
                    "concern basis. Sri Lanka rupees (LKR) are the functional and presentation currency. Amounts are rounded to the nearest rupee. "
                    "Comparative figures are presented for the preceding year."}]
    for key, title, ref, when, text in POLICY_TEXT:
        wanted = {"always": True, "borrowings": bool(present & {"borrowings_current", "borrowings_non_current"}),
                  "long_lived": bool(present & {"ppe", "intangibles"})}.get(when, when in present)
        if wanted:
            ref = ref if fw_key == "full" else ""
            out.append({"key": key, "title": f"{title} ({ref})" if ref else title, "text": text})
    out = [{**p, "text": for_entity(p["text"], engagement)} for p in out]
    custom = (engagement.get("data") or {}).get("policy_text") or {}
    return [{**p, "text": custom[p["key"]], "standard": False} if custom.get(p["key"]) else {**p, "standard": True} for p in out]


NOUN = {"company": "Company", "partnership": "Partnership", "individual": "business"}
OWNERS = {"company": "shareholder advances", "partnership": "amounts due to the partners", "individual": "amounts due to the proprietor"}


def for_entity(text: str, engagement: dict) -> str:
    """Standard wording written for a company, said of a partnership or a sole proprietor's business instead."""
    entity = engagement.get("entity_type") if engagement.get("entity_type") in NOUN else "company"
    if entity == "company":
        return text
    noun = NOUN[entity]
    return (text.replace("The Company's", f"The {noun}'s").replace("the Company's", f"the {noun}'s").replace("The Company", f"The {noun}")
            .replace("the Company", f"the {noun}").replace("shareholder advances", OWNERS[entity]))


def notes(fin: dict, engagement: dict, comp: dict | None = None, rate: Decimal | None = None) -> list[dict]:
    """The notes: corporate information, the policies, then one numbered note per heading with its accounts
    (current and comparative), the income tax reconciliation and the matters only the accountant can complete."""
    what = {"partnership": "is a partnership carrying on business in Sri Lanka", "individual": "is a sole proprietorship carrying on business in Sri Lanka"}.get(
        engagement.get("entity_type"), f"({engagement.get('nic_or_reg') or '[registration no.]'}) is a company incorporated and domiciled in Sri Lanka")
    out = [{"no": 1, "key": "corporate", "title": "Corporate information", "text":
            f"{engagement.get('legal_name') or '[Entity]'} {what}. Principal place of business: {engagement.get('address') or '[address]'}. "
            f"Principal activity: {engagement.get('activity') or '[activity]'}."},
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
        pbt = (fin.get("pl") or {}).get("current", {}).get("pbt") or ZERO
        tax = comp.get("income_tax") or ZERO
        rows = [{"label": "Accounting profit before tax", "amount": pbt}]
        if rate:
            pct = format((Decimal(rate) * 100).normalize(), "f")
            at_rate = (pbt * rate).quantize(Decimal("0.01"))
            add = ((comp.get("total_add_backs") or ZERO) * rate).quantize(Decimal("0.01"))
            ded = -((comp.get("total_deductions") or ZERO) * rate).quantize(Decimal("0.01"))
            rows += [{"label": f"Tax at the standard rate of {pct}%", "amount": at_rate},
                     {"label": "Tax effect of disallowable expenses", "amount": add},
                     {"label": "Tax effect of allowable deductions, allowances and losses", "amount": ded}]
            other = tax - at_rate - add - ded
            if other:
                rows.append({"label": "Tax effect of income taxed at other rates and tax losses", "amount": other})
        else:
            rows += [{"label": "Add: disallowable expenses and adjustments", "amount": comp.get("total_add_backs")},
                     {"label": "Less: allowable deductions, allowances and losses", "amount": -(comp.get("total_deductions") or ZERO)},
                     {"label": "Taxable income (per the tax computation)", "amount": comp.get("taxable_income")}]
        rows.append({"label": "Income tax on taxable income (per the tax computation)", "amount": tax, "kind": "subtotal"})
        if accounting - tax:
            rows.append({"label": "Deferred tax and under- / (over-) provision", "amount": accounting - tax})
        rows.append({"label": "Income tax expense in profit or loss", "amount": accounting, "kind": "total"})
        out.append({"no": n, "key": "tax_reconciliation", "title": "Income tax - reconciliation", "rows": rows, "rate": rate})
        n += 1
    for key, title in (("events", "Events after the reporting period"), ("contingencies", "Contingent liabilities and commitments"),
                       ("related", "Related party transactions")):
        data = engagement.get("data") or {}
        written = (data.get("note_text") or {}).get(key)
        # From the questionnaire when the accountant hasn't written it (AFIT, 28 Nov 2026): the client's details for a
        # yes, the nil wording for a no; unanswered, the nil wording too, with the question still to be answered.
        answer = (data.get("disclosures") or {}).get(key) or {}
        if key == "contingencies":
            more = (data.get("disclosures") or {}).get("commitments") or {}
            details = " ".join(x.get("details", "") for x in (more, answer) if x.get("answer") == "yes" and x.get("details"))
            answered = bool(more.get("answer") and answer.get("answer"))
        else:
            details = answer.get("details", "") if answer.get("answer") == "yes" else ""
            answered = bool(answer.get("answer"))
        text = written or details or NIL_WORDING[key]
        out.append({"no": n, "key": key, "title": title, "text": text, "to_complete": not (written or answered), "editable": True})
        n += 1
    return out


NIL_WORDING = {
    "events": "No events have arisen after the reporting date that require adjustment to, or disclosure in, the financial statements.",
    "contingencies": "There were no material capital commitments or contingent liabilities at the reporting date.",
    "related": "There were no related party transactions other than those disclosed in these financial statements.",
}


def audit_report(engagement: dict, year_end: str) -> dict:
    """The draft independent auditor's report, laid out as AFIT's report on SLAuS 700 (Revised): the standard wording,
    with the opinion left for the auditor to confirm or modify. A labelled template - never an opinion."""
    name = engagement.get("legal_name") or "[Entity]"
    entity = engagement.get("entity_type") if engagement.get("entity_type") in NOUN else "company"
    framework = "Sri Lanka Accounting Standards (SLFRS and LKAS)" if (engagement.get("reporting_framework") or "smes") == "full" else \
        FRAMEWORK.get(engagement.get("reporting_framework") or "smes", FRAMEWORK["smes"]).replace(" issued by CA Sri Lanka", "")
    report = {"label": "DRAFT TEMPLATE - NOT AN AUDIT OPINION", "title": "Independent Auditor's Report", "addressee": f"To the {({'company': 'Shareholders', 'partnership': 'Partners', 'individual': 'Proprietor'})[entity]} of {name}",
            "sections": [
                {"title": "Report on the Audit of the Financial Statements", "text": ""},
                {"title": "Opinion", "text":
                    f"We have audited the financial statements of {name}, which comprise the statement of financial position as at {year_end}, and the "
                    "comprehensive income statement, statement of changes in equity and cash flow statement for the year then ended, and notes to the "
                    "financial statements, including material accounting policy information.\n\n"
                    "[Opinion - the auditor to confirm or modify after the audit.] In our opinion, the accompanying financial statements give a true and "
                    f"fair view of the financial position of the Company as at {year_end}, and of its financial performance and cash flows for the year "
                    f"then ended in accordance with {framework}."},
                {"title": "Basis for Opinion", "text":
                    "We conducted our audit in accordance with Sri Lanka Auditing Standards (SLAuSs). Our responsibilities under those standards are "
                    "further described in the Auditor's Responsibilities for the Audit of the Financial Statements section of our report. We are "
                    "independent of the Company in accordance with the Code of Ethics issued by CA Sri Lanka and have fulfilled our other ethical "
                    "responsibilities in accordance with that Code. We believe that the audit evidence we have obtained is sufficient and appropriate "
                    "to provide a basis for our opinion."},
                {"title": "Responsibilities of Management and Those Charged with Governance for the Financial Statements", "text":
                    f"Management is responsible for the preparation of financial statements that give a true and fair view in accordance with {framework}, "
                    "and for such internal control as management determines is necessary to enable the preparation of financial statements that are "
                    "free from material misstatement, whether due to fraud or error.\n\n"
                    "In preparing the financial statements, management is responsible for assessing the Company's ability to continue as a going "
                    "concern, disclosing, as applicable, matters related to going concern and using the going concern basis of accounting unless "
                    "management either intends to liquidate the Company or to cease operations, or has no realistic alternative but to do so.\n\n"
                    "Those charged with governance are responsible for overseeing the Company's financial reporting process."},
                {"title": "Auditor's Responsibilities for the Audit of the Financial Statements", "text":
                    "Our objectives are to obtain reasonable assurance about whether the financial statements as a whole are free from material "
                    "misstatement, whether due to fraud or error, and to issue an auditor's report that includes our opinion. Reasonable assurance is a "
                    "high level of assurance, but is not a guarantee that an audit conducted in accordance with SLAuSs will always detect a material "
                    "misstatement when it exists. Misstatements can arise from fraud or error and are considered material if, individually or in the "
                    "aggregate, they could reasonably be expected to influence the economic decisions of users taken on the basis of these financial "
                    "statements."},
                {"title": "Auditor's Responsibilities for the Audit of the Financial Statements (continued)", "continued": True, "text":
                    "As part of an audit in accordance with SLAuSs, we exercise professional judgement and maintain professional scepticism throughout "
                    "the audit. We also:\n\n"
                    "\u2022 Identify and assess the risks of material misstatement due to fraud or error, design procedures responsive to those risks, and "
                    "obtain sufficient appropriate audit evidence. Fraud may involve collusion, forgery, intentional omissions, misrepresentation or "
                    "override of internal control, so the risk of failing to detect a fraud-related misstatement is higher.\n\n"
                    "\u2022 Obtain an understanding of relevant internal control to design appropriate audit procedures. Our audit does not express an "
                    "opinion on the effectiveness of the Company's internal control.\n\n"
                    "\u2022 Evaluate the appropriateness of accounting policies and the reasonableness of accounting estimates and related disclosures.\n\n"
                    "\u2022 Conclude on the appropriateness of management's use of the going concern basis and whether a material uncertainty exists. If "
                    "it does, we draw attention to adequate disclosures or modify our opinion if disclosures are inadequate. Our conclusions are based "
                    "on evidence available up to the date of our report. Future events or conditions may cause the Company to cease to continue as a "
                    "going concern.\n\n"
                    "\u2022 Evaluate the overall presentation, structure and content of the financial statements, including disclosures, and whether they "
                    "represent the underlying transactions and events in a manner that achieves fair presentation.\n\n"
                    "We communicate with those charged with governance regarding, among other matters, the planned scope and timing of the audit and "
                    "significant audit findings, including significant deficiencies in internal control that we identify during our audit."},
                {"title": "Report on Other Legal and Regulatory Requirements", "text":
                    ("As required by section 163(2) of the Companies Act No. 7 of 2007, we" if entity == "company" else "We") +
                    " have obtained all the information and explanations that were required for the audit and, as far as appears from our "
                    "examination, proper accounting records have been kept by the Company."},
            ],
            "signature": "AFIT Connect\nChartered Accountants\nGampaha\n[Date of the report]"}
    for sec in report["sections"]:
        sec["text"] = for_entity(sec["text"], engagement)
    return report
