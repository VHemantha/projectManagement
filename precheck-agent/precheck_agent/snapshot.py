"""The Job Snapshot (AFIT design requirements, 16 Nov 2026): the first thing the preparer sees, a
one-page story of the client and its year - what it does and how it earns money, what it owns and
how that is funded, who owns it and their current accounts, how it earns and spends, the year's
significant events, what to pay attention to, and what the AI understood.

Who does what:
- Code works out every figure from the records: last year's trial balance (or signed statements)
  with its comparative column, and this year's general ledger when there is one. Lines are grouped
  by what they are (property and equipment, cash, receivables; bank borrowing, shareholder funding,
  trade payables ...), each with the line it came from, so a figure can be opened to its source.
- The model writes the words, in the same call as the pre-check: the business story, revenue
  sources, events (each confirmed, inferred or unresolved), ownership where a document shows it,
  focus areas and what it understood. Code keeps only real sources, and flags a sentence whose
  figures are not in the records. No percentage or total in the snapshot is the model's own.

The snapshot explains the business; the pre-check findings say what needs attention.
"""
import re

from .textutil import clip_words

STATUSES = ("confirmed", "inferred", "unresolved")
# The snapshot's findings under the firm's headings, in this order (AFIT, 21 Nov 2026).
SECTIONS = (
    ("company_background", "Company background",
     "company name, incorporation, starting date, legal structure, ownership and shareholding, principal activities, locations and reporting period"),
    ("nature_of_business", "Nature of business",
     "main products or services, how revenue is generated, key customers, suppliers and the business model"),
    ("business_environment", "Business environment",
     "industry conditions, competition, economic factors, regulatory requirements and significant external changes"),
    ("management_governance", "Management and governance",
     "directors, shareholders, key management personnel, governance structure and management changes"),
    ("financial_performance", "Financial performance",
     "revenue, gross profit, net profit, major expenses, comparison with the prior year and significant fluctuations"),
    ("financial_position", "Financial position",
     "major assets, liabilities, equity, working capital, borrowings, liquidity and unusual balances"),
    ("significant_events", "Significant transactions and events",
     "major asset purchases, loans, investments, related-party transactions, restructuring, litigation and unusual transactions"),
    ("accounting_policies", "Accounting policies and reporting framework",
     "the applicable framework (NZ IFRS, PBE standards, special purpose or tax-only reporting), significant accounting policies, changes in "
     "policies, estimates and judgements"),
    ("key_risks", "Key accounting risks",
     "significant risks of material misstatement, revenue recognition, management override and other account-specific risks"),
    ("prior_year_matters", "Prior-year accounting matters",
     "previous accounting judgements, adjustments, management letter points, unresolved matters and recurring issues"),
    ("going_concern", "Going concern and future outlook",
     "cash flows, financial stability, financing arrangements, future business plans and going concern uncertainties"),
)
SECTION_KEYS = [k for k, _, _ in SECTIONS]
LEVELS = ("high", "medium", "low", "none")
MAX_FINDINGS = 5
EVENT_KINDS = ("purchase", "disposal", "financing", "dividend", "investment", "trading", "structure", "other")

_STR = {"type": "string"}
_IDS = {"type": "array", "items": _STR}
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["business_story", "revenue_sources", "financial_story", "events", "ownership", "current_accounts", "focus_areas", "understood",
                 "sections"],
    "properties": {
        "sections": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["key", "summary", "findings"],
            "properties": {
                "key": {"type": "string", "enum": SECTION_KEYS},
                "summary": _STR,
                "findings": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["label", "text", "status", "level", "sources"],
                    "properties": {"label": _STR, "text": _STR, "status": {"type": "string", "enum": list(STATUSES)},
                                   "level": {"type": "string", "enum": list(LEVELS)}, "sources": _IDS}}},
            }}},
        "business_story": _STR,
        "revenue_sources": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["label", "detail", "sources"],
            "properties": {"label": _STR, "detail": _STR, "sources": _IDS}}},
        "financial_story": _STR,
        "events": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "kind", "status", "sources"],
            "properties": {"text": _STR, "kind": {"type": "string", "enum": list(EVENT_KINDS)},
                           "status": {"type": "string", "enum": list(STATUSES)}, "sources": _IDS}}},
        "ownership": {
            "type": "object", "additionalProperties": False, "required": ["shareholders", "note", "sources"],
            "properties": {
                "shareholders": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["name", "percent", "sources"],
                    "properties": {"name": _STR, "percent": {"type": "number"}, "sources": _IDS}}},
                "note": _STR, "sources": _IDS}},
        "current_accounts": _STR,
        "focus_areas": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["area", "why", "sources"],
            "properties": {"area": _STR, "why": _STR, "sources": _IDS}}},
        "understood": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "status", "sources"],
            "properties": {"text": _STR, "status": {"type": "string", "enum": list(STATUSES)}, "sources": _IDS}}},
    },
}

