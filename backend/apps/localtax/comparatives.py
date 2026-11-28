"""Comparatives from last year's financial statements (AFIT, 24 Nov 2026).

Local_Tax_AI reads the prior year's statements (from a Google Drive link or an upload) into lines. Each line has the
text as printed, the amount for that year, and the FS heading it belongs to. The steps:
- Code proposes the trial balance account for each line: the same name, a close name under the same heading, or the
  only account under that heading. A line with no match is offered as a new account.
- The accountant confirms or changes each match.
- The confirmed amounts become the trial balance's prior-year column, signed the trial balance's way (debit +).
- The PPE note's closing cost and accumulated depreciation by class become the depreciation schedule's opening
  balances.

Retained earnings: the trial balance's prior-year retained earnings is the balance before that year's profit, the
statements show it after. So the prior-year profit worked out from the confirmed lines is taken off.
"""
import difflib
import re
from decimal import Decimal, InvalidOperation

from .engine import depreciation as DEP
from .engine import fs as FS

ZERO = Decimal("0")
PPE_NOTE = "ppe_note"
CASH_FLOW = "cash_flow"  # last year's statement of cash flows: this year's cash flow comparatives (27 Nov 2026)
CF_SECTIONS = ("operating", "investing", "financing", "cash")
TAX_REC = "tax_reconciliation"  # last year's reconciliation of the tax expense to the accounting profit (28 Nov 2026)


