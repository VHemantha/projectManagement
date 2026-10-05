"""Facts code can work out from the figures, for the pre-check — no model.

- last year's lines, from last year's trial balance (or, failing that, its signed statements);
- each bank export of this year: period covered, opening and closing balance, money in and
  out, totals by payer and payee;
- checks with a right answer: this year's opening bank balance equals last year's closing
  balance, and the bank data covers the whole year.

The pre-check model reads these as compact, numbered lines; every amount it may use comes from here.
"""
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from .config import Settings
from .periods import period_end
from .rules import _block_for, _col, _header, _is_total, _name_of
from .textutil import to_number

MAX_LINES = 40
MAX_COUNTERPARTIES = 12

SECTION_OF_TYPE = [
    (r"revenue|income|sales|other income", "Income"),
    (r"expense|overhead|direct cost|cost of sales|depreciation", "Expenses"),
    (r"bank|current asset|fixed asset|non-current asset|inventory|prepayment|asset", "Assets"),
    (r"liabilit|payable|loan|gst|tax", "Liabilities"),
    (r"equity|capital|retained|reserve|shareholder|drawings", "Equity"),
]
_HEADING = re.compile(r"^(trading income|income|revenue|other income|expenses?|administrative expenses|standing charges|"
                      r"current assets|non-current assets|fixed assets|assets|current liabilities|non-current liabilities|"
                      r"liabilities|equity|shareholders'? equity)$", re.I)
_NUM = r"(?:[-–]|\(?-?\$?[\d,]+(?:\.\d+)?\)?)"
_FS_LINE = re.compile(rf"^(?P<label>[A-Za-z][A-Za-z0-9&'’/(),. -]*?[A-Za-z)])\s+(?P<nums>{_NUM}(?:\s+{_NUM}){{0,5}})$")
_ACCOUNT_NO = re.compile(r"(?<!\d)\d{2}-\d{4}-\d{7}-\d{2,3}(?!\d)")  # NZ bank account; "_" may follow it in a file name

# --- last year's lines ---------------------------------------------------------------------

def _section(text: str) -> str:
    for pattern, section in SECTION_OF_TYPE:
        if re.search(pattern, text, re.I):
            return section
    return ""


def tb_lines(doc: dict) -> list[dict]:
    """Account lines of a trial balance: label, section (from the account-type column when there
    is one), this year's balance (debit minus credit) and the comparative column if present."""
    out = []
    for table in doc["parsed"]["tables"]:
        found = _header(table)
        if not found:
            continue
        h_index, header = found
        dr = _col(header, r"^debit", r"^dr\b")
        cr = _col(header, r"^credit", r"^cr\b")
        bal = _col(header, r"balance|amount|current year|^cy\b|this year|ytd|year to date") if dr is None or cr is None else None
        if (dr is None or cr is None) and bal is None:
            continue
        typ = _col(header, r"account type|^type$|^class$")
        code = _col(header, r"^(account )?code$|^no\.?$|^number$")
        prior = next((i for i, cell in enumerate(header) if i not in (dr, cr, bal, typ, code) and (
            re.search(r"prior|previous|last year|^py\b|comparative", cell) or re.fullmatch(r"\d{1,2}\s*[a-z]{3,9}\s*20\d\d|20\d\d|fy\s*\d{2,4}", cell))), None)
        skip = {i for i in (dr, cr, bal, prior, typ, code) if i is not None}
        for row_no, cells in table["rows"][h_index + 1:]:
            get = lambda i: to_number(cells[i]) if i is not None and i < len(cells) else None  # noqa: E731
            label = _name_of(cells, skip)
            if not label or _is_total(label):
                continue
            if dr is not None and cr is not None:
                amount = (get(dr) or 0.0) - (get(cr) or 0.0)
            else:
                amount = get(bal) or 0.0
            kind = str(cells[typ]).strip() if typ is not None and typ < len(cells) and cells[typ] is not None else ""
            out.append({
                "label": label, "section": _section(kind) or _section(label), "type": kind, "amount": round(amount, 2),
                "comparative": None if get(prior) is None else round(get(prior), 2),
                "file": doc["file"], "block": _block_for(doc["parsed"], table["name"], row_no),
            })
    return out


def _fs_number(token: str) -> float:
    if token in ("-", "–"):
        return 0.0
    return to_number(token.replace("$", "")) or 0.0


def statement_lines(doc: dict) -> list[dict]:
    """Lines of financial statements read as text: "Insurance 1,255 1,255" -> this year 1,255,
    comparative 1,255. Section from the headings seen above the line."""
    out, seen, section = [], set(), ""
    for block in doc["parsed"]["blocks"]:
        text = block["text"].strip()
        if _HEADING.match(text):
            section = _section(text) or section
            continue
        m = _FS_LINE.match(text)
        if not m:
            continue
        label = m.group("label").strip(" .")
        nums = [_fs_number(t) for t in m.group("nums").split()]
        if _is_total(label) or label.lower() in seen or re.fullmatch(r"(page|note|notes)\b.*", label.lower()) or len(label) < 3:
            continue
        seen.add(label.lower())
        out.append({"label": label, "section": section or _section(label), "type": "", "amount": nums[0],
                    "comparative": nums[1] if len(nums) > 1 else None, "file": doc["file"], "block": block})
    return out


