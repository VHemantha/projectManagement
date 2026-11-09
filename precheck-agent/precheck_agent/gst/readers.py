"""Documents into records. A table (Excel or CSV) is read by code: the heading row is found and each
column mapped from the names Xero, IRD and the firm's workpapers use; only a table code cannot map
goes to the model for its mapping, and the rows are still read by code. A PDF or a document is read
by the model (gst-document-reading skill) into the same records. Every record keeps its source.
Amounts are Decimals as the document gives them; signs are converted later, in the engine."""
import re
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .money import amount, day
from .sources import Source

# field -> heading names (normalised), most specific first.
FIELDS = {
    "ageing": {
        "contact": ["contact", "customer", "supplier", "client", "name", "debtor", "creditor"],
        "ref": ["invoice number", "invoice no", "invoice #", "bill number", "reference", "invoice", "number", "ref", "inv no", "document"],
        "date": ["invoice date", "date", "issue date", "transaction date"],
        "due": ["due date"],
        "total": ["total", "amount due", "outstanding", "balance", "total due", "amount outstanding", "total outstanding"],
        "gst": ["gst", "tax", "gst amount", "tax amount", "gst on outstanding", "gst outstanding", "gst (nzd)", "tax (nzd)"],
    },
    "general_ledger": {
        "date": ["date", "transaction date"],
        "account": ["account", "account name"],
        "code": ["account code", "code"],
        "source_type": ["source", "source type", "transaction type", "type"],
        "contact": ["contact", "name", "payee", "contact name"],
        "description": ["description", "details", "narration", "particulars", "memo", "transaction"],
        "ref": ["reference", "ref", "invoice number", "transaction ref", "number", "journal number"],
        "debit": ["debit", "debits", "dr", "debit (nzd)"],
        "credit": ["credit", "credits", "cr", "credit (nzd)"],
        "amount": ["amount", "net", "net amount", "value"],
        "gross": ["gross", "gross amount"],
        "gst": ["gst", "tax", "gst amount", "tax amount", "gst (nzd)"],
        "tax_code": ["tax rate", "tax code", "gst rate", "tax type", "tax rate name", "gst code"],
    },
    "trial_balance": {
        "code": ["account code", "code"],
        "account": ["account", "account name", "description"],
        "debit": ["debit year to date", "ytd debit", "debit ytd", "debit", "dr"],
        "credit": ["credit year to date", "ytd credit", "credit ytd", "credit", "cr"],
        "balance": ["balance", "closing balance", "ytd", "year to date", "net", "amount"],
    },
    "journal_report": {
        "journal": ["journal number", "journal #", "journal no", "journal", "journal id", "transaction id"],
        "date": ["effective date", "journal date", "date"],
        "created": ["created", "created date", "date created", "created on", "entered", "date entered", "posted", "posted date"],
        "modified": ["modified", "last modified", "updated", "date modified", "changed"],
        "account": ["account", "account name"],
        "code": ["account code", "code"],
        "description": ["narration", "description", "details", "memo"],
        "ref": ["reference", "ref", "source"],
        "debit": ["debit", "dr"],
        "credit": ["credit", "cr"],
        "gst": ["gst", "tax", "gst amount", "tax amount"],
    },
    "gst_returns": {
        "period_end": ["period end", "period ended", "period ending", "period to", "to", "return period", "period"],
        "period_start": ["period start", "period from", "from"],
        "version": ["version", "return version", "amended"],
        "filed": ["date filed", "filed date", "filed", "finalised", "date finalised", "submitted", "date submitted"],
        "box5": ["box 5", "total sales and income", "total sales"],
        "box6": ["box 6", "zero rated supplies", "zero rated", "zero-rated"],
        "box8": ["box 8", "output tax", "output gst", "gst on sales", "gst on income", "gst collected on sales and income"],
        "box9": ["box 9", "debit adjustments", "adjustments to output"],
        "box10": ["box 10", "total gst collected"],
        "box11": ["box 11", "total purchases and expenses", "total purchases", "purchases and expenses"],
        "box12": ["box 12", "input tax", "input gst", "gst on purchases", "gst on purchases and expenses"],
        "box13": ["box 13", "credit adjustments"],
        "box14": ["box 14", "total gst credit"],
        "box15": ["box 15", "gst to pay", "net gst", "gst payable", "gst to pay or refund", "amount payable", "net", "difference"],
    },
    "ird_statement": {
        "date": ["date", "transaction date", "processed", "date processed"],
        "effective": ["effective date", "effective"],
        "type": ["transaction type", "type", "transaction", "description", "details", "item"],
        "period": ["period end", "period", "return period", "gst period", "for period"],
        "debit": ["debit", "dr", "debits"],
        "credit": ["credit", "cr", "credits"],
        "amount": ["amount"],
        "reference": ["reference", "ref", "payment reference"],
        "balance": ["balance", "running balance", "account balance"],
    },
    "late_claims": {
        "date": ["transaction date", "invoice date", "date"],
        "ref": ["reference", "invoice number", "ref", "number", "invoice"],
        "contact": ["contact", "name", "customer", "supplier"],
        "description": ["description", "details", "narration"],
        "gst": ["gst", "tax", "gst amount", "tax amount"],
        "side": ["sales or purchases", "type", "box", "category", "account type", "source"],
        "return_period": ["included in return", "return period", "filed in", "return", "period"],
    },
}
REQUIRED = {
    "ageing": ["total"], "general_ledger": ["date"], "trial_balance": ["account"], "journal_report": ["account"],
    "gst_returns": ["period_end"], "ird_statement": ["date"], "late_claims": ["gst"],
}
# A heading that holds one of these words isn't the plain GST amount ("Total incl GST", "GST rate").
NOT_AN_AMOUNT = ("incl", "excl", "rate", "code", "type", "account", "inclusive", "exclusive", "number")