def _norm(s: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", (s or "").lower().replace("&", " and ")).split())


def _amount(v) -> Decimal | None:
    try:
        return Decimal(str(v).replace(",", "")) if str(v or "").strip() else None
    except InvalidOperation:
        return None


def tb_amount(heading: str, presented: Decimal) -> Decimal:
    """A presented amount, signed the trial balance's way: income, equity and liabilities are credits; an expense
    is a debit however it is printed; an asset keeps its printed sign (accumulated depreciation is printed in
    brackets)."""
    kind = FS.HEADINGS.get(heading, ("", "", "asset"))[2]
    if kind in ("income", "equity", "liability"):
        return -presented
    if kind == "expense":
        return abs(presented)
    return presented


def propose(lines: list[dict], tb: list[dict]) -> list[dict]:
    """For each line read: the proposed action ("match" with a TB code, "new" account, "ppe" for the PPE note, or
    "ignore") and its heading."""
    accounts = [{"code": str(t["code"]), "norm": _norm(t["name"]), "heading": t.get("heading") or ""} for t in tb]
    out = []
    for i, ln in enumerate(lines):
        if _amount(ln.get("amount")) is None:
            out.append({"index": i, "action": "ignore", "code": "", "heading": "", "why": "No amount."})
            continue
        cat = str(ln.get("category") or "")
        if cat.startswith(PPE_NOTE):
            out.append({"index": i, "action": "ppe", "code": "", "heading": "ppe", "why": "PPE note: the opening balances for depreciation."})
            continue
        if cat == TAX_REC:
            out.append({"index": i, "action": "tax_rec", "code": "", "heading": "", "why": "Tax reconciliation: this year's comparatives."})
            continue
        if cat == CASH_FLOW:
            out.append({"index": i, "action": "cash_flow", "code": "", "heading": "", "why": "Cash flow statement: this year's cash flow comparatives."})
            continue
        heading = cat if cat in FS.HEADINGS else FS.suggest_heading(ln.get("description") or "")
        n = _norm(ln.get("description") or "")
        code, why = "", ""
        exact = [a for a in accounts if a["norm"] == n]
        if exact:
            code, why = exact[0]["code"], "Same name."
        else:
            pool = [a for a in accounts if a["heading"] == heading] or accounts
            close = difflib.get_close_matches(n, [a["norm"] for a in pool], n=1, cutoff=0.72)
            if close:
                code, why = next(a["code"] for a in pool if a["norm"] == close[0]), "A close name."
        out.append({"index": i, "action": "match" if code else "new", "code": code, "heading": heading, "why": why or "No account of that name."})
    # a heading with one account in the TB and one unmatched line in the statements: the same thing
    for h in {p["heading"] for p in out if p["action"] == "new"}:
        tb_h = [a for a in accounts if a["heading"] == h]
        lines_h = [p for p in out if p["heading"] == h and p["action"] in ("new", "match")]
        if len(tb_h) == 1 and len(lines_h) == 1 and lines_h[0]["action"] == "new":
            lines_h[0].update(action="match", code=tb_h[0]["code"], why="The only account under this heading.")
    return out


def apply(lines: list[dict], mapping: list[dict], tb_lines, policy: list[dict]) -> dict:
    """The confirmed mapping applied: {"comparatives": {code: amount}, "new": [{code, name, heading, comparative}],
    "opening": {category: {cost, accumulated}}, "cash_flow": [{section, label, amount}], "notes": [...]}. Nothing is saved here."""
    by_index = {int(m.get("index", -1)): m for m in mapping if isinstance(m, dict)}
    codes = {str(t.code): t for t in tb_lines}
    comps: dict[str, Decimal] = {}
    new, opening, notes, used_new, cash_flow = [], {}, [], set(), []
    nature: dict[str, str] = {}  # revenue account -> its nature as last year's statements describe it
    tax_rec: list[dict] = []
    new_categories: list[dict] = []  # PPE classes of last year's statements the policy doesn't have
    prior_labels: dict[str, str] = {}  # category -> its name in last year's PPE note
    for i, ln in enumerate(lines):
        m = by_index.get(i) or {}
        action = m.get("action")
        amount = _amount(ln.get("amount"))
        if amount is None or action in (None, "ignore"):
            continue
        if action == "ppe":
            label, _, part = (ln.get("description") or "").partition("|")
            label = " ".join(label.split())
            cat = m.get("category") or DEP.category_of(label, policy)
            if not cat and label:
                # A class last year's statements have and the policy doesn't: it becomes one of the client's categories,
                # under last year's name (its rate is for the accountant to set) - AFIT, 28 Nov 2026.
                cat = "_".join(re.sub(r"[^a-z0-9 ]", " ", label.lower()).split())[:40] or "other"
                if cat not in {c["key"] for c in policy} and cat not in {c["key"] for c in new_categories}:
                    new_categories.append({"key": cat, "label": label[:80]})
            if not cat:
                notes.append(f"PPE note line “{ln.get('description')}”: no category - not used.")
                continue
            if label:
                prior_labels.setdefault(cat, label[:80])
            row = opening.setdefault(cat, {"cost": ZERO, "accumulated": ZERO})
            row["accumulated" if re.search(r"accum|depreciation", part or label, re.I) else "cost"] += abs(amount)
            continue
        if action == "tax_rec":
            tax_rec.append({"label": " ".join((ln.get("description") or "").split())[:200], "amount": amount})
            continue
        if action == "cash_flow":
            section, _, label = (ln.get("description") or "").partition("|")
            section = section.strip().lower()
            if not label.strip() or section not in CF_SECTIONS:
                section, label = "", ln.get("description") or ""
            cash_flow.append({"section": section, "label": label.strip()[:200], "amount": amount})
            continue
        heading = m.get("heading") if m.get("heading") in FS.HEADINGS else ""
        if action == "match":
            code = str(m.get("code") or "")
            if code not in codes:
                notes.append(f"“{ln.get('description')}”: account {code} is not in the trial balance - not used.")
                continue
            comps[code] = comps.get(code, ZERO) + tb_amount(heading or codes[code].heading, amount)
            if (heading or codes[code].heading) == "revenue":
                nature[code] = " ".join((ln.get("description") or "").split())[:120]
        elif action == "new":
            if not heading:
                notes.append(f"“{ln.get('description')}”: choose its heading to add it as an account - not used.")
                continue
            code = str(m.get("code") or "").strip()[:40] or f"PY-{i + 1:03d}"
            while code in codes or code in used_new:
                code += "A"
            used_new.add(code)
            new.append({"code": code, "name": (ln.get("description") or code)[:200], "heading": heading, "comparative": tb_amount(heading, amount)})
            if heading == "revenue":
                nature[code] = " ".join((ln.get("description") or "").split())[:120]
    # retained earnings: the balance before the prior year's profit (see the module's note)
    headings = {c: t.heading for c, t in codes.items()} | {n["code"]: n["heading"] for n in new}
    pl = sum((v for c, v in comps.items() if FS.HEADINGS.get(headings.get(c, ""), ("",))[0] == "pl"), ZERO)
    pl += sum((n["comparative"] for n in new if FS.HEADINGS[n["heading"]][0] == "pl"), ZERO)
    prior_profit = -pl
    re_codes = [c for c in comps if headings.get(c) == "retained_earnings"]
    if re_codes and prior_profit:
        comps[re_codes[0]] += prior_profit
        notes.append(f"Retained earnings: the prior year's profit of {prior_profit:,.2f} is taken off the closing balance shown, as the trial "
                     "balance holds the balance before that year's profit.")
    return {"comparatives": comps, "new": new, "opening": opening, "cash_flow": cash_flow, "revenue_nature": nature, "tax_rec": tax_rec,
            "ppe_categories": {"new": new_categories, "labels": prior_labels}, "notes": notes}


def file_id_from(link: str) -> str:
    """A Google Drive file id from a pasted link (…/file/d/<id>/…, …?id=<id>) or the id itself."""
    link = (link or "").strip()
    m = re.search(r"/(?:file|document|spreadsheets|presentation)/d/([A-Za-z0-9_-]{10,})", link) or re.search(r"[?&]id=([A-Za-z0-9_-]{10,})", link)
    if m:
        return m.group(1)
    return link if re.fullmatch(r"[A-Za-z0-9_-]{20,}", link) else ""