def prior_year_lines(prior_docs: list[dict], settings: Settings) -> tuple[list[dict], list[dict]]:
    """(material lines of last year's accounts, the documents they came from). A trial balance
    is preferred (one line per account, exact figures); signed statements are used without one."""
    tbs = [d for d in prior_docs if d["file"]["document_class"] == "trial_balance"]
    lines, sources = [], []
    for d in tbs:
        found = tb_lines(d)
        if len(found) >= 3:
            lines, sources = found, [d]
            break
    if not lines:
        for d in prior_docs:
            if d["file"]["document_class"] in ("financial_statements", "prior_year_statements"):
                found = statement_lines(d)
                if len(found) > len(lines):
                    lines, sources = found, [d]
    material = [ln for ln in lines if abs(ln["amount"]) >= settings.analysis_min_amount]
    material.sort(key=lambda ln: (["Income", "Expenses", "Assets", "Liabilities", "Equity", ""].index(ln["section"]), -abs(ln["amount"])))
    return material[:MAX_LINES], sources


# --- this year's material --------------------------------------------------------------------

def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text[:19] if fmt.startswith("%Y-%m-%d %H") else text, fmt).date()
        except ValueError:
            continue
    return None


def bank_exports(doc: dict) -> list[dict]:
    """A table with a date, an amount and (ideally) a running balance is a bank export."""
    out = []
    for table in doc["parsed"]["tables"]:
        rows = table["rows"]
        for h, (_, cells) in enumerate(rows[:10]):
            header = [str(c or "").strip().lower() for c in cells]
            d_col = next((i for i, c in enumerate(header) if "date" in c), None)
            a_col = next((i for i, c in enumerate(header) if c == "amount" or c.startswith("amount")), None)
            if d_col is None or a_col is None:
                continue
            b_col = next((i for i, c in enumerate(header) if c == "balance" or c.startswith("balance")), None)
            who = [i for i, c in enumerate(header) if re.search(r"details|payee|description|particulars|name|reference|narrative", c)]
            typ = next((i for i, c in enumerate(header) if c in ("type", "transaction type")), None)
            txns = []
            for row_no, r in rows[h + 1:]:
                when = _as_date(r[d_col]) if d_col < len(r) else None
                amount = to_number(r[a_col]) if a_col < len(r) else None
                if when is None or amount is None:
                    continue
                parts = [str(r[i]).strip() for i in who[:2] if i < len(r) and r[i] not in (None, "")]
                txns.append({"row": row_no, "date": when, "amount": float(amount),
                             "balance": to_number(r[b_col]) if b_col is not None and b_col < len(r) else None,
                             "who": " / ".join(parts) or "(no details)", "type": str(r[typ]).strip() if typ is not None and typ < len(r) and r[typ] else ""})
            if len(txns) < 3:
                continue
            descending = txns[0]["date"] > txns[-1]["date"]
            first, last = (txns[-1], txns[0]) if descending else (txns[0], txns[-1])
            account = _ACCOUNT_NO.search(doc["file"]["name"]) or _ACCOUNT_NO.search(" ".join(str(c) for _, r in rows[:5] for c in r))
            out.append({
                "file": doc["file"], "parsed": doc["parsed"], "table": table["name"], "account": account.group(0) if account else "",
                "from": min(t["date"] for t in txns), "to": max(t["date"] for t in txns), "count": len(txns),
                "opening": None if first["balance"] is None else round(first["balance"] - first["amount"], 2),
                "opening_row": first["row"], "closing": last["balance"], "closing_row": last["row"],
                "money_in": round(sum(t["amount"] for t in txns if t["amount"] > 0), 2),
                "money_out": round(-sum(t["amount"] for t in txns if t["amount"] < 0), 2),
                "txns": txns,
            })
            break
    return out


def counterparties(export: dict) -> list[dict]:
    groups: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0, "rows": [], "type": ""})
    for t in export["txns"]:
        key = re.sub(r"\s+", " ", t["who"]).strip()[:60]
        g = groups[key]
        g["total"] += t["amount"]
        g["count"] += 1
        g["rows"].append(t["row"])
        g["type"] = g["type"] or t["type"]
    ranked = sorted(groups.items(), key=lambda kv: -abs(kv[1]["total"]))[:MAX_COUNTERPARTIES]
    return [{"name": k, "total": round(v["total"], 2), "count": v["count"], "type": v["type"], "rows": v["rows"]} for k, v in ranked]