def norm(text) -> str:
    return " ".join(re.sub(r"[^a-z0-9#/]+", " ", str(text or "").lower()).split())


def _score(heading: str, synonyms: list[str], field_name: str) -> int:
    h = norm(heading)
    if not h:
        return 0
    if field_name in ("gst", "box8", "box12") and any(w in h.split() for w in NOT_AN_AMOUNT):
        return 0
    for rank, syn in enumerate(synonyms):
        if h == syn:
            return 100 - rank
    for rank, syn in enumerate(synonyms):
        if len(syn) > 3 and re.search(rf"\b{re.escape(syn)}\b", h):
            return 50 - rank
    return 0


def map_headings(cells: list, fields: dict[str, list[str]]) -> dict[str, int]:
    """{field: column index} from one row of headings: the best match first, each column used once."""
    options = sorted(((_score(c, syns, f), f, i) for i, c in enumerate(cells) for f, syns in fields.items()), reverse=True)
    out, used = {}, set()
    for score, f, i in options:
        if score and f not in out and i not in used:
            out[f] = i
            used.add(i)
    return out


@dataclass
class Table:
    src: Source
    sheet: str
    header_row: int
    cols: dict[str, int]
    rows: list[tuple[int, list]] = field(default_factory=list)

    def get(self, values: list, name: str):
        i = self.cols.get(name)
        return values[i] if i is not None and i < len(values) else None

    def text(self, values: list, name: str) -> str:
        v = self.get(values, name)
        return "" if v is None else " ".join(str(v).split())

    def ref(self, row: int) -> str:
        return self.src.ref(self.sheet, row)


