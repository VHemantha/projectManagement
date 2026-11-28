"""The cash flow statement's comparatives (AFIT, 27-28 Nov 2026): last year's statement of cash flows as printed (read
with last year's financial statements) set against this year's lines.

Last year's wording rarely matches this year's ("Real estate stock" for inventories, "Payable", "Less - Tax Paid",
"Office Equipment Purchases", "Profit/(Loss) for the year before the taxation"), so each line is first put in a group
by what it is - profit before tax, depreciation, inventories, payables, tax paid, PPE purchases, the shareholder's
current account, a section's total, the net change, cash at the start and end of the year, ... - and matched within
its section by group. Several of last year's lines in one group are added together. A line no group fits is matched
by its wording. Last year's lines with nothing this year come in before their section's total, with Nil for this year.
A line of this year's that last year's statement doesn't show is Nil last year (the statement was read in full).
"""
import difflib
import re
from decimal import Decimal

ZERO = Decimal("0")

HEADS = {"operating activities": "operating", "cash flows from operating activities": "operating",
         "investing activities": "investing", "cash flows from investing activities": "investing",
         "financing activities": "financing", "cash flows from financing activities": "financing",
         "movement in cash and cash equivalents": "cash"}

# (group, pattern) - the first that matches wins, so the narrower come first.
GROUPS = [
    ("start", r"\b(start|beginning|opening|brought forward)\b"),
    ("end", r"\b(end of|closing|carried forward)\b|^at end"),
    ("total", r"\bnet cash\b|^total\b"),
    ("net_change", r"(increase|decrease)[^a-z]*(/|or)?[^a-z]*(\(?(increase|decrease)\)?)?[^a-z]*in cash|net change in cash"),
    ("generated", r"cash generated from operations|operating profit before working capital"),
    ("pbt", r"(profit|loss).{0,40}before.{0,10}tax"),
    ("depreciation", r"depreciation|amortis|amortiz"),
    ("interest_income", r"interest (income|received)"),
    ("interest_paid", r"interest paid"),
    ("finance_costs", r"finance (cost|charge|expense)|interest expense"),
    ("tax_paid", r"\btax(ation)? paid|tax payment|paid.{0,10}tax"),
    ("inventories", r"inventor|\bstocks?\b|work in progress"),
    ("receivables", r"receivable|debtor|prepayment"),
    ("other_current_assets", r"other current asset"),
    ("other_current_liabilities", r"other current liabilit"),
    ("payables", r"payable|creditor|accru"),
    ("deposits", r"deposit"),
    ("intangibles", r"intangible|software"),
    ("investments", r"investment"),
    ("disposal", r"(proceeds|sale|disposal).{0,40}(property|plant|equipment|vehicle|asset|machinery|building)"),
    ("ppe", r"property|plant|equipment|vehicle|furniture|computer|fixed asset|machinery|building|\bppe\b"),
    ("share_issue", r"issue of shares|share capital|stated capital|proceeds.{0,20}shares"),
    ("shareholder", r"sh?a?r?e?holder|shreholder|director'?s? (current|loan)|proprietor|partners?'? current|owner"),
    ("borrowings", r"\bloans?\b|borrowing|overdraft|lease"),
    ("dividends", r"dividend|drawing"),
]
_COMPILED = [(g, re.compile(p, re.I)) for g, p in GROUPS]


def group_of(label: str, section: str = "") -> str:
    low = " ".join((label or "").lower().split())
    if section == "cash" and low in ("increase", "decrease"):
        return "net_change"
    for g, p in _COMPILED:
        if p.search(low):
            return g
    return ""


def _d(v) -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "") else ZERO
    except Exception:  # noqa: BLE001 - an unreadable figure counts as nothing
        return ZERO


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (text or "").lower()).split())