# --- checks with a right answer -------------------------------------------------------------------

def _closing_in_prior(prior_docs: list[dict], account: str) -> tuple[float, dict, dict] | None:
    """Last year's closing balance for a bank account, from a prior-year document that names the
    account number and states a closing balance."""
    if not account:
        return None
    for d in prior_docs:
        blocks = d["parsed"]["blocks"]
        if not any(account in b["text"] for b in blocks):
            continue
        for b in blocks:
            m = re.search(r"closing balance\s*\$?(-?[\d,]+\.\d\d)", b["text"], re.I)
            if m:
                return to_number(m.group(1)), d["file"], b
    return None


def _prior_bank_line(prior_lines: list[dict]) -> dict | None:
    banks = [ln for ln in prior_lines if re.search(r"\bbank\b|current account|cheque|savings", f"{ln['label']} {ln['type']}", re.I)
             and not re.search(r"charge|fee|interest|loan", ln["label"], re.I)]
    return banks[0] if len(banks) == 1 else None


def year_bounds(prior_docs: list[dict], current: int | None) -> tuple[date | None, date | None]:
    """This year's start and end, from the period stated in last year's statements."""
    for d in prior_docs:
        end = period_end(" ".join(b["text"] for b in d["parsed"]["blocks"][:40]))
        if end:
            try:
                this_end = end.replace(year=end.year + 1)
            except ValueError:  # 29 February
                this_end = end + timedelta(days=365)
            return end + timedelta(days=1), this_end
    if current:
        return date(current - 1, 4, 1), date(current, 3, 31)
    return None, None


def run_checks(exports: list[dict], prior_docs: list[dict], prior_lines: list[dict], start: date | None, end: date | None,
               today: date) -> list[dict]:
    checks = []
    bank_line = _prior_bank_line(prior_lines)
    for e in exports:
        where = e["account"] or e["file"]["name"]
        # 1. Opening balance this year = closing balance last year.
        prior = _closing_in_prior(prior_docs, e["account"])
        if prior is None and bank_line and len(exports) == 1:
            prior = (bank_line["amount"], bank_line["file"], bank_line["block"])
        if prior is not None and e["opening"] is not None:
            value, pfile, pblock = prior
            ok = abs(e["opening"] - value) <= 1.0
            checks.append({
                "id": f"opening:{where}", "label": "This year's opening bank balance equals last year's closing balance", "passed": ok,
                "detail": f"{where}: opening {_fmt(e['opening'])} this year, closing {_fmt(value)} last year"
                          + ("" if ok else f", a difference of {_fmt(abs(e['opening'] - value))}") + ".",
                "evidence": [(e["file"], _block_for(e["parsed"], e["table"], e["opening_row"])), (pfile, pblock)],
            })
        # 2. The bank data covers the whole year.
        if start and end:
            due_end = min(end, today - timedelta(days=31))
            gaps = []
            if e["from"] > start + timedelta(days=10):
                gaps.append(f"starts {e['from']:%d %b %Y}, after the year began on {start:%d %b %Y}")
            if e["to"] < due_end - timedelta(days=10):
                gaps.append(f"ends {e['to']:%d %b %Y}, before {due_end:%d %b %Y}")
            checks.append({
                "id": f"coverage:{where}", "label": "Bank data covers the whole year", "passed": not gaps,
                "detail": f"{where}: transactions {e['from']:%d %b %Y} to {e['to']:%d %b %Y}" + (f" ({'; '.join(gaps)})" if gaps else "") + ".",
                "evidence": [(e["file"], _block_for(e["parsed"], e["table"], e["closing_row"]))],
            })
    return checks


def _fmt(n: float) -> str:
    return f"{n:,.2f}"


# --- putting it together ---------------------------------------------------------------------------

def prepare(prior_docs: list[dict], current_docs: list[dict], periods: dict, settings: Settings, today: date | None = None) -> dict:
    """Everything code works out for the pre-check. prior_docs are last year's documents (its
    statements, trial balance and workpapers), current_docs what arrived for this year; both
    {"file", "parsed"}."""
    today = today or date.today()
    prior_lines, sources = prior_year_lines(prior_docs, settings) if prior_docs else ([], [])
    all_prior_lines = []
    if sources:  # every line of last year's trial balance (or statements), not only the material ones
        src = sources[0]
        all_prior_lines = tb_lines(src) if src["file"]["document_class"] == "trial_balance" else statement_lines(src)
    exports = [e for d in current_docs for e in bank_exports(d)]
    start, end = year_bounds(prior_docs or sources, periods.get("current"))
    checks = run_checks(exports, prior_docs, all_prior_lines or prior_lines, start, end, today)
    return {"prior_lines": prior_lines, "all_prior_lines": all_prior_lines, "sources": sources,
            "exports": exports, "checks": checks, "start": start, "end": end}