def find_table(src: Source, kind: str, ai=None) -> Table | None:
    fields, required = FIELDS[kind], REQUIRED[kind]
    best = None
    for sheet in src.sheets:
        for idx, (row_no, values) in enumerate(sheet["rows"][:40]):
            cols = map_headings(values, fields)
            if all(r in cols for r in required) and len(cols) >= 2 and (best is None or len(cols) > len(best[2])):
                best = (sheet, idx, cols)
    if best is None and ai is not None and src.sheets:
        mapped = ai.map_columns(kind, {f: s[0] for f, s in fields.items()}, src)
        sheet = next((s for s in src.sheets if s["name"] == mapped.get("sheet")), src.sheets[0])
        cols = {c["field"]: int(c["column"]) for c in mapped.get("columns", []) if c.get("field") in fields}
        idx = next((i for i, (r, _) in enumerate(sheet["rows"]) if r == mapped.get("header_row")), None)
        if idx is not None and all(r in cols for r in required):
            best = (sheet, idx, cols)
    if best is None:
        return None
    sheet, idx, cols = best
    return Table(src, sheet["name"], sheet["rows"][idx][0], cols, sheet["rows"][idx + 1:])


def _first_text(values: list) -> str:
    return next((" ".join(str(v).split()) for v in values if v not in (None, "") and not isinstance(v, (int, float))), "")


def _is_total(values: list) -> bool:
    return _first_text(values).lower().startswith(("total", "grand total", "closing balance", "net movement"))


def _amounts_in(values: list, t: Table, names) -> bool:
    return any(amount(t.get(values, n)) is not None for n in names)


# --- ageing reports ----------------------------------------------------------------------------------

def read_ageing(src: Source, ai=None) -> dict:
    """{"has_gst_column", "rows": [...], "report_total", "report_gst_total", "how", "problem"}."""
    if src.sheets:
        t = find_table(src, "ageing", ai)
        if t is None:
            return {"has_gst_column": None, "rows": [], "problem": "The ageing report's headings could not be found.", "how": "code"}
        rows, contact, total, gst_total = [], "", None, None
        for row_no, values in t.rows:
            first = _first_text(values)
            if _is_total(values):
                total = amount(t.get(values, "total")) if amount(t.get(values, "total")) is not None else total
                if "gst" in t.cols:
                    gst_total = amount(t.get(values, "gst")) if amount(t.get(values, "gst")) is not None else gst_total
                continue
            tot = amount(t.get(values, "total"))
            if tot is None:
                if first and not _amounts_in(values, t, ["gst"]):
                    contact = first  # a contact heading in a detailed report
                continue
            rows.append({"id": f"{src.sid}:{t.sheet}:{row_no}", "contact": t.text(values, "contact") or contact, "ref": t.text(values, "ref"),
                         "date": day(t.get(values, "date")), "total": tot,
                         "gst": amount(t.get(values, "gst")) if "gst" in t.cols else None, "source": t.ref(row_no)})
        return {"has_gst_column": "gst" in t.cols, "rows": rows, "report_total": total, "report_gst_total": gst_total, "how": "code",
                "heading": [t.sheet, t.header_row]}
    if ai is None:
        return {"has_gst_column": None, "rows": [], "problem": "The report could not be read.", "how": ""}
    got = ai.extract("ageing", src)
    if not got:
        return {"has_gst_column": None, "rows": [], "problem": "The model could not read the report.", "how": "ai"}
    rows = []
    for n, r in enumerate(got.get("rows", []), start=1):
        tot = amount(r.get("total"))
        if tot is None:
            continue
        rows.append({"id": f"{src.sid}:ai:{n}", "contact": r.get("contact", ""), "ref": r.get("reference", ""), "date": day(r.get("date")),
                     "total": tot, "gst": amount(r.get("gst")) if got.get("has_gst_column") else None, "source": f"{src.sid} {src.name}, {r.get('source', '')}"})
    return {"has_gst_column": bool(got.get("has_gst_column")), "rows": rows, "report_total": amount(got.get("report_total")),
            "report_gst_total": amount(got.get("report_gst_total")), "how": "ai"}


# --- the general ledger, trial balance and journals -------------------------------------------------------

_ACCOUNT_CODE = re.compile(r"^\s*(\d{2,6}(?:\.\d+)?)\s*[-–:]\s*(.+)$|^(.+?)\s*\((\d{2,6}(?:\.\d+)?)\)\s*$")