ANSWER = """- snapshot: the Job Snapshot, shown to the preparer BEFORE the findings (see the job-snapshot skill). It explains the business; it does not repeat the requests.
  business_story: 2-4 short sentences: what the client does and how it earns money. revenue_sources: 1-4 boxes (label of 1-3 words, detail of at most 12 words).
  financial_story: at most 3 sentences on growth, decline and profit, in words; code shows the figures and the changes, so do not calculate any percentage, difference or total yourself.
  events: the year's significant purchases, disposals, financing, dividends, investments and changes in trading or structure, each "confirmed" (a document shows it), "inferred" (the records suggest it: say what would confirm it) or "unresolved".
  ownership: shareholders with their percentage only where a document states it (percent -1 when it is not shown); never confuse ownership with current-account balances. current_accounts: one or two sentences on the shareholder current accounts, if the records show any.
  focus_areas: 2-4 areas the preparer should pay attention to, and why. understood: 1-2 statements linking the story to the records examined, with any material assumption or gap.
  sections: the snapshot's findings under the firm's eleven headings, one entry per heading, in this order:
""" + "\n".join(f"    {k}: {d}." for k, _, d in SECTIONS) + """
    Each: "summary" one plain sentence (at most 30 words); "findings" 0-5, each a "label" (1-5 words), "text" (at most 30 words), a status
    (confirmed, inferred, unresolved) and the sources. "level": for key_risks, how significant the risk of misstatement is (high, medium,
    low); "none" everywhere else. Where the records say nothing on a heading, say so in the summary ("Not shown in the documents read")
    with no findings: never fill a heading with guesses. Code shows every figure as a chart beside your words: do not calculate any.
  Every statement cites its sources."""

# What each balance is, from its label (and its trial balance section).
NON_CURRENT = [
    ("Property", r"\b(land|building|property|properties|premises|freehold|leasehold|house|flat|unit|apartment)\b"),
    ("Vehicles", r"\b(vehicle|motor|car|truck|van|ute)\b"),
    ("Plant and equipment", r"\b(plant|equipment|machinery|furniture|fixture|fitting|chattel|computer|tools?|office equipment|fixed asset)\b"),
    ("Investments", r"\b(investment|shares in|share portfolio|managed fund|kiwisaver|bonds?)\b"),
    ("Intangibles", r"\b(goodwill|intangible|software|intellectual property|licen[cs]e)\b"),
]
CURRENT = [
    ("Cash and bank", r"\b(cash|bank|cheque|savings|call account|term deposit|on call|everyday|anz|asb|bnz|westpac|kiwibank|tsb|heartland)\b|\b\d{2}-\d{4}-\d{7}-\d{2,3}\b"),
    ("Receivables", r"\b(receivable|debtor|accounts receivable|trade debtors|accrued income|owed by)\b"),
    ("Inventory", r"\b(inventor|stock on hand|stock\b|work in progress|wip)\b"),
    ("Prepayments and tax", r"\b(prepa|gst|income tax|rwt|tax refund|withholding)\b"),
]
FUNDING = [
    ("Shareholder funding", r"\b(shareholder|director|current account|owner|partner|advance from|beneficiar)"),
    ("Bank borrowing", r"\b(loan|mortgage|borrowing|overdraft|facility|anz|asb|bnz|westpac|kiwibank|heartland|tsb)\b"),
    ("Trade payables", r"\b(payable|creditor|accrual|accrued|accounts payable|trade creditors)\b"),
    ("Tax owed", r"\b(gst|income tax|paye|ird|tax payable|provisional|fbt|withholding)\b"),
]
DEPRECIATION = r"accumulated depreciation|accum\.? dep|less depreciation|provision for depreciation"
CURRENT_ACCOUNT = r"current account|shareholder|director('s)? loan|advance (from|to)|owner'?s? (loan|account)|drawings"
MAX_LINES = 6


def _group(label: str, groups: list[tuple[str, str]], other: str) -> str:
    for name, pattern in groups:
        if re.search(pattern, label, re.I):
            return name
    return other