def annotate(rows: list[dict], prior: list[dict], fallback: dict | None = None) -> list[dict]:
    """rows: this year's lines in order, {"label", "kind" (head | blank | sub | grand | line), "sec"? }. Returns them
    with "py" (last year) set, and last year's unmatched lines added ({"label", "cy": 0, "py", "prior_only": True}).
    fallback: {"pbt", "end"} - last year's profit before tax and closing cash from the trial balance, when the
    statement as read doesn't give them."""
    fallback = fallback or {}
    pool = []
    for i, x in enumerate(prior):
        sec = (x.get("section") or "").lower()
        g = group_of(x.get("label", ""), sec)
        if g in ("start", "end", "net_change"):
            sec = "cash"
        pool.append({"i": i, "section": sec, "group": g, "label": x.get("label", ""), "amount": _d(x.get("amount"))})
    used: set[int] = set()

    def first(pred, reuse=False):
        hit = next((p for p in pool if (reuse or p["i"] not in used) and pred(p)), None)
        if hit:
            used.add(hit["i"])
        return hit

    out, sec = [], ""
    for row in rows:
        row = dict(row)
        kind, label = row.get("kind", "line"), row.get("label", "")
        if kind == "head":
            sec = row.get("sec") or HEADS.get(label.lower(), sec)
        if kind in ("head", "blank"):
            out.append(row)
            continue
        sec = row.get("sec") or sec
        g = group_of(label, sec)
        if label.lower().startswith("net cash") or (kind == "sub" and sec in ("operating", "investing", "financing")
                                                    and g not in ("generated", "net_change", "start", "end")):
            g = "total"
        py = None
        if g in ("start", "end"):
            hit = first(lambda p: p["group"] == g)
            py = hit["amount"] if hit else None
        elif g == "net_change":
            hit = first(lambda p: p["group"] == "net_change") or first(lambda p: p["group"] == "net_change", reuse=True)
            py = hit["amount"] if hit else None
        elif g == "total":
            hit = first(lambda p: p["group"] == "total" and p["section"] == sec) or first(lambda p: p["group"] == "total" and not p["section"])
            py = hit["amount"] if hit else None
        elif g:
            hits = [p for p in pool if p["i"] not in used and p["group"] == g and p["section"] in (sec, "")] or \
                [p for p in pool if p["i"] not in used and p["group"] == g and p["section"] not in ("cash",) and g not in ("generated",)]
            if hits:
                used.update(p["i"] for p in hits)
                py = sum((p["amount"] for p in hits), ZERO)
        else:
            norm = _norm(label)
            cands = [p for p in pool if p["i"] not in used and not p["group"] and p["section"] in (sec, "")]
            best = max(cands, key=lambda p: difflib.SequenceMatcher(None, norm, _norm(p["label"])).ratio(), default=None)
            if best and difflib.SequenceMatcher(None, norm, _norm(best["label"])).ratio() >= 0.6:
                used.add(best["i"])
                py = best["amount"]
        if py is None and g == "pbt" and fallback.get("pbt") is not None:
            py = _d(fallback["pbt"])
        if py is None and g == "end" and fallback.get("end") is not None:
            py = _d(fallback["end"])
        row["py"] = ZERO if py is None else py
        if g == "total":  # last year's lines with nothing this year go in before the section's total
            for p in pool:
                if p["i"] not in used and p["section"] == sec and p["group"] not in ("total", "start", "end", "net_change", "generated"):
                    used.add(p["i"])
                    out.append({"label": p["label"], "cy": ZERO, "py": p["amount"], "prior_only": True, "sec": sec})
        out.append(row)
    return out


def with_comparatives(cf: dict, prior: list[dict], fallback: dict | None = None, source: str = "") -> dict:
    """The statement of cash flows as the web page shows it (engine/depth.cash_flows), with last year's figure on
    each line ("comparative"), the totals and the cash balances; last year's lines with nothing this year are added to
    their section (amount 0, "prior_only")."""
    if not cf or not cf.get("available") or not prior:
        return cf
    cf = {**cf, "sections": [dict(s, rows=[dict(r) for r in s["rows"]], after=[dict(r) for r in s.get("after") or []]) for s in cf["sections"]]}
    flat = []
    for s in cf["sections"]:
        flat.append({"label": s["title"], "kind": "head", "sec": s["key"]})
        flat += [{"label": r["label"], "kind": "line", "ref": (s["key"], "rows", i)} for i, r in enumerate(s["rows"])]
        if s.get("subtotal"):
            flat.append({"label": s["subtotal"]["label"], "kind": "line", "ref": (s["key"], "subtotal", None)})
        flat += [{"label": r["label"], "kind": "line", "ref": (s["key"], "after", i)} for i, r in enumerate(s["after"])]
        flat.append({"label": s["total"]["label"], "kind": "sub", "ref": (s["key"], "total", None)})
    flat += [{"label": "Movement in cash and cash equivalents", "kind": "head", "sec": "cash"},
             {"label": "Net change in cash and cash equivalents", "kind": "line", "ref": ("net_change",)},
             {"label": "At start of year", "kind": "line", "ref": ("opening_cash",)},
             {"label": "At end of year", "kind": "line", "ref": ("closing_cash",)}]
    by_key = {s["key"]: s for s in cf["sections"]}
    for row in annotate(flat, prior, fallback):
        ref = row.get("ref")
        if row.get("prior_only"):
            s = by_key.get(row.get("sec"))
            if s is not None:
                s["rows"].append({"label": row["label"], "amount": ZERO, "note": "", "comparative": row["py"], "prior_only": True})
            continue
        if not ref:
            continue
        if len(ref) == 1:
            cf[f"{ref[0]}_comparative"] = row["py"]
        elif ref[1] in ("rows", "after"):
            by_key[ref[0]][ref[1]][ref[2]]["comparative"] = row["py"]
        else:
            by_key[ref[0]][ref[1]] = {**by_key[ref[0]][ref[1]], "comparative": row["py"]}
    cf["has_comparative"] = True
    cf["comparative_source"] = source
    return cf