def split_account(text: str) -> tuple[str, str]:
    """"200 - Sales" / "Sales (200)" -> ("200", "Sales")."""
    m = _ACCOUNT_CODE.match(text or "")
    if not m:
        return "", (text or "").strip()
    return (m.group(1), m.group(2).strip()) if m.group(1) else (m.group(4), m.group(3).strip())


def _signed(t: Table, values: list) -> tuple[Decimal, Decimal]:
    """(debit, credit) of a line: from debit/credit columns, else a signed amount (debit positive)."""
    if "debit" in t.cols or "credit" in t.cols:
        return abs(amount(t.get(values, "debit")) or Decimal(0)), abs(amount(t.get(values, "credit")) or Decimal(0))
    a = amount(t.get(values, "amount")) or Decimal(0)
    return (a, Decimal(0)) if a >= 0 else (Decimal(0), -a)


def read_ledger(src: Source, ai=None) -> dict:
    """{"lines": [...], "opening": {account: debit-positive balance}, "problem"}."""
    t = find_table(src, "general_ledger", ai)
    if t is None or not ({"debit", "credit", "amount"} & set(t.cols)):
        return {"lines": [], "opening": {}, "problem": "The general ledger's headings (date, debit, credit) could not be found."}
    lines, opening, account = [], {}, ""
    for row_no, values in t.rows:
        first = _first_text(values)
        low = first.lower()
        when = day(t.get(values, "date"))
        debit, credit = _signed(t, values)
        if when is None and not (debit or credit):
            if first and not low.startswith(("total", "closing", "net movement", "opening")):
                account = first  # an account heading
            continue
        if low.startswith(("total", "closing balance", "net movement")):
            continue
        acc = t.text(values, "account") or account
        if low.startswith("opening") or t.text(values, "description").lower().startswith("opening balance"):
            name = split_account(acc)[1]
            opening[name] = opening.get(name, Decimal(0)) + debit - credit
            continue
        if when is None:
            continue
        code, name = split_account(acc)
        lines.append({"id": f"{src.sid}:{row_no}", "account": name, "code": t.text(values, "code") or code, "date": when,
                      "source_type": t.text(values, "source_type"), "contact": t.text(values, "contact"),
                      "description": t.text(values, "description"), "ref": t.text(values, "ref"), "debit": debit, "credit": credit,
                      "gross": amount(t.get(values, "gross")), "gst": amount(t.get(values, "gst")), "tax_code": t.text(values, "tax_code"),
                      "source": t.ref(row_no)})
    return {"lines": lines, "opening": opening, "problem": "" if lines else "No ledger lines were found."}


def read_trial_balance(src: Source, ai=None) -> dict:
    t = find_table(src, "trial_balance", ai)
    if t is None:
        return {"rows": [], "problem": "The trial balance's headings could not be found."}
    rows = []
    for row_no, values in t.rows:
        if _is_total(values):
            continue
        name = t.text(values, "account")
        if not name:
            continue
        if "debit" in t.cols or "credit" in t.cols:
            debit, credit = abs(amount(t.get(values, "debit")) or Decimal(0)), abs(amount(t.get(values, "credit")) or Decimal(0))
            balance = debit - credit
        else:
            balance = amount(t.get(values, "balance"))
            if balance is None:
                continue
        code, plain = split_account(name)
        rows.append({"account": plain, "code": t.text(values, "code") or code, "balance": balance, "source": t.ref(row_no)})
    return {"rows": rows, "problem": "" if rows else "No accounts were found in the trial balance."}