def _signed(line: dict, from_tb: bool) -> tuple[float, float | None]:
    """A line's amount the way people read it: income, liabilities and equity positive. A trial
    balance is debit positive, credit negative; statements print each line positive."""
    if not from_tb:
        return line["amount"], line["comparative"]
    flip = -1 if line["section"] in ("Income", "Liabilities", "Equity") else 1
    comp = line["comparative"]
    return round(flip * line["amount"], 2), (None if comp is None else round(flip * comp, 2))


def _norm(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def figures(facts: dict, id_of: dict[int, str]) -> dict:
    """Every figure in the snapshot, worked out by code. `id_of` maps a line of
    facts["all_prior_lines"] (by its position) to its T id in the model's input, where it has one."""
    lines = facts.get("all_prior_lines") or []
    if not lines:
        return {"available": False, "basis": "", "year_label": "", "comparative_label": ""}
    from_tb = lines[0]["file"].get("document_class") == "trial_balance"
    rows = []
    for n, ln in enumerate(lines):
        amount, comparative = _signed(ln, from_tb)
        rows.append({"label": ln["label"], "section": ln["section"], "amount": amount, "comparative": comparative,
                     "source": id_of.get(n), "file": ln["file"], "block": ln["block"]})
    by = lambda section: [r for r in rows if r["section"] == section]  # noqa: E731
    total = lambda rs, key="amount": round(sum((r[key] or 0) for r in rs), 2)  # noqa: E731
    has_comp = any(r["comparative"] is not None for r in rows)

    income, expenses = by("Income"), by("Expenses")
    assets, liabilities, equity = by("Assets"), by("Liabilities"), by("Equity")

    def mix(rs: list[dict], groups, other: str) -> list[dict]:
        out: dict[str, dict] = {}
        for r in rs:
            name = _group(r["label"], groups, other)
            # Accumulated depreciation nets against its asset ("Motor vehicles - accumulated
            # depreciation" is a vehicle line); one that names no asset goes with plant and equipment.
            if groups is NON_CURRENT and name == other and re.search(DEPRECIATION, r["label"], re.I):
                name = "Plant and equipment"
            g = out.setdefault(name, {"label": name, "amount": 0.0, "comparative": 0.0, "lines": []})
            g["amount"] = round(g["amount"] + r["amount"], 2)
            g["comparative"] = round(g["comparative"] + (r["comparative"] or 0), 2)
            g["lines"].append(r)
        groups_out = [g for g in out.values() if abs(g["amount"]) >= 0.005]
        for g in groups_out:
            g["lines"] = sorted(g["lines"], key=lambda r: -abs(r["amount"]))[:MAX_LINES]
            if not has_comp:
                g["comparative"] = None
        return sorted(groups_out, key=lambda g: -g["amount"])

    non_current = [r for r in assets if _group(r["label"], NON_CURRENT, "") or re.search(DEPRECIATION, r["label"], re.I)]
    current = [r for r in assets if r not in non_current]
    asset_mix = mix(non_current, NON_CURRENT, "Other non-current assets") + mix(current, CURRENT, "Other current assets")
    funding = mix(liabilities, FUNDING, "Other liabilities")
    total_assets, total_liabilities = total(assets), total(liabilities)
    net_assets = round(total_assets - total_liabilities, 2)
    if net_assets:
        # Assets less liabilities: what is left for the owners, or a shortfall when the recorded
        # assets are less than what is owed (a property at cost, say, may not be in the records read).
        funding.append({"label": "Equity (what is left for the owners)" if net_assets > 0 else "Shortfall (owed more than the recorded assets)",
                        "amount": net_assets, "derived": True, "lines": [],
                        "comparative": round(total(assets, "comparative") - total(liabilities, "comparative"), 2) if has_comp else None})
    accounts = [r for r in liabilities + assets if re.search(CURRENT_ACCOUNT, r["label"], re.I)]
    current_accounts = [{**r, "direction": "owed to the shareholder" if r["section"] == "Liabilities" else "owed by the shareholder"}
                        for r in sorted(accounts, key=lambda r: -abs(r["amount"]))[:MAX_LINES]]

    def kpi(label: str, value: float, comp: float | None) -> dict:
        change = None if comp in (None, 0) else round((value - comp) / abs(comp) * 100)
        return {"label": label, "amount": value, "comparative": comp, "change_pct": change}

    rev, exp = total(income), total(expenses)
    rev_c, exp_c = (total(income, "comparative"), total(expenses, "comparative")) if has_comp else (None, None)
    kpis = []
    if income or expenses:
        kpis += [kpi("Revenue", rev, rev_c), kpi("Expenses", exp, exp_c),
                 kpi("Net profit", round(rev - exp, 2), None if rev_c is None else round(rev_c - exp_c, 2))]
    if assets:
        kpis.append(kpi("Total assets", total_assets, total(assets, "comparative") if has_comp else None))
    receivables = [r for r in current if _group(r["label"], CURRENT, "") == "Receivables"]
    if receivables:
        kpis.append(kpi("Money customers owe", total(receivables), total(receivables, "comparative") if has_comp else None))

    top = lambda rs: sorted(rs, key=lambda r: -abs(r["amount"]))[:MAX_LINES]  # noqa: E731
    return {
        "available": True,
        "basis": "trial_balance" if from_tb else "financial_statements",
        "year_label": "Last year", "comparative_label": "Year before" if has_comp else "",
        "kpis": kpis, "income": top(income), "expenses": top(expenses),
        "asset_mix": asset_mix, "funding_mix": funding, "current_accounts": current_accounts,
        "this_year": this_year(facts, rows),
    }


def this_year(facts: dict, rows: list[dict]) -> dict | None:
    """This year's income and expenses so far, from the general ledger: each ledger account that
    has the same name as one of last year's income or expense lines. None without a ledger."""
    ledger = facts.get("ledger") or []
    if not ledger:
        return None
    last = {_norm(r["label"]): r for r in rows if r["section"] in ("Income", "Expenses")}
    income = expenses = 0.0
    matched = 0
    for a in ledger:
        r = last.get(_norm(a["name"]))
        if r is None:
            continue
        movement = (a["debits"] or 0) - (a["credits"] or 0)
        if r["section"] == "Income":
            income += -movement
        else:
            expenses += movement
        matched += 1
    if not matched:
        return None
    return {"revenue": round(income, 2), "expenses": round(expenses, 2), "net_profit": round(income - expenses, 2), "accounts_matched": matched}


def clean(raw: dict | None, valid, figures_ok) -> dict | None:
    """The model's words, checked: real sources only, a status for every event and statement, and
    a flag on any sentence whose figures are not in the records. None when the answer had none."""
    if not raw:
        return None

    def sentence(text, limit):
        return clip_words(" ".join(str(text or "").split()), limit)

    def flags(text) -> list[str]:
        return [] if figures_ok(text) else ["figure_not_in_documents"]

    story = sentence(raw.get("business_story"), 80)
    fin = sentence(raw.get("financial_story"), 70)
    revenue = [{"label": sentence(r.get("label"), 4), "detail": sentence(r.get("detail"), 14), "sources": valid(r.get("sources", []))}
               for r in raw.get("revenue_sources") or [] if str(r.get("label", "")).strip()][:4]
    events = []
    for e in (raw.get("events") or [])[:6]:
        text = sentence(e.get("text"), 40)
        if not text:
            continue
        sources = valid(e.get("sources", []))
        status = e.get("status") if e.get("status") in STATUSES else "inferred"
        if status == "confirmed" and not sources:
            status = "inferred"  # said to be shown by a document, but cites none
        events.append({"text": text, "kind": e.get("kind") if e.get("kind") in EVENT_KINDS else "other", "status": status,
                       "sources": sources, "flags": flags(text)})
    own = raw.get("ownership") or {}
    holders = []
    for h in (own.get("shareholders") or [])[:8]:
        name = sentence(h.get("name"), 8)
        if not name:
            continue
        sources = valid(h.get("sources", []))
        pct = h.get("percent")
        verified = isinstance(pct, (int, float)) and 0 < pct <= 100 and bool(sources) and figures_ok(f"{pct:g}")
        holders.append({"name": name, "percent": float(pct) if verified else None, "sources": sources})
    if sum(h["percent"] or 0 for h in holders) > 100.5:  # not a real split: show no percentages
        holders = [{**h, "percent": None} for h in holders]
    focus = [{"area": sentence(f.get("area"), 6), "why": sentence(f.get("why"), 30), "sources": valid(f.get("sources", []))}
             for f in (raw.get("focus_areas") or []) if str(f.get("area", "")).strip()][:4]
    understood = [{"text": sentence(u.get("text"), 40), "status": u.get("status") if u.get("status") in STATUSES else "inferred",
                   "sources": valid(u.get("sources", []))} for u in (raw.get("understood") or []) if str(u.get("text", "")).strip()][:2]
    accounts = sentence(raw.get("current_accounts"), 50)
    sections = {}
    for sec in raw.get("sections") or []:
        key = sec.get("key")
        if key not in SECTION_KEYS or key in sections:
            continue
        found = []
        for f in (sec.get("findings") or [])[:MAX_FINDINGS]:
            text = sentence(f.get("text"), 34)
            if not text:
                continue
            sources = valid(f.get("sources", []))
            status = f.get("status") if f.get("status") in STATUSES else "inferred"
            if status == "confirmed" and not sources:
                status = "inferred"  # said to be shown by a document, but cites none
            level = f.get("level") if key == "key_risks" and f.get("level") in LEVELS[:3] else "none"
            found.append({"label": sentence(f.get("label"), 6), "text": text, "status": status, "level": level, "sources": sources,
                          "flags": flags(text)})
        summary = sentence(sec.get("summary"), 34)
        sections[key] = {"key": key, "summary": summary if figures_ok(summary) else "", "findings": found}
    ordered = [{**(sections.get(k) or {"key": k, "summary": "", "findings": []}), "title": title} for k, title, _ in SECTIONS] if sections else []
    return {
        "sections": ordered,
        "business_story": story, "story_flags": flags(story), "revenue_sources": revenue,
        "financial_story": fin, "financial_flags": flags(fin), "events": events,
        "ownership": {"shareholders": holders, "note": sentence(own.get("note"), 30), "sources": valid(own.get("sources", []))},
        "current_accounts": accounts if figures_ok(accounts) else "", "focus_areas": focus, "understood": understood,
    }


def background(job: dict, key: dict, nature: str) -> list[dict]:
    """Company background facts the task card itself gives (AFIT, 21 Nov 2026): never the model's."""
    from .precheck import ENTITY_TYPES

    s = job.get("settings") or {}
    rows = [("Client", job.get("client_name") or ""), ("Task", job.get("title") or ""), ("Group", job.get("group") or ""),
            ("Legal structure", ENTITY_TYPES.get(s.get("entity_type", ""), "")), ("Business nature", nature),
            ("Reporting period", (f"{s['year_start']} to {s['year_end']}" if s.get("year_start") and s.get("year_end") else
                                  f"Year ending {s['year_end']}" if s.get("year_end") else key.get("this_year") or "")),
            ("Location", s.get("location", ""))]
    return [{"label": label, "value": str(value)} for label, value in rows if str(value or "").strip()]


def changes(now: dict, before: dict | None) -> list[str]:
    """What changed in the snapshot's key figures since the task's last pre-check (new documents,
    corrections), in plain words. [] for the first one, or when nothing moved."""
    if not before or not (before.get("figures") or {}).get("available") or not now.get("available"):
        return []
    old = {k["label"]: k["amount"] for k in before["figures"].get("kpis", [])}
    out = []
    for k in now.get("kpis", []):
        if k["label"] in old and abs(old[k["label"]] - k["amount"]) >= 1:
            out.append(f"{k['label']} is now {k['amount']:,.0f} (was {old[k['label']]:,.0f} in the last pre-check).")
    old_this = before["figures"].get("this_year")
    new_this = now.get("this_year")
    if new_this and not old_this:
        out.append("This year's general ledger has been read for the first time.")
    return out[:5]


def assemble(cleaned: dict | None, figs: dict, view, previous: dict | None) -> dict:
    """The snapshot as the task card shows it: the figures with a source to open, the model's words
    with their sources, and what changed since the last pre-check."""
    def line(r: dict) -> dict:
        return {"label": r["label"], "amount": r["amount"], "comparative": r["comparative"], "source": view(r)}

    out_figs = {k: v for k, v in figs.items()}
    if figs.get("available"):
        for key in ("income", "expenses"):
            out_figs[key] = [line(r) for r in figs[key]]
        for key in ("asset_mix", "funding_mix"):
            out_figs[key] = [{**{k: v for k, v in g.items() if k != "lines"}, "lines": [line(r) for r in g["lines"]]} for g in figs[key]]
        out_figs["current_accounts"] = [{**line(r), "direction": r["direction"]} for r in figs["current_accounts"]]
    words = cleaned or {}
    snapshot = {"figures": out_figs, **words, "written": bool(cleaned)}
    snapshot["changes"] = changes(out_figs, previous)
    return snapshot