def read_journals(src: Source, ai=None) -> dict:
    t = find_table(src, "journal_report", ai)
    if t is None:
        return {"lines": [], "problem": "The journal report's headings could not be found."}
    lines, journal, jdate = [], "", None
    for row_no, values in t.rows:
        first = _first_text(values)
        debit, credit = _signed(t, values)
        if not (debit or credit):
            m = re.search(r"journal\s*#?\s*(\w+)", first, re.I)
            if m:
                journal = m.group(1)
                jdate = day(t.get(values, "date")) or jdate
            continue
        if _is_total(values):
            continue
        code, name = split_account(t.text(values, "account"))
        lines.append({"id": f"{src.sid}:{row_no}", "journal": t.text(values, "journal") or journal, "date": day(t.get(values, "date")) or jdate,
                      "created": day(t.get(values, "created")), "modified": day(t.get(values, "modified")), "account": name,
                      "code": t.text(values, "code") or code, "description": t.text(values, "description"), "ref": t.text(values, "ref"),
                      "debit": debit, "credit": credit, "gst": amount(t.get(values, "gst")), "source": t.ref(row_no)})
    return {"lines": lines, "problem": "" if lines else "No journal lines were found."}


# --- returns, IRD statements, late claims, last year's reconciliation --------------------------------------

def _period_end(value) -> date | None:
    """"31/03/2026", "2026-03-31", "Mar 2026", "1 Feb 2026 - 31 Mar 2026" -> the period's last day."""
    from .money import month_end

    if value in (None, ""):
        return None
    d = day(value)
    if d:
        return d
    text = str(value)
    parts = re.split(r"\s+(?:-|–|to)\s+", text)
    if len(parts) == 2 and day(parts[1]):
        return day(parts[1])
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{4})", text)
    if m:
        d = day(f"1 {m.group(1)[:3]} {m.group(2)}")
        return month_end(d) if d else None
    return None


def read_returns(src: Source, ai=None) -> dict:
    boxes = ["box5", "box6", "box8", "box9", "box10", "box11", "box12", "box13", "box14", "box15"]
    out = []
    if src.sheets and (t := find_table(src, "gst_returns", ai)):
        for row_no, values in t.rows:
            end = _period_end(t.get(values, "period_end"))
            if end is None or _is_total(values):
                continue
            rec = {b: amount(t.get(values, b)) for b in boxes}
            out.append({"id": f"{src.sid}:{row_no}", "period_start": day(t.get(values, "period_start")), "period_end": end,
                        "version": t.text(values, "version") or "original", "filed": day(t.get(values, "filed")), **rec, "source": t.ref(row_no),
                        "how": "code"})
        return {"returns": out, "problem": "" if out else "No return periods were found."}
    if ai is None:
        return {"returns": [], "problem": "The return summary could not be read."}
    got = ai.extract("gst_returns", src)
    for n, r in enumerate(got.get("returns", []), start=1):
        end = _period_end(r.get("period_end"))
        if end is None:
            continue
        out.append({"id": f"{src.sid}:ai:{n}", "period_start": day(r.get("period_start")), "period_end": end,
                    "version": r.get("version") or "original", "filed": day(r.get("filed_date")),
                    **{b: amount(r.get(b)) for b in boxes}, "source": f"{src.sid} {src.name}, {r.get('source', '')}", "note": r.get("note", ""),
                    "how": "ai"})
    return {"returns": out, "problem": "" if out else "No return periods could be read from this document."}


def read_ird(src: Source, ai=None) -> dict:
    out = []
    if src.sheets and (t := find_table(src, "ird_statement", ai)):
        for row_no, values in t.rows:
            when = day(t.get(values, "date"))
            if when is None or _is_total(values):
                continue
            debit = abs(amount(t.get(values, "debit")) or Decimal(0))
            credit = abs(amount(t.get(values, "credit")) or Decimal(0))
            if "amount" in t.cols and not ({"debit", "credit"} & set(t.cols)):
                a = amount(t.get(values, "amount")) or Decimal(0)
                debit, credit = (a, Decimal(0)) if a >= 0 else (Decimal(0), -a)
            out.append({"id": f"{src.sid}:{row_no}", "date": when, "effective": day(t.get(values, "effective")) or when,
                        "type": t.text(values, "type"), "period_end": _period_end(t.get(values, "period")), "debit": debit, "credit": credit,
                        "reference": t.text(values, "reference"), "source": t.ref(row_no), "how": "code"})
        return {"lines": out, "problem": "" if out else "No statement lines were found."}
    if ai is None:
        return {"lines": [], "problem": "The IRD statement could not be read."}
    got = ai.extract("ird_statement", src)
    for n, r in enumerate(got.get("lines", []), start=1):
        when = day(r.get("date"))
        if when is None:
            continue
        out.append({"id": f"{src.sid}:ai:{n}", "date": when, "effective": day(r.get("effective_date")) or when,
                    "type": " ".join(f"{r.get('type', '')} {r.get('description', '')}".split()), "period_end": _period_end(r.get("period_end")),
                    "debit": abs(amount(r.get("debit")) or Decimal(0)), "credit": abs(amount(r.get("credit")) or Decimal(0)),
                    "reference": r.get("reference", ""), "source": f"{src.sid} {src.name}, {r.get('source', '')}", "how": "ai"})
    return {"lines": out, "problem": "" if out else "No statement lines could be read from this document."}


def _side(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ("sale", "income", "output", "box 9", "box 5", "receivable", "invoice")):
        return "output"
    if any(w in t for w in ("purchase", "expense", "input", "box 13", "box 11", "payable", "bill")):
        return "input"
    return ""


def read_late_claims(src: Source, ai=None) -> dict:
    out = []
    if src.sheets and (t := find_table(src, "late_claims", ai)):
        for row_no, values in t.rows:
            gst = amount(t.get(values, "gst"))
            if gst is None or _is_total(values):
                continue
            out.append({"id": f"{src.sid}:{row_no}", "date": day(t.get(values, "date")), "ref": t.text(values, "ref"),
                        "contact": t.text(values, "contact"), "description": t.text(values, "description"), "gst": gst,
                        "side": _side(t.text(values, "side")), "return_period_end": _period_end(t.get(values, "return_period")),
                        "source": t.ref(row_no), "how": "code"})
        return {"items": out, "problem": ""}
    if ai is None:
        return {"items": [], "problem": "The later returns' detail could not be read."}
    got = ai.extract("late_claims", src)
    for n, r in enumerate(got.get("items", []), start=1):
        gst = amount(r.get("gst"))
        if gst is None:
            continue
        out.append({"id": f"{src.sid}:ai:{n}", "date": day(r.get("date")), "ref": r.get("reference", ""), "contact": r.get("contact", ""),
                    "description": r.get("description", ""), "gst": gst, "side": r.get("side", ""),
                    "return_period_end": _period_end(r.get("return_period_end")), "source": f"{src.sid} {src.name}, {r.get('source', '')}", "how": "ai"})
    return {"items": out, "problem": ""}


def read_prior_year(src: Source, ai=None) -> dict:
    if ai is None:
        return {"problem": "Last year's reconciliation could not be read."}
    got = ai.extract("prior_year_recon", src)
    if not got or (not got.get("gl_gst_balance") and not got.get("unpaid_returns")):
        return {"problem": "Last year's GST reconciliation could not be read: check its figures by hand."}
    ref = f"{src.sid} {src.name}"
    return {
        "balance_date": day(got.get("balance_date")), "gl_gst_balance": amount(got.get("gl_gst_balance")),
        "ird_outstanding": amount(got.get("ird_outstanding")),
        "unpaid_returns": [{"period_end": _period_end(r.get("period_end")), "amount": amount(r.get("amount")), "source": f"{ref}, {r.get('source', '')}"}
                           for r in got.get("unpaid_returns", []) if amount(r.get("amount")) is not None],
        "timing_items": [{"item": r.get("item", ""), "amount": amount(r.get("amount")), "source": f"{ref}, {r.get('source', '')}"}
                         for r in got.get("timing_items", [])],
        "unresolved": [{"item": r.get("item", ""), "amount": amount(r.get("amount")), "source": f"{ref}, {r.get('source', '')}"}
                       for r in got.get("unresolved", [])],
        "problem": "",
    }
