"""The financial statements as a document, in AFIT's house format (Team 3 > Local cards).

A full set is laid out as AFIT's sample statements are:
- a cover page and a contents page, neither of them numbered;
- the independent auditor's report on the firm's letterhead (audited engagements only). Page numbering starts here.
  The report is a labelled template, never an opinion;
- the comprehensive income statement;
- the statement of financial position, with the accountant's certificate and the directors' approval;
- the statement of changes in equity (both years);
- the cash flow statement;
- the numbered accounting policies;
- the numbered notes, each statement line pointing to its note.

Every page has the company's name, the statement's title and its page number. Amounts are whole rupees, negatives in
brackets, nothing is "Nil", and the current year is shaded.

An income-statement-only engagement is one page, as AFIT's sole proprietor income statement: the revenue, direct
expense and operating expense accounts line by line, the gross and net profit.

All figures come from the engine's statements (services.state). Nothing is computed here but presentation totals and
the cash flow's interest received, which is moved out of the operating activities. The statements say DRAFT until the
Financial Statements stage is approved.
"""
import difflib
import io
import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from xml.sax.saxutils import escape

ZERO = Decimal("0")
GREY = "#e8e8e8"
# Totals with a tinted band: only in the statement of changes in equity and the PPE note (AFIT, 28 Nov 2026);
# elsewhere totals are bold and ruled.
TOTAL_BG = "#dce6f2"
OFFSET = 2  # the cover and the contents are not numbered
LOGO = Path(__file__).resolve().parent / "assets" / "afit_logo.png"  # optional: drawn on the auditor's report when present
FIRM = {
    "name": "AFIT Connect (Chartered Accountants)",
    "lines": ["P.O. Box – 58/8/H, Ihala Karagahamuna, Kadawatha, Gampaha, Sri Lanka",
              "Tel - +94 11 292 99 49 | +94 11 365 27 91 | +94 77 125 30 35",
              "Email – info@afitconnect.com     Web - www.afitconnect.com",
              "Practitioner - Dushan Thumbovila (FCA, ACCA, BSc)     Director – Nuwan Srimal (ACA, ACCA, BSc)"],
    "auditor": "AFIT Connect, Chartered Accountants, Kadawatha, Gampaha.",
}
TITLES = {"is": "Comprehensive income statement", "sofp": "Statement of financial position", "soce": "Statement of changes in equity",
          "cf": "Cash flow statement", "policies": "Accounting policies", "notes": "Notes to the financial statements"}
STATEMENTS = ("is", "sofp", "soce", "cf")
DIRECTOR = re.compile(r"director", re.I)
# What each entity calls its owners' funds and the people who sign.
ENTITY = {
    "company": {"noun": "Company", "capital": "Stated capital", "retained": "Retained earnings", "owner_account": "Shareholder’s current account",
                "drawings": "Dividends", "issue": "Issue of shares", "issue_cf": "Proceeds from the issue of shares",
                "advances": ("Net advances from shareholders", "Net repayments to shareholders"), "drawings_cf": "Dividends paid",
                "signers": ("Director", "Director"), "owners": "shareholders", "related": "Related parties and stated capital",
                "owner_balance": "Shareholder advances outstanding",
                "related_text": "Shareholder advances are unsecured, interest-free and repayable on demand. Key management compensation comprises "
                                "short-term salaries. Ordinary shares carry one vote each and rank equally for dividends and distributions."},
    "partnership": {"noun": "Partnership", "capital": "Partners’ capital", "retained": "Undistributed profits",
                    "owner_account": "Partners’ current accounts", "drawings": "Partners’ drawings", "issue": "Capital introduced",
                    "issue_cf": "Capital introduced by the partners", "advances": ("Net advances from partners", "Net repayments to partners"),
                    "drawings_cf": "Partners’ drawings", "signers": ("Partner", "Partner"), "owners": "partners",
                    "related": "Related parties and partners’ capital", "owner_balance": "Amounts due to partners",
                    "related_text": "Amounts due to the partners are unsecured, interest-free and repayable on demand. Profits and losses are shared "
                                    "in accordance with the partnership agreement."},
    "individual": {"noun": "business", "capital": "Proprietor’s capital", "retained": "Accumulated profits",
                   "owner_account": "Proprietor’s current account", "drawings": "Drawings", "issue": "Capital introduced",
                   "issue_cf": "Capital introduced by the proprietor", "advances": ("Net advances from the proprietor", "Net repayments to the proprietor"),
                   "drawings_cf": "Drawings", "signers": ("Proprietor",), "owners": "the proprietor", "related": "Related parties and capital",
                   "owner_balance": "Amount due to the proprietor",
                   "related_text": "The amount due to the proprietor is unsecured, interest-free and repayable on demand."},
}
# What each entity calls its owners' funds and the people who sign.
ENTITY = {
    "company": {"noun": "Company", "capital": "Stated capital", "retained": "Retained earnings", "owner_account": "Shareholder’s current account",
                "drawings": "Dividends", "issue": "Issue of shares", "issue_cf": "Proceeds from the issue of shares",
                "advances": ("Net advances from shareholders", "Net repayments to shareholders"), "drawings_cf": "Dividends paid",
                "signers": ("Director", "Director"), "owners": "shareholders", "related": "Related parties and stated capital",
                "owner_balance": "Shareholder advances outstanding",
                "related_text": "Shareholder advances are unsecured, interest-free and repayable on demand. Key management compensation comprises "
                                "short-term salaries. Ordinary shares carry one vote each and rank equally for dividends and distributions."},
    "partnership": {"noun": "Partnership", "capital": "Partners’ capital", "retained": "Undistributed profits",
                    "owner_account": "Partners’ current accounts", "drawings": "Partners’ drawings", "issue": "Capital introduced",
                    "issue_cf": "Capital introduced by the partners", "advances": ("Net advances from partners", "Net repayments to partners"),
                    "drawings_cf": "Partners’ drawings", "signers": ("Partner", "Partner"), "owners": "partners",
                    "related": "Related parties and partners’ capital", "owner_balance": "Amounts due to partners",
                    "related_text": "Amounts due to the partners are unsecured, interest-free and repayable on demand. Profits and losses are shared "
                                    "in accordance with the partnership agreement."},
    "individual": {"noun": "business", "capital": "Proprietor’s capital", "retained": "Accumulated profits",
                   "owner_account": "Proprietor’s current account", "drawings": "Drawings", "issue": "Capital introduced",
                   "issue_cf": "Capital introduced by the proprietor", "advances": ("Net advances from the proprietor", "Net repayments to the proprietor"),
                   "drawings_cf": "Drawings", "signers": ("Proprietor",), "owners": "the proprietor", "related": "Related parties and capital",
                   "owner_balance": "Amount due to the proprietor",
                   "related_text": "The amount due to the proprietor is unsecured, interest-free and repayable on demand."},
}
# What each entity calls its owners' funds and the people who sign.
ENTITY = {
    "company": {"noun": "Company", "capital": "Stated capital", "retained": "Retained earnings", "owner_account": "Shareholder\’s current account",
                "drawings": "Dividends", "issue": "Issue of shares", "issue_cf": "Proceeds from the issue of shares",
                "advances": ("Net advances from shareholders", "Net repayments to shareholders"), "drawings_cf": "Dividends paid",
                "signers": ("Director", "Director"), "owners": "shareholders", "related": "Related parties and stated capital",
                "owner_balance": "Shareholder advances outstanding",
                "related_text": "Shareholder advances are unsecured, interest-free and repayable on demand. Key management compensation comprises "
                                "short-term salaries. Ordinary shares carry one vote each and rank equally for dividends and distributions."},
    "partnership": {"noun": "Partnership", "capital": "Partners\’ capital", "retained": "Undistributed profits",
                    "owner_account": "Partners\’ current accounts", "drawings": "Partners\’ drawings", "issue": "Capital introduced",
                    "issue_cf": "Capital introduced by the partners", "advances": ("Net advances from partners", "Net repayments to partners"),
                    "drawings_cf": "Partners\’ drawings", "signers": ("Partner", "Partner"), "owners": "partners",
                    "related": "Related parties and partners\’ capital", "owner_balance": "Amounts due to partners",
                    "related_text": "Amounts due to the partners are unsecured, interest-free and repayable on demand. Profits and losses are shared "
                                    "in accordance with the partnership agreement."},
    "individual": {"noun": "business", "capital": "Proprietor\’s capital", "retained": "Accumulated profits",
                   "owner_account": "Proprietor\’s current account", "drawings": "Drawings", "issue": "Capital introduced",
                   "issue_cf": "Capital introduced by the proprietor", "advances": ("Net advances from the proprietor", "Net repayments to the proprietor"),
                   "drawings_cf": "Drawings", "signers": ("Proprietor",), "owners": "the proprietor", "related": "Related parties and capital",
                   "owner_balance": "Amount due to the proprietor",
                   "related_text": "The amount due to the proprietor is unsecured, interest-free and repayable on demand."},
}
# What each entity calls its owners' funds and the people who sign.
ENTITY = {
    "company": {"noun": "Company", "capital": "Stated capital", "retained": "Retained earnings", "owner_account": "Shareholder\’s current account",
                "drawings": "Dividends", "issue": "Issue of shares", "issue_cf": "Proceeds from the issue of shares",
                "advances": ("Net advances from shareholders", "Net repayments to shareholders"), "drawings_cf": "Dividends paid",
                "signers": ("Director", "Director"), "owners": "shareholders", "related": "Related parties and stated capital",
                "owner_balance": "Shareholder advances outstanding",
                "related_text": "Shareholder advances are unsecured, interest-free and repayable on demand. Key management compensation comprises "
                                "short-term salaries. Ordinary shares carry one vote each and rank equally for dividends and distributions."},
    "partnership": {"noun": "Partnership", "capital": "Partners\’ capital", "retained": "Undistributed profits",
                    "owner_account": "Partners\’ current accounts", "drawings": "Partners\’ drawings", "issue": "Capital introduced",
                    "issue_cf": "Capital introduced by the partners", "advances": ("Net advances from partners", "Net repayments to partners"),
                    "drawings_cf": "Partners\’ drawings", "signers": ("Partner", "Partner"), "owners": "partners",
                    "related": "Related parties and partners\’ capital", "owner_balance": "Amounts due to partners",
                    "related_text": "Amounts due to the partners are unsecured, interest-free and repayable on demand. Profits and losses are shared "
                                    "in accordance with the partnership agreement."},
    "individual": {"noun": "business", "capital": "Proprietor\’s capital", "retained": "Accumulated profits",
                   "owner_account": "Proprietor\’s current account", "drawings": "Drawings", "issue": "Capital introduced",
                   "issue_cf": "Capital introduced by the proprietor", "advances": ("Net advances from the proprietor", "Net repayments to the proprietor"),
                   "drawings_cf": "Drawings", "signers": ("Proprietor",), "owners": "the proprietor", "related": "Related parties and capital",
                   "owner_balance": "Amount due to the proprietor",
                   "related_text": "The amount due to the proprietor is unsecured, interest-free and repayable on demand."},
}
# What each entity calls its owners' funds and the people who sign.
ENTITY = {
    "company": {"noun": "Company", "capital": "Stated capital", "retained": "Retained earnings", "owner_account": "Shareholder\u2019s current account",
                "drawings": "Dividends", "issue": "Issue of shares", "issue_cf": "Proceeds from the issue of shares",
                "advances": ("Net advances from shareholders", "Net repayments to shareholders"), "drawings_cf": "Dividends paid",
                "signers": ("Director", "Director"), "owners": "shareholders", "related": "Related parties and stated capital",
                "owner_balance": "Shareholder advances outstanding",
                "related_text": "Shareholder advances are unsecured, interest-free and repayable on demand. Key management compensation comprises "
                                "short-term salaries. Ordinary shares carry one vote each and rank equally for dividends and distributions."},
    "partnership": {"noun": "Partnership", "capital": "Partners\u2019 capital", "retained": "Undistributed profits",
                    "owner_account": "Partners\u2019 current accounts", "drawings": "Partners\u2019 drawings", "issue": "Capital introduced",
                    "issue_cf": "Capital introduced by the partners", "advances": ("Net advances from partners", "Net repayments to partners"),
                    "drawings_cf": "Partners\u2019 drawings", "signers": ("Partner", "Partner"), "owners": "partners",
                    "related": "Related parties and partners\u2019 capital", "owner_balance": "Amounts due to partners",
                    "related_text": "Amounts due to the partners are unsecured, interest-free and repayable on demand. Profits and losses are shared "
                                    "in accordance with the partnership agreement."},
    "individual": {"noun": "business", "capital": "Proprietor\u2019s capital", "retained": "Accumulated profits",
                   "owner_account": "Proprietor\u2019s current account", "drawings": "Drawings", "issue": "Capital introduced",
                   "issue_cf": "Capital introduced by the proprietor", "advances": ("Net advances from the proprietor", "Net repayments to the proprietor"),
                   "drawings_cf": "Drawings", "signers": ("Proprietor",), "owners": "the proprietor", "related": "Related parties and capital",
                   "owner_balance": "Amount due to the proprietor",
                   "related_text": "The amount due to the proprietor is unsecured, interest-free and repayable on demand."},
}


def r(v) -> str:
    """Whole rupees: 1234567.5 -> "1,234,568"; negatives in brackets; zero -> "Nil"; nothing -> ""."""
    if v in (None, ""):
        return ""
    n = Decimal(str(v)).quantize(Decimal("1"))
    if n == 0:
        return "Nil"
    return f"({abs(n):,})" if n < 0 else f"{n:,}"


def _d(v) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else ZERO


# --- the cash flow statement's comparatives (27-28 Nov 2026): engine/cf_compare.py ------------------------------------
def cash_flow_comparatives(rows: list[dict], prior: list[dict], fin: dict) -> list[dict]:
    """This year's cash flow rows with last year's figures ("py") from last year's statement as printed, matched by
    what each line is (engine/cf_compare.py). Profit before tax and the closing cash fall back to the trial balance's
    comparative figures (cash net of bank overdrafts)."""
    from .engine.cf_compare import annotate
    from .engine.depth import overdraft

    comp = (fin.get("pl") or {}).get("comparative") or {}
    cash = ((fin.get("bs") or {}).get("cash") or {}).get("comparative")
    fallback = {"pbt": comp.get("pbt"), "end": (_d(cash) - overdraft(fin, "comparative")) if cash is not None else None}
    return annotate(rows, prior, fallback)


# --- the tax reconciliation's comparatives (28 Nov 2026) --------------------------------------------------------------
def _rec_role(label: str) -> str:
    low = (label or "").lower()
    if re.search(r"deferred|under.?\s*/?\s*\(?over|over.?provision", low):
        return "deferred"
    if re.search(r"profit before tax|accounting profit|loss before tax", low) and not re.search(r"\btax (at|on)\b|rate", low):
        return "pbt"
    if re.search(r"standard rate|statutory rate|at the rate|tax at \d|@ ?\d|\d+ ?%", low):
        return "at_rate"
    if re.search(r"taxable income|per the tax computation|current (income )?tax", low):
        return "current"
    if re.search(r"tax expense|charge for the year|in profit or loss|total", low):
        return "total"
    return "line"


def tax_rec_comparatives(rows: list[dict], prior: list[dict], computed: dict) -> list[tuple]:
    """The reconciliation to accounting profit with last year's figures: (label, this year, last year, kind). Last
    year's reconciliation as printed when it was read - each line to this year's by what it is (profit before tax, tax
    at the standard rate, current tax, deferred tax, the tax expense) or by wording; a line printed only last year comes
    in before current tax. Without it (last year's statements have none), it is worked out from last year's figures:
    tax at the standard rate on last year's profit before tax, the balance to last year's current tax as one line, then
    deferred tax - so it adds up to last year's tax expense."""
    out = [[x["label"], _d(x["amount"]), None, {"subtotal": "sub", "total": "total"}.get(x.get("kind") or "")] for x in rows]
    if prior:
        pool = [{"i": i, "label": x.get("label", ""), "role": _rec_role(x.get("label", "")), "amount": _d(x.get("amount"))} for i, x in enumerate(prior)]
        used: set[int] = set()
        for row in out:
            role = "current" if row[3] == "sub" else "total" if row[3] == "total" else _rec_role(row[0])
            if role != "line":
                hit = next((p for p in pool if p["i"] not in used and p["role"] == role), None)
            else:
                cands = [p for p in pool if p["i"] not in used and p["role"] == "line"]
                hit = max(cands, key=lambda p: difflib.SequenceMatcher(None, row[0].lower(), p["label"].lower()).ratio(), default=None)
                if hit and difflib.SequenceMatcher(None, row[0].lower(), hit["label"].lower()).ratio() < 0.6:
                    hit = None
            if hit:
                used.add(hit["i"])
                row[2] = hit["amount"]
        at = next((i for i, row in enumerate(out) if row[3] == "sub"), len(out))
        extra = [[p["label"], None, p["amount"], None] for p in pool if p["i"] not in used and p["role"] in ("line", "at_rate", "deferred")]
        out[at:at] = extra
        for row in out:
            if row[2] is None and row[1] is not None:
                row[2] = ZERO  # last year's reconciliation was read in full: a line it doesn't show was nil
        return [tuple(r) for r in out]
    pbt, rate, cur, dfr = computed.get("pbt"), computed.get("rate"), computed.get("current"), computed.get("deferred") or ZERO
    if pbt is None or cur is None:
        return [tuple(r) for r in out]
    expense = cur + dfr
    for row in out:
        role = "current" if row[3] == "sub" else "total" if row[3] == "total" else _rec_role(row[0])
        row[2] = {"pbt": pbt, "current": cur, "total": expense, "deferred": dfr}.get(role)
        if role == "at_rate" and rate:
            row[2] = (pbt * _d(rate)).quantize(Decimal("0.01"))
    if rate:
        at_rate = (pbt * _d(rate)).quantize(Decimal("0.01"))
        at = next((i for i, row in enumerate(out) if row[3] == "sub"), len(out))
        if cur - at_rate:
            out.insert(at, ["Tax effect of disallowable expenses, deductions and other items (prior year, net)", None, cur - at_rate, None])
    if dfr and not any(_rec_role(r[0]) == "deferred" for r in out):
        at = next((i for i, row in enumerate(out) if row[3] == "total"), len(out))
        out.insert(at, ["Deferred tax and under- / (over-) provision", None, dfr, None])
    return [tuple(r) for r in out]


def _long(d: date) -> str:
    return f"{d.day} {d:%B %Y}"


def _flowable_mark(**attrs):
    """A zero-size flowable that records where a part of the document starts or ends."""
    from reportlab.platypus import Flowable

    class Mark(Flowable):
        def wrap(self, *_):
            return 0, 0

        def draw(self):
            pass

    m = Mark()
    for k, v in attrs.items():
        setattr(m, k, v)
    return m


class _Report:
    def __init__(self, st: dict):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm

        self.st, self.colors, self.mm = st, colors, mm
        e = st["engagement"]
        self.e = e
        self.data = e.get("data") or {}
        self.fin = st.get("financials") or {}
        self.dp = st.get("statements") or {}
        self.full = (self.dp.get("scope") or self.fin.get("scope") or "full") == "full"
        self.audited = bool(e.get("audited")) and self.full
        self.legal = e.get("legal_name") or e.get("task") or ""
        self.name = self.legal.upper()
        self.entity = e.get("entity_type") if e.get("entity_type") in ENTITY else "company"
        self.L = ENTITY[self.entity]
        self.entity = e.get("entity_type") if e.get("entity_type") in ENTITY else "company"
        self.L = ENTITY[self.entity]
        self.entity = e.get("entity_type") if e.get("entity_type") in ENTITY else "company"
        self.L = ENTITY[self.entity]
        self.entity = e.get("entity_type") if e.get("entity_type") in ENTITY else "company"
        self.L = ENTITY[self.entity]
        self.entity = e.get("entity_type") if e.get("entity_type") in ENTITY else "company"
        self.L = ENTITY[self.entity]
        ye = date.fromisoformat(e["fy_end"]) if e.get("fy_end") else None
        self.ye = ye
        self.cy = str(ye.year) if ye else "Current"
        self.py = str(ye.year - 1) if ye else "Prior"
        self.ye_text = _long(ye) if ye else "[year end]"
        self.start = (ye.replace(year=ye.year - 1) + timedelta(days=1)) if ye else None
        self.has_comp = bool(self.fin.get("has_comparative"))
        fs_stage = (e.get("stages") or {}).get("fs", {})
        self.draft = fs_stage.get("status") != "approved"
        # A trial balance Local_Tax_AI made up from a story: dummy data, said on every page.
        self.dummy = ((e.get("data") or {}).get("tb_source") or {}).get("kind") == "story"
        self.ppe = st.get("ppe") or {}
        self.approved_on = None
        if not self.draft and fs_stage.get("at"):
            try:
                self.approved_on = _long(datetime.fromisoformat(str(fs_stage["at"]).replace("Z", "+00:00")).date())
            except ValueError:
                pass
        base = getSampleStyleSheet()["Normal"]

        def S(name, **kw):
            return ParagraphStyle(name, parent=base, **kw)

        self.s = {
            "cover": S("cover", fontName="Times-Bold", fontSize=12, alignment=1, leading=16),
            "co_t": S("co_t", fontName="Times-Bold", fontSize=11.5, leading=16, spaceAfter=10),
            "body": S("body", fontName="Helvetica", fontSize=8.5, leading=11, alignment=4),
            "ind": S("ind", fontName="Helvetica", fontSize=8.5, leading=11, alignment=4, leftIndent=10 * mm, spaceAfter=4),
            "nt": S("nt", fontName="Helvetica", fontSize=8.5, leading=11, alignment=4, leftIndent=10 * mm, spaceBefore=4, spaceAfter=4),
            "sub": S("sub", fontName="Helvetica-Bold", fontSize=8.5, leading=11, leftIndent=10 * mm),
            "cell": S("cell", fontName="Helvetica", fontSize=8.5, leading=10),
            "cellb": S("cellb", fontName="Helvetica-Bold", fontSize=8.5, leading=10),
            "cellh": S("cellh", fontName="Helvetica-Bold", fontSize=8.5, leading=10, alignment=2),
            "nh": S("nh", fontName="Helvetica-Bold", fontSize=9.5, leading=12),
            "tr": S("tr", fontName="Times-Roman", fontSize=8.5, leading=10.2, alignment=4, spaceAfter=7),
            "th": S("th", fontName="Times-Bold", fontSize=8.5, leading=11, spaceBefore=8, spaceAfter=5),
            "pname": S("pname", fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=14),
            "ptitle": S("ptitle", fontName="Helvetica-Bold", fontSize=11.5, leading=15, spaceAfter=14),
            "psmall": S("psmall", fontName="Helvetica", fontSize=7.5, leading=10),
        }
        self.pages: dict[str, int] = {}
        self.starts: dict[str, int] = {}
        self.layout: dict[str, int] = {}  # the previous pass's part starts, for the page headers
        self.notes: dict[str, int] = {}
        if self.full:
            self._number_notes()

    # --- the notes' numbers: profit or loss first, income tax, the financial position, then the disclosures ---------
    def _bs(self, h, which="amount") -> Decimal:
        return _d(((self.fin.get("bs") or {}).get(h) or {}).get(which))

    def _has(self, *hs) -> bool:
        return any(self._bs(h) or (self.has_comp and self._bs(h, "comparative")) for h in hs)

    def _number_notes(self):
        n = 1
        rows = {row["heading"]: row for row in (self.fin.get("pl") or {}).get("rows") or []}
        for h in ("revenue", "cost_of_sales", "other_income", "admin_expenses", "distribution_expenses", "finance_costs"):
            lines = rows.get(h, {}).get("lines") or []
            if lines and not (h == "other_income" and len(lines) == 1):  # a single other income line is shown on the face
                self.notes[h] = n
                n += 1
        if self._pbt_items():
            self.notes["pbt"] = n
            n += 1
        cur, comp = (self.fin.get("pl") or {}).get("current") or {}, (self.fin.get("pl") or {}).get("comparative") or {}
        if cur.get("income_tax_expense") or comp.get("income_tax_expense") or self._tax_rec():
            self.notes["tax"] = n
            n += 1
        bs = self.fin.get("bs") or {}
        for h in ("ppe", "intangibles", "investments", "other_non_current_assets", "inventories", "trade_receivables", "other_current_assets", "cash",
                  "borrowings_non_current", "trade_payables", "borrowings_current", "other_current_liabilities"):
            hs = (h, "tax_payable") if h == "trade_payables" else (h,)  # the income tax payable is in trade and other payables
            if any((bs.get(x) or {}).get("lines") for x in hs) and self._has(*hs):
                self.notes[h] = n
                n += 1
        for key in ("commitments", "contingencies", "events", "related", "risk"):
            self.notes[key] = n
            n += 1
        self.notes["share_capital"] = self.notes["shareholder_current_account"] = self.notes["related"]

    # "Profit before tax is stated after charging" (AFIT, 28 Nov 2026): auditors' remuneration, depreciation and
    # amortisation and directors' remuneration, from the expense accounts' names - each only when the books have it.
    PBT_ITEMS = (("Auditors' remuneration", re.compile(r"\baudit", re.I)), ("Depreciation", re.compile(r"depreciation", re.I)),
                 ("Amortisation", re.compile(r"amorti[sz]", re.I)), ("Directors' remuneration", None))

    def _pbt_items(self) -> list[tuple]:
        lines = [ln for row in (self.fin.get("pl") or {}).get("rows") or [] if row["kind"] == "expense" for ln in row["lines"]]
        out = []
        for label, pattern in self.PBT_ITEMS:
            pat = pattern or DIRECTOR
            hits = [ln for ln in lines if pat.search(ln.get("name") or "")]
            if label == "Directors' remuneration" and self.entity != "company":
                continue
            cy = sum((_d(ln["amount"]) for ln in hits), ZERO)
            py = sum((_d(ln.get("comparative")) for ln in hits), ZERO) if self.has_comp else None
            if hits and (cy or py):
                out.append((label, cy, py))
        return out

    def pbt_note(self, no):
        return [self.note_head(no, "Profit before tax"), self.P("Profit before tax is stated after charging:", "nt"),
                self.note_table(self._pbt_items())]

    def _tax_rec(self):
        return next((x for x in self.dp.get("notes") or [] if x.get("key") == "tax_reconciliation"), None)

    # --- building blocks -------------------------------------------------------------------------------------------
    def P(self, text, style="body"):
        from reportlab.platypus import Paragraph

        return Paragraph(text, self.s[style])

    def shown(self, key, default=""):
        p = self.pages.get(key)
        return p - OFFSET if p else default

    def years(self, cols=2):
        return [self.cy, self.py][:cols] if self.has_comp else [self.cy]

    def statement_table(self, rows: list[dict], period: str, cols: int = 2, pad: float = 4.2):
        """A primary statement: rows {"label", "note", "cy", "py", "kind": caps|head|line|sub|grand|blank, "indent"},
        the period over the year columns, the current year shaded."""
        from reportlab.platypus import Table, TableStyle

        c, mm = self.colors, self.mm
        years = self.years(cols)
        data = [["", "", period] + [""] * (len(years) - 1), ["", "Notes"] + years]
        last = 1 + len(years)
        style = [("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
                 ("ALIGN", (1, 0), (1, -1), "CENTER"), ("SPAN", (2, 0), (last, 0)), ("ALIGN", (2, 0), (last, 0), "CENTER"),
                 ("LINEBELOW", (2, 0), (last, 0), 0.7, c.black), ("BACKGROUND", (2, 1), (2, -1), c.HexColor(GREY)),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), pad), ("BOTTOMPADDING", (0, 0), (-1, -1), pad),
                 ("TOPPADDING", (0, 0), (-1, 1), 1), ("BOTTOMPADDING", (0, 0), (-1, 1), 1)]
        for i, row in enumerate(rows, start=2):
            kind = row.get("kind", "line")
            label = ("&nbsp;" * 4 * row.get("indent", 0)) + escape(row.get("label", ""))
            vals = [row.get("cy"), row.get("py")][: len(years)]
            bold = kind in ("head", "sub", "grand")
            data.append([self.P(label, "cellb" if bold else "cell"), str(row.get("note") or "")] +
                        (["" for _ in vals] if kind in ("head", "caps", "blank") else [r(v) for v in vals]))
            if kind in ("sub", "grand"):
                style += [("FONTNAME", (2, i), (-1, i), "Helvetica-Bold"), ("LINEABOVE", (2, i), (-1, i), 0.7, c.black)]
            if kind == "grand":
                style.append(("LINEBELOW", (2, i), (-1, i), 1.8, c.black))
            if kind == "blank":
                style += [("TOPPADDING", (0, i), (-1, i), 1), ("BOTTOMPADDING", (0, i), (-1, i), 1)]
        widths = [98 * mm, 16 * mm] + ([29 * mm] * len(years) if len(years) > 1 else [36 * mm])
        t = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=2)
        t.setStyle(TableStyle(style))
        return t

    def note_head(self, no, title):
        from reportlab.platypus import Table, TableStyle

        t = Table([[str(no), self.P(escape(title), "nh")]], colWidths=[10 * self.mm, 160 * self.mm], hAlign="LEFT")
        t.setStyle(TableStyle([("FONTNAME", (0, 0), (0, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (0, 0), 9.5), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 10), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
        return t

    def note_table(self, lines: list[tuple], total=None, header=True, cols=None, kinds=None):
        """A note's accounts: lines (label, current, comparative); the total with a line above and a double line under.
        kinds: {row index: "sub" | "total" | "head"} for reconciliation rows."""
        from reportlab.platypus import Table, TableStyle

        c, mm = self.colors, self.mm
        years = cols or self.years()
        data = [["", ""] + years] if header else []
        off = len(data)
        style = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("BACKGROUND", (2, 0), (2, -1), c.HexColor(GREY)),
                 ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
        if header:
            style += [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("TOPPADDING", (0, 0), (-1, 0), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 7)]
        for i, (label, a, b) in enumerate(lines):
            kind = (kinds or {}).get(i)
            data.append(["", self.P(escape(label), "cellb" if kind else "cell")] + ([r(a)] + ([r(b)] if len(years) > 1 else []) if kind != "head" else [""] * len(years)))
            if kind in ("sub", "total"):
                style += [("FONTNAME", (2, off + i), (-1, off + i), "Helvetica-Bold"),
                          ("LINEABOVE", (2, off + i), (-1, off + i), 0.6, c.black)]
            if kind == "total":
                style.append(("LINEBELOW", (2, off + i), (-1, off + i), 1.6, c.black))
        if total is not None:
            data.append(["", ""] + [r(total[0])] + ([r(total[1])] if len(years) > 1 else []))
            style += [("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
                      ("LINEABOVE", (2, -1), (-1, -1), 0.6, c.black), ("LINEBELOW", (2, -1), (-1, -1), 1.6, c.black)]
        t = Table(data, colWidths=[10 * mm, 102 * mm] + [29 * mm] * len(years), hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return t

    # --- the pages ---------------------------------------------------------------------------------------------------
    def cover(self):
        from reportlab.platypus import PageBreak, Spacer

        return [_flowable_mark(_sec="cover"), Spacer(1, 18 * self.mm), self.P(escape(self.name), "cover"), Spacer(1, 66 * self.mm),
                self.P(f"FINANCIAL STATEMENTS - {self.ye_text.upper()}", "cover"), PageBreak()]

    def contents(self):
        from reportlab.platypus import PageBreak, Table, TableStyle

        c, mm = self.colors, self.mm
        items = []
        if self.audited:
            items.append(("Independent auditor’s report", "auditor", "auditor_end"))
        items += [("Comprehensive income statement", "is", None), ("Statement of financial position", "sofp", None),
                  ("Statement of changes in equity", "soce", None), ("Cash flow statement", "cf", None),
                  ("Accounting policies", "policies", "policies_end"), ("Notes to the financial statements", "notes", "notes_end")]
        data = [["CONTENTS", ""], ["", "PAGE"]]
        for label, k, k_end in items:
            a, b = self.shown(k), (self.shown(k_end) if k_end else "")
            data.append([label, f"{a}–{b}" if b and b != a else str(a)])
        t = Table(data, colWidths=[128 * mm, 32 * mm], hAlign="LEFT")
        t.setStyle(TableStyle([("SPAN", (0, 0), (1, 0)), ("ALIGN", (0, 0), (1, 0), "CENTER"), ("FONTNAME", (0, 0), (1, 1), "Times-Bold"),
                               ("FONTSIZE", (0, 0), (1, 0), 11), ("LINEBELOW", (0, 0), (1, 0), 0.7, c.black), ("FONTSIZE", (0, 1), (-1, -1), 8.5),
                               ("FONTNAME", (0, 2), (-1, -1), "Helvetica"), ("FONTSIZE", (1, 1), (1, 1), 9.5), ("ALIGN", (1, 1), (1, -1), "CENTER"),
                               ("TOPPADDING", (0, 1), (-1, 1), 22), ("TOPPADDING", (0, 2), (-1, -1), 15), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        return [_flowable_mark(_sec="contents"), self.P(escape(self.name), "co_t"), self.P(f"FINANCIAL STATEMENTS - {self.ye_text.upper()}", "co_t"),
                self.P("", "body"), t, PageBreak()]

    def auditor(self):
        from reportlab.platypus import CondPageBreak, PageBreak, Spacer

        ar = self.dp.get("audit_report") or {}
        out = [_flowable_mark(_toc="auditor", _sec="auditor"), self.P(escape(ar.get("addressee", "")), "tr")]
        for sec in ar.get("sections") or []:
            if sec.get("continued"):
                out.append(CondPageBreak(95 * self.mm))  # the bullets start the second page, as in AFIT's report
            out.append(self.P(escape(sec["title"]), "th"))
            for para in (sec.get("text") or "").split("\n\n"):
                if para.strip():
                    out.append(self.P(escape(para.strip()), "tr"))
        out.append(Spacer(1, 14 * self.mm))
        out += [self.P(f"<b>{escape(line)}</b>", "tr") for line in (ar.get("signature") or "").split("\n")]
        return out + [_flowable_mark(_toc="auditor_end"), PageBreak()]

    def _period(self, prefix="Year ended") -> str:
        return f"{prefix} {self.ye.day} {self.ye:%B}" if self.ye else prefix

    def income_statement(self):
        from reportlab.platypus import PageBreak

        pl = self.fin.get("pl") or {}
        cur, comp = pl.get("current") or {}, pl.get("comparative") or {}
        other_names = [ln["name"] for row in pl.get("rows") or [] if row["heading"] == "other_income" for ln in row["lines"]]
        other_label = "Interest income" if other_names and all(re.search(r"interest", x, re.I) for x in other_names) else "Other income"
        n = self.notes

        def row(label, key, sign=1, kind="line", note_key=None):
            return {"label": label, "cy": sign * _d(cur.get(key)), "py": sign * _d(comp.get(key)) if comp else None, "kind": kind,
                    "note": n.get(note_key or key, "")}

        rows = [row("Revenue", "revenue"), row("Cost of sales", "cost_of_sales", -1), row("Gross profit", "gross_profit", kind="sub")]
        if cur.get("other_income") or comp.get("other_income"):
            rows.append(row(other_label, "other_income"))
        rows.append({"label": "Operating expenses", "kind": "head"})
        for key, label in (("admin_expenses", "Administrative expenses"), ("distribution_expenses", "Distribution expenses"),
                           ("finance_costs", "Finance and other expenses")):
            if cur.get(key) or comp.get(key):
                rows.append(row(label, key, -1))
        rows += [row("Profit from operating activities", "pbt", kind="sub"), row("Income tax expense", "income_tax_expense", -1, note_key="tax"),
                 row("Profit for the year", "profit", kind="sub"), row("Other comprehensive income", "oci"),
                 row("Total comprehensive income for the year", "total_comprehensive_income", kind="grand")]
        return [_flowable_mark(_toc="is", _sec="is"), self.statement_table(rows, self._period(), pad=5.5), PageBreak()]

    def financial_position(self):
        from reportlab.platypus import PageBreak, Spacer, Table, TableStyle

        pl = self.fin.get("pl") or {}
        cur_tci = _d((pl.get("current") or {}).get("total_comprehensive_income"))
        comp_tci = _d((pl.get("comparative") or {}).get("total_comprehensive_income"))
        n, amt, hc = self.notes, self._bs, self.has_comp

        def line(label, hs, note=None):
            hs = hs if isinstance(hs, tuple) else (hs,)
            return {"label": label, "cy": sum((amt(h) for h in hs), ZERO), "py": sum((amt(h, "comparative") for h in hs), ZERO) if hc else None,
                    "note": n.get(note or hs[0], "")}

        def group(title, total_label, items):
            keep = [line(lb, hs) for lb, hs in items if self._has(*(hs if isinstance(hs, tuple) else (hs,)))]
            if not keep:
                return [], ZERO, ZERO
            s_cy, s_py = sum((x["cy"] for x in keep), ZERO), sum((x["py"] or ZERO for x in keep), ZERO)
            return [{"label": title, "kind": "head"}] + keep + [{"label": total_label, "cy": s_cy, "py": s_py if hc else None, "kind": "sub"}], s_cy, s_py

        nca, nca_cy, nca_py = group("Non-current assets", "Total non-current assets", [
            ("Property, plant and equipment", "ppe"), ("Intangible assets", "intangibles"), ("Investments", "investments"),
            ("Other non-current assets", "other_non_current_assets")])
        ca, ca_cy, ca_py = group("Current assets", "Total current assets", [
            ("Inventories", "inventories"), ("Trade and other receivables", "trade_receivables"), ("Other current assets", "other_current_assets"),
            ("Cash and cash equivalents", "cash")])
        rows = [{"label": "ASSETS", "kind": "caps"}] + nca + ca + [
            {"label": "Total assets", "cy": nca_cy + ca_cy, "py": (nca_py + ca_py) if hc else None, "kind": "grand"}, {"label": "", "kind": "blank"}]
        # retained earnings at the year end = brought forward + the year's result + dividends
        L = self.L
        eq = [line(L["capital"], "share_capital")]
        if self._has("reserves"):
            eq.append(line("Reserves", "reserves"))
        eq.append({"label": L["retained"], "cy": amt("retained_earnings") + cur_tci + amt("dividends"),
                   "py": amt("retained_earnings", "comparative") + comp_tci + amt("dividends", "comparative") if hc else None})
        eq_cy, eq_py = sum((x["cy"] for x in eq), ZERO), sum((x["py"] or ZERO for x in eq), ZERO)
        rows += [{"label": "EQUITY AND LIABILITIES", "kind": "caps"}] + eq + [{"label": "Total equity", "cy": eq_cy, "py": eq_py if hc else None, "kind": "sub"}]
        ncl, ncl_cy, ncl_py = group("Non-current liabilities", "Total non-current liabilities", [
            ("Borrowings", "borrowings_non_current"), ("Deferred tax", "deferred_tax")])
        cl, cl_cy, cl_py = group("Current liabilities", "Total current liabilities", [
            ("Trade and other payables", ("trade_payables", "tax_payable")), (L["owner_account"], "shareholder_current_account"),
            ("Short-term borrowings", "borrowings_current"), ("Other current liabilities", "other_current_liabilities")])
        rows += ncl + cl + [{"label": "Total liabilities", "cy": ncl_cy + cl_cy, "py": (ncl_py + cl_py) if hc else None, "kind": "sub"},
                            {"label": "Total equity and liabilities", "cy": eq_cy + ncl_cy + cl_cy, "py": (eq_py + ncl_py + cl_py) if hc else None,
                             "kind": "grand"}]
        dots = "…" * 26
        signers = list(L["signers"])
        directors = Table([[dots] * len(signers), signers], colWidths=[95 * self.mm, 75 * self.mm][: len(signers)], hAlign="LEFT")
        directors.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), "Helvetica"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                       ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
        responsible = {"company": ("The Board of Directors is responsible for the preparation and presentation of these financial statements.",
                                   "Signed for and on behalf of the Board."),
                       "partnership": ("The partners are responsible for the preparation and presentation of these financial statements.",
                                       "Signed for and on behalf of the partners."),
                       "individual": ("The proprietor is responsible for the preparation and presentation of these financial statements.",
                                      "Signed by the proprietor.")}[self.entity]
        certificate = ("I certify that these financial statements are in compliance with the requirements of the Companies Act No. 7 of 2007."
                       if self.entity == "company" else "I certify that these financial statements have been prepared from the books and records of the "
                                                        f"{self.L['noun'].lower()}.")
        sign = [Spacer(1, 12), self.P(certificate),
                Spacer(1, 16), self.P(f"{dots}<br/>Accountant"), Spacer(1, 7), self.P(self.approved_on or "Date: " + "…" * 18), Spacer(1, 7),
                self.P(responsible[0]), Spacer(1, 5), self.P(responsible[1]), Spacer(1, 16), directors]
        return [_flowable_mark(_toc="sofp", _sec="sofp"), self.statement_table(rows, self._period("As at"), pad=2.9)] + sign + [PageBreak()]

    def changes_in_equity(self):
        from reportlab.platypus import PageBreak, Table, TableStyle

        c, mm, amt = self.colors, self.mm, self._bs
        pl = self.fin.get("pl") or {}
        cur, comp = pl.get("current") or {}, pl.get("comparative") or {}
        with_res = self._has("reserves") or _d(cur.get("oci")) or _d(comp.get("oci"))
        sc_c, res_c = (amt("share_capital", "comparative"), amt("reserves", "comparative")) if self.has_comp else (amt("share_capital"), amt("reserves"))

        def block(start, end, sc_open, res_open, re_open, profit, oci, issue, res_move, dividends):
            rows = [("open", f"Balance at {_long(start) if start else 'the start of the year'}", sc_open, res_open, re_open),
                    ("line", "Profit for the year", ZERO, ZERO, profit), ("line", "Other comprehensive income", ZERO, oci, ZERO)]
            if issue:
                rows.append(("line", self.L["issue"], issue, ZERO, ZERO))
            if res_move:
                rows.append(("line", "Other movements in reserves", ZERO, res_move, ZERO))
            if dividends:
                rows.append(("line", self.L["drawings"], ZERO, ZERO, dividends))
            rows.append(("close", f"Balance at {_long(end) if end else 'the end of the year'}", sum((x[2] for x in rows), ZERO),
                         sum((x[3] for x in rows), ZERO), sum((x[4] for x in rows), ZERO)))
            return rows

        blocks = []
        if self.has_comp and self.start:
            p_start, p_end = self.start.replace(year=self.start.year - 1), self.ye.replace(year=self.ye.year - 1)
            blocks.append(block(p_start, p_end, sc_c, res_c - _d(comp.get("oci")), amt("retained_earnings", "comparative"), _d(comp.get("profit")),
                                _d(comp.get("oci")), ZERO, ZERO, amt("dividends", "comparative")))
        blocks.append(block(self.start, self.ye, sc_c, res_c, amt("retained_earnings"), _d(cur.get("profit")), _d(cur.get("oci")),
                            amt("share_capital") - sc_c, amt("reserves") - res_c - _d(cur.get("oci")) if self.has_comp else ZERO, amt("dividends")))
        two = lambda s: escape(s).replace(" ", "<br/>", 1)  # noqa: E731 - two-line column headings
        header = ["", self.P(two(self.L["capital"]), "cellh")] + ([self.P("Reserves", "cellh")] if with_res else []) + \
            [self.P(two(self.L["retained"]), "cellh"), self.P("Total", "cellh")]
        data, style = [header], [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                 ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, 0), 12)]
        for b in blocks:
            if len(data) > 1:
                data.append([""] * len(header))
            for kind, label, sc, res, ret in b:
                i = len(data)
                data.append([self.P(escape(label), "cellb" if kind != "line" else "cell"), r(sc)] + ([r(res)] if with_res else []) + [r(ret), r(sc + res + ret)])
                if kind == "open":
                    style += [("LINEABOVE", (1, i), (-1, i), 0.7, c.black), ("FONTNAME", (1, i), (-1, i), "Helvetica-Bold")]
                if kind == "close":
                    style += [("BACKGROUND", (0, i), (-1, i), c.HexColor(TOTAL_BG)), ("FONTNAME", (1, i), (-1, i), "Helvetica-Bold"),
                              ("LINEABOVE", (1, i), (-1, i), 0.7, c.black), ("LINEBELOW", (1, i), (-1, i), 1.8, c.black)]
        w = 25 * mm if with_res else 28 * mm
        t = Table(data, colWidths=[170 * mm - w * (len(header) - 1)] + [w] * (len(header) - 1), hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return [_flowable_mark(_toc="soce", _sec="soce"), t, PageBreak()]

    def cash_flow(self):
        from reportlab.platypus import PageBreak

        cf = self.dp.get("cash_flows") or {}
        if not cf.get("available"):
            return [_flowable_mark(_toc="cf", _sec="cf"), self.P(escape(cf.get("reason", "")), "body"), PageBreak()]
        n = self.notes
        # Interest income is shown in investing activities (interest received), as AFIT presents it.
        interest = -sum((_d(ln["amount"]) for row in (self.fin.get("pl") or {}).get("rows") or [] if row["heading"] == "other_income"
                         for ln in row["lines"] if re.search(r"interest", ln.get("name") or "", re.I)), ZERO)
        secs = {s["key"]: s for s in cf["sections"]}
        op = secs["operating"]
        items = {x["label"]: _d(x["amount"]) for x in op["rows"] + (op.get("after") or [])}
        rows = [{"label": "Operating activities", "kind": "head"}, {"label": "Profit before tax", "cy": items.get("Profit before tax", ZERO)}]
        adj = [(lb, items.get(lb, ZERO)) for lb in ("Depreciation", "Amortisation")] + [("Interest income", -interest)]
        adj = [(lb, v) for lb, v in adj if v]
        if adj:
            rows += [{"label": "Adjustments", "kind": "head"}] + [{"label": lb, "cy": v} for lb, v in adj]
        wc_labels = {"(Increase) / decrease in inventories": "Inventories", "(Increase) / decrease in trade and other receivables": "Trade and other receivables",
                     "(Increase) / decrease in other current assets": "Other current assets",
                     "Increase / (decrease) in trade and other payables": "Trade and other operating payables",
                     "Increase / (decrease) in other current liabilities": "Other current liabilities"}
        wc = [(wc_labels[lb], items[lb]) for lb in wc_labels if items.get(lb)]
        if wc:
            rows += [{"label": "Changes in working capital", "kind": "head"}] + [{"label": lb, "cy": v} for lb, v in wc]
        if items.get("Income tax paid"):
            rows.append({"label": "Income tax paid", "cy": items["Income tax paid"]})
        op_total = _d(op["total"]["amount"]) - interest
        rows.append({"label": "Net cash from operating activities" if op_total >= 0 else "Net cash used in operating activities", "cy": op_total, "kind": "sub"})
        rows.append({"label": "", "kind": "blank"})

        inv = secs["investing"]
        inv_items = {x["label"]: _d(x["amount"]) for x in inv["rows"]}
        inv_rows = [("Refundable deposits paid", inv_items.get("Deposits paid", ZERO), n.get("other_non_current_assets", "")),
                    ("Purchase of property, plant and equipment", inv_items.get("Purchase of property, plant and equipment (net of disposals)", ZERO), n.get("ppe", "")),
                    ("Purchase of intangible assets", inv_items.get("Purchase of intangible assets (net)", ZERO), n.get("intangibles", "")),
                    ("(Increase) / decrease in investments", inv_items.get("(Increase) / decrease in investments", ZERO), n.get("investments", "")),
                    ("Interest received", interest, "")]
        inv_total = _d(inv["total"]["amount"]) + interest
        rows += [{"label": "Investing activities", "kind": "head"}] + [{"label": lb, "cy": v, "note": no} for lb, v, no in inv_rows if v]
        rows += [{"label": "Net cash used in investing activities" if inv_total < 0 else "Net cash from investing activities", "cy": inv_total, "kind": "sub"},
                 {"label": "", "kind": "blank"}]

        fi = secs["financing"]
        fi_items = {x["label"]: _d(x["amount"]) for x in fi["rows"]}
        adv = fi_items.get("Net movement in shareholder's current account", ZERO)
        fi_rows = [(self.L["issue_cf"], fi_items.get("Proceeds from the issue of shares", ZERO), n.get("share_capital", "")),
                   ("Net movement in borrowings", fi_items.get("Net movement in borrowings", ZERO), ""),
                   (self.L["advances"][0 if adv >= 0 else 1], adv, n.get("shareholder_current_account", "")),
                   (self.L["drawings_cf"], fi_items.get("Dividends paid", ZERO), "")]
        fi_total = _d(fi["total"]["amount"])
        rows += [{"label": "Financing activities", "kind": "head"}] + [{"label": lb, "cy": v, "note": no} for lb, v, no in fi_rows if v]
        rows += [{"label": "Net cash used in financing activities" if fi_total < 0 else "Net cash from financing activities", "cy": fi_total, "kind": "sub"},
                 {"label": "", "kind": "blank"}]
        net = _d(cf["net_change"])
        word = "increase" if net >= 0 else "decrease"
        rows += [{"label": f"Net {word} in cash and cash equivalents", "cy": net, "kind": "sub"}, {"label": "", "kind": "blank"},
                 {"label": "Movement in cash and cash equivalents", "kind": "head"}, {"label": "At start of year", "cy": cf["opening_cash"]},
                 {"label": word.capitalize(), "cy": net}, {"label": "At end of year", "cy": cf["closing_cash"], "kind": "grand", "note": n.get("cash", "")}]
        # The comparatives (27 Nov 2026): last year's cash flow statement as printed (read with last year's financial
        # statements), each figure on the line it matches. Working them out again would need the balances at the start
        # of the prior year, which the trial balance doesn't hold.
        prior = [x for x in ((self.data.get("prior_cash_flow") or {}).get("lines") or []) if x.get("amount") not in (None, "")]
        has = self.has_comp
        out = [_flowable_mark(_toc="cf", _sec="cf")]
        if has and prior:
            rows = cash_flow_comparatives(rows, prior, self.fin)
        else:
            self.has_comp = False
        t = self.statement_table(rows, self._period(), pad=3.4)
        self.has_comp = has
        out.append(t)
        if has and not prior:
            out.append(self.P("Comparatives are shown once last year's financial statements, with their statement of cash flows, are read "
                              "(Trial balance › Comparatives from last year).", "body"))
        return out + [PageBreak()]

    def policies(self):
        from reportlab.platypus import KeepTogether, PageBreak

        e, data = self.e, self.data
        pol = next((x["policies"] for x in self.dp.get("notes") or [] if x["key"] == "policies"), [])
        out = [_flowable_mark(_toc="policies", _sec="policies"), self.note_head(1, "Corporate information")]
        reg = f" ({e['nic_or_reg']})" if e.get("nic_or_reg") and self.entity != "individual" else ""
        what = {"company": "is a private limited liability company incorporated under the Companies Act No. 7 of 2007 and domiciled in Sri Lanka. "
                           "Its registered office and principal place of business are at",
                "partnership": "is a partnership carrying on business in Sri Lanka. Its principal place of business is at",
                "individual": "is a sole proprietorship carrying on business in Sri Lanka. Its principal place of business is at"}[self.entity]
        out.append(self.P(escape(f"{self.legal or '[Name]'}{reg} {what} {e.get('address') or '[address]'}. "
                                 f"Its principal activity is {(e.get('activity') or '[principal activity]').rstrip('.')}."), "ind"))
        if self.entity == "company":
            people = [("Directors", data.get("directors") or "[Directors' names]"),
                      ("", "The Board is responsible for preparing and presenting the financial statements."),
                      ("Company secretary", data.get("company_secretary") or "[Company secretary name]")]
        elif self.entity == "partnership":
            people = [("Partners", data.get("directors") or "[Partners' names]"),
                      ("", "The partners are responsible for preparing and presenting the financial statements.")]
        else:
            people = [("Proprietor", data.get("directors") or e.get("client_name") or "[Proprietor's name]"),
                      ("", "The proprietor is responsible for preparing and presenting the financial statements.")]
        if self.audited:
            people.append(("Auditor", FIRM["auditor"]))
        for title, text in people:
            if title:
                out.append(self.P(escape(title), "sub"))
            out.append(self.P(escape(text), "ind" if not title else "ind"))
        num = 2
        for p in pol:
            if p["key"] == "judgements":
                label = f"{num - 1}.1"
            else:
                label = str(num)
                num += 1
            out.append(KeepTogether([self.note_head(label, p["title"]), self.P(escape(p["text"]), "ind")]))
        return out + [_flowable_mark(_toc="policies_end"), PageBreak()]

    def notes_pages(self):
        from reportlab.platypus import KeepTogether

        fin, n, draft = self.fin, self.notes, self.draft
        texts = self.data.get("note_text") or {}
        out = [_flowable_mark(_toc="notes", _sec="notes")]
        rows_by_heading = {row["heading"]: row for row in (fin.get("pl") or {}).get("rows") or []}
        labels = {"revenue": "Revenue", "cost_of_sales": "Cost of sales", "other_income": "Other income", "admin_expenses": "Administrative expenses",
                  "distribution_expenses": "Distribution expenses", "finance_costs": "Finance and other expenses",
                  "ppe": "Property, plant and equipment", "intangibles": "Intangible assets", "investments": "Investments",
                  "other_non_current_assets": "Other non-current assets", "inventories": "Inventories", "trade_receivables": "Trade and other receivables",
                  "other_current_assets": "Other current assets", "cash": "Cash and cash equivalents", "borrowings_non_current": "Non-current borrowings",
                  "trade_payables": "Trade and other payables", "borrowings_current": "Short-term borrowings",
                  "other_current_liabilities": "Other current liabilities"}

        def acc(lines, sign):
            return [(ln["name"], sign * _d(ln["amount"]), sign * _d(ln["comparative"]) if ln.get("comparative") is not None else None) for ln in lines]

        answers = self.data.get("disclosures") or {}

        def text(key, default):
            """The accountant's own wording; else the questionnaire's answer - the client's details for a yes, the
            standard nil wording for a no (AFIT, 28 Nov 2026); else the standard wording."""
            t = texts.get(key)
            if t:
                return escape(t)
            a = answers.get(key) or {}
            if a.get("answer") == "yes" and a.get("details"):
                return escape(a["details"])
            return escape(default)

        for h, no in n.items():
            block = None
            if h in rows_by_heading:
                row = rows_by_heading[h]
                lines = acc(row["lines"], -1 if row["kind"] == "income" else 1)
                if h == "revenue":
                    lines = self.revenue_by_nature(row["lines"], lines)
                block = [self.note_head(no, labels[h]), self.note_table(lines, (row["amount"], row["comparative"]))]
                if texts.get(h):
                    block.append(self.P(escape(texts[h]), "nt"))
            elif h == "pbt":
                block = self.pbt_note(no)
            elif h == "tax":
                block = self.tax_note(no)
            elif h == "ppe":
                v = fin["bs"]["ppe"]
                table = self.ppe_schedule_note() or self.ppe_note(v)
                block = [self.note_head(no, labels[h]), table or self.note_table(acc(v["lines"], 1), (v["amount"], v["comparative"]))]
            elif h in labels:
                bs = fin["bs"]
                v = bs[h]
                sign = -1 if v["kind"] in ("equity", "liability") else 1
                lines = acc(v["lines"], sign)
                total = (_d(v["amount"]), _d(v["comparative"]) if self.has_comp else None)
                if h == "trade_payables":  # with the income tax payable, as the statement of financial position shows it
                    tp = bs.get("tax_payable") or {}
                    tax_lines = acc(tp.get("lines") or [], -1)
                    if len(tax_lines) == 1:
                        tax_lines = [("Current income tax payable", tax_lines[0][1], tax_lines[0][2])]
                    lines += tax_lines
                    total = (total[0] + _d(tp.get("amount")), (total[1] + _d(tp.get("comparative"))) if self.has_comp else None)
                block = [self.note_head(no, labels[h]), self.note_table(lines, total)]
                if h == "cash":
                    block += self.cash_equivalents_table()
            elif h == "commitments":
                block = [self.note_head(no, "Commitments"),
                         self.P(text(h, f"The {self.L['noun']} had no material capital or other contractual commitments at the reporting date."), "nt")]
            elif h == "contingencies":
                block = [self.note_head(no, "Contingent liabilities"),
                         self.P(text(h, f"The {self.L['noun']} had no material contingent liabilities at the reporting date."), "nt")]
            elif h == "events":
                block = [self.note_head(no, "Events after the reporting period"),
                         self.P(text(h, "No subsequent events requiring adjustment or material disclosure were identified up to the date the "
                                        f"{ {'company': 'Board', 'partnership': 'partners', 'individual': 'proprietor'}[self.entity]} "
                                        "authorised the financial statements for issue."), "nt")]
            elif h == "related":
                block = self.related_note(no, text)
            elif h == "risk":
                block = [self.note_head(no, "Financial risk management"),
                         self.P(text(h, "Credit exposure mainly arises from bank deposits and trade receivables. Management monitors ageing and "
                                        "counterparty quality. Liquidity exposure arises chiefly from payables and amounts due to " f"{self.L['owners']}. Management "
                                        "monitors short-term cash forecasts. Financial liabilities have contractual maturities within one year. The Company "
                                        "has no material foreign currency or variable-rate borrowing exposure.").replace("The Company", f"The {self.L['noun']}"), "nt")]
            if block:
                out.append(KeepTogether(block))
        return out + [_flowable_mark(_toc="notes_end")]

    def revenue_by_nature(self, accounts: list[dict], lines: list[tuple]) -> list[tuple]:
        """Revenue by its nature (AFIT, 28 Nov 2026): each revenue account under the description last year's statements
        gave it (e.g. "Sale of goods", "Rendering of services"), accounts of one nature added together; an account
        last year's statements don't describe keeps its own name."""
        nature = self.data.get("revenue_nature") or {}
        if not nature:
            return lines
        out: dict[str, list] = {}
        for ln, (name, cy, py) in zip(accounts, lines):
            label = nature.get(str(ln.get("code"))) or name
            row = out.setdefault(label, [ZERO, None])
            row[0] += cy
            if py is not None:
                row[1] = (row[1] or ZERO) + py
        return [(label, cy, py) for label, (cy, py) in out.items()]

    def cash_equivalents_table(self) -> list:
        """The cash note's second part (AFIT, 28 Nov 2026): cash and cash equivalents as the statement of cash flows has
        them - cash and bank balances less bank overdrafts (which are in short-term borrowings) - so the note agrees with
        the cash flow statement's closing balance."""
        from reportlab.platypus import Spacer

        cf = self.dp.get("cash_flows") or {}
        parts = cf.get("cash_components")
        if not cf.get("available") or not parts:
            return []
        hc = self.has_comp
        od_note = self.notes.get("borrowings_current")
        rows = [("Cash and bank balances", _d(parts["cash"]), _d(parts["cash_comparative"]) if hc else None),
                (f"Bank overdrafts (Note {od_note})" if od_note and (parts["overdraft"] or parts["overdraft_comparative"]) else "Bank overdrafts",
                 -_d(parts["overdraft"]), -_d(parts["overdraft_comparative"]) if hc else None)]
        total = (_d(cf["closing_cash"]), _d(cf["opening_cash"]) if hc else None)
        return [Spacer(1, 6), self.P("For the purpose of the statement of cash flows, the year end cash and cash equivalents comprise the following:", "nt"),
                self.note_table(rows, total)]

    def tax_note(self, no):
        from reportlab.platypus import Spacer

        row = next((x for x in (self.fin.get("pl") or {}).get("rows") or [] if x["heading"] == "income_tax_expense"), None)
        lines = row["lines"] if row else []
        dfr = [ln for ln in lines if re.search(r"deferred", ln.get("name") or "", re.I)]
        cur_lines = [ln for ln in lines if ln not in dfr]

        def tot(ls, which):
            return sum((_d(ln.get(which)) for ln in ls), ZERO)

        body = [("Current tax expense", tot(cur_lines, "amount"), tot(cur_lines, "comparative") if self.has_comp else None),
                ("Deferred tax expense", tot(dfr, "amount"), tot(dfr, "comparative") if self.has_comp else None)]
        block = [self.note_head(no, "Income tax"), self.note_table(body, (tot(lines, "amount"), tot(lines, "comparative") if self.has_comp else None))]
        rec = self._tax_rec()
        if rec:
            if self.has_comp:  # with last year's figures (28 Nov 2026)
                prior = (self.data.get("prior_tax_rec") or {}).get("lines") or []
                comp = (self.fin.get("pl") or {}).get("comparative") or {}
                computed = {"pbt": _d(comp["pbt"]) if comp.get("pbt") is not None else None, "rate": rec.get("rate"),
                            "current": tot(cur_lines, "comparative"), "deferred": tot(dfr, "comparative")}
                rec_rows = tax_rec_comparatives(rec["rows"], prior, computed)
                cols = self.years()
            else:
                rec_rows = [(x["label"], _d(x["amount"]), None, {"subtotal": "sub", "total": "total"}.get(x.get("kind") or "")) for x in rec["rows"]]
                cols = [self.cy]
            kinds = {i: k for i, (_, _, _, k) in enumerate(rec_rows) if k}
            block += [Spacer(1, 6), self.P("Reconciliation to accounting profit", "sub"),
                      self.note_table([(lb, cy, py) for lb, cy, py, _ in rec_rows], header=True, cols=cols, kinds=kinds)]
        text = (self.data.get("note_text") or {}).get("tax") or \
            "Current tax is based on the taxable income worked out under the Inland Revenue Act No. 24 of 2017."
        return block + [Spacer(1, 4), self.P(escape(text), "nt")]

    def related_note(self, no, text):
        amt, hc = self._bs, self.has_comp
        rows = []
        if self._has("shareholder_current_account"):
            rows.append((self.L["owner_balance"], amt("shareholder_current_account"), amt("shareholder_current_account", "comparative") if hc else None))
        kmp = [ln for row in (self.fin.get("pl") or {}).get("rows") or [] if row["kind"] == "expense" for ln in row["lines"]
               if DIRECTOR.search(ln.get("name") or "")]
        if kmp:
            rows.append(("Key management compensation", sum((_d(ln["amount"]) for ln in kmp), ZERO),
                         sum((_d(ln.get("comparative")) for ln in kmp), ZERO) if hc else None))
        shares = self.data.get("shares_issued")
        cap = self.L["capital"]
        rows.append((f"{cap} – {shares}" if shares and self.entity == "company" else cap, amt("share_capital"),
                     amt("share_capital", "comparative") if hc else None))
        return [self.note_head(no, self.L["related"]), self.note_table(rows), self.P(text("related", self.L["related_text"]), "nt")]

    def ppe_schedule_note(self):
        """The PPE note from the depreciation schedule (AFIT, 24 Nov 2026), by category: the cost from the opening
        balance to the closing one, the accumulated depreciation likewise, and the net book value this year and last.
        Used once the schedule is approved; its closing balances are checked against the trial balance."""
        from reportlab.platypus import Table, TableStyle

        sched = self.ppe.get("schedule") or {}
        cats = sched.get("categories") or []
        if not cats or self.ppe.get("status") == "not_approved":
            return None
        c, mm = self.colors, self.mm
        names = [x["label"] for x in cats]
        cols = names + (["Total"] if len(names) > 1 else [])
        start = date.fromisoformat(sched["start"]) - timedelta(days=1)

        def vals(fn):
            xs = [_d(fn(x)) for x in cats]
            return [r(v) for v in xs] + ([r(sum(xs, ZERO))] if len(names) > 1 else [])

        rows, kinds = [], {}

        def add(label, values=None, kind="line"):
            kinds[len(rows)] = kind
            rows.append(["", self.P(f"<b>{escape(label)}</b>" if kind in ("head", "net") else escape(label), "cell")] + (values or [""] * len(cols)))

        add("Cost", kind="head")
        add(f"At {_long(start)}", vals(lambda x: x["cost"]["opening"]))
        add("Additions", vals(lambda x: x["cost"]["additions"]))
        add("Disposals", vals(lambda x: -_d(x["cost"]["disposals"])))
        add(f"At {self.ye_text}", vals(lambda x: x["cost"]["closing"]), "net")
        add("Accumulated depreciation", kind="head")
        add(f"At {_long(start)}", vals(lambda x: x["accumulated"]["opening"]))
        add("Charge for the year", vals(lambda x: x["accumulated"]["charge"]))
        add("On disposals", vals(lambda x: -_d(x["accumulated"]["disposals"])))
        add(f"At {self.ye_text}", vals(lambda x: x["accumulated"]["closing"]), "net")
        add("Net book value", kind="head")
        add(f"At {self.ye_text}", vals(lambda x: x["nbv"]["closing"]), "net")
        add(f"At {_long(start)}", vals(lambda x: x["nbv"]["opening"]))
        header = ["", ""] + [self.P(escape(x).replace(" ", "<br/>", 1) if len(x) > 10 else escape(x), "cellh") for x in cols]
        style = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                 ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, 0), 8)]
        for i, kind in kinds.items():
            if kind == "head":
                style.append(("TOPPADDING", (0, i + 1), (-1, i + 1), 8))
            if kind == "net":
                style += [("FONTNAME", (2, i + 1), (-1, i + 1), "Helvetica-Bold"), ("BACKGROUND", (1, i + 1), (-1, i + 1), c.HexColor(TOTAL_BG)),
                          ("LINEABOVE", (2, i + 1), (-1, i + 1), 0.6, c.black), ("LINEBELOW", (2, i + 1), (-1, i + 1), 1.6, c.black)]
        width = min(27.0, 104.0 / len(cols))
        t = Table([header] + rows, colWidths=[10 * mm, (160 - width * len(cols)) * mm] + [width * mm] * len(cols), hAlign="LEFT")
        t.setStyle(TableStyle(style))
        rates = "; ".join(f"{x['label']} {_d(x['rate']) * 100:g}% {'reducing balance' if x['method'] == 'reducing_balance' else 'straight-line'}"
                          for x in cats if _d(x["rate"]))
        from reportlab.platypus import KeepTogether

        return KeepTogether([t, self.P(escape(f"Depreciation is charged monthly at: {rates}. " + (sched.get("convention") or "")), "nt")])

    def ppe_note(self, v):
        """Cost, accumulated depreciation and the year's movement, by class, from the PPE accounts (cost accounts and
        their accumulated depreciation accounts); None when the accounts can't be paired into classes."""
        from reportlab.platypus import Table, TableStyle

        c, mm = self.colors, self.mm
        classes: dict[str, dict] = {}
        # The classes are the asset categories (AFIT, 28 Nov 2026): last year's, once last year's statements are read,
        # each account in the category and role the PPE section gives it; by the account's name only without them.
        cats = {a["code"]: a for a in self.ppe.get("accounts") or [] if a.get("category")}
        labels = {p["key"]: p["label"] for p in self.ppe.get("policy") or []}
        for ln in v["lines"]:
            name = ln["name"]
            a = cats.get(str(ln.get("code")))
            if a:
                dep, key = a.get("role") == "accumulated", labels.get(a["category"], a["category"])
            else:
                dep = bool(re.search(r"accum|acc\.|depreciation|provision for dep", name, re.I))
                key = re.sub(r"(?i)\b(accumulated|acc\.?|provision for|depreciation|at cost|cost|on|of|-|–|\(|\))\b", " ", name)
                key = " ".join(re.sub(r"[^A-Za-z& ]", " ", key).split()).capitalize() or "Other"
            k = classes.setdefault(key, {"cost": ZERO, "dep": ZERO, "cost_p": ZERO, "dep_p": ZERO})
            k["dep" if dep else "cost"] += _d(ln["amount"])
            k["dep_p" if dep else "cost_p"] += _d(ln.get("comparative"))
        if not classes or len(classes) > 5 or not any(k["dep"] for k in classes.values()):
            return None
        names = list(classes)
        cols = names + (["Total"] if len(names) > 1 else [])

        def vals(fn):
            xs = [fn(classes[k]) for k in names]
            return [r(x) for x in xs] + ([r(sum(xs, ZERO))] if len(names) > 1 else [])

        rows, kinds = [], {}

        def add(label, values=None, kind="line"):
            kinds[len(rows)] = kind
            rows.append(["", self.P(f"<b>{escape(label)}</b>" if kind in ("head", "net") else escape(label), "cell")] + (values or [""] * len(cols)))

        if self.has_comp:
            add(f"At {_long(self.ye.replace(year=self.ye.year - 1))}" if self.ye else "At the start of the year", kind="head")
            add("Cost", vals(lambda k: k["cost_p"]))
            add("Accumulated depreciation", vals(lambda k: k["dep_p"]))
            add("Net book amount", vals(lambda k: k["cost_p"] + k["dep_p"]), "net")
            add(f"Year ended {self.ye_text}", kind="head")
            add("Opening balance", vals(lambda k: k["cost_p"] + k["dep_p"]))
            add("Additions", vals(lambda k: max(k["cost"] - k["cost_p"], ZERO)))
            add("Disposals – cost", vals(lambda k: min(k["cost"] - k["cost_p"], ZERO)))
            add("Depreciation charge", vals(lambda k: k["dep"] - k["dep_p"]))
            add("Closing net book amount", vals(lambda k: k["cost"] + k["dep"]), "net")
        add(self.ye_text if self.ye else "At the end of the year", kind="head")
        add("Cost", vals(lambda k: k["cost"]))
        add("Accumulated depreciation", vals(lambda k: k["dep"]))
        add("Net book amount", vals(lambda k: k["cost"] + k["dep"]), "net")
        header = ["", ""] + [self.P(escape(x).replace(" ", "<br/>", 1) if len(x) > 10 else escape(x), "cellh") for x in cols]
        style = [("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (2, 0), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                 ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, 0), 8)]
        for i, kind in kinds.items():
            if kind == "head":
                style.append(("TOPPADDING", (0, i + 1), (-1, i + 1), 8))
            if kind == "net":
                style += [("FONTNAME", (2, i + 1), (-1, i + 1), "Helvetica-Bold"), ("BACKGROUND", (1, i + 1), (-1, i + 1), c.HexColor(TOTAL_BG)),
                          ("LINEBELOW", (2, i + 1), (-1, i + 1), 1.6, c.black)]
        width = min(27.0, 104.0 / len(cols))
        t = Table([header] + rows, colWidths=[10 * mm, (160 - width * len(cols)) * mm] + [width * mm] * len(cols), hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return t

    # --- the income statement on its own: AFIT's sole proprietor format --------------------------------------------
    def proprietor(self):
        from reportlab.platypus import Table, TableStyle

        c, mm = self.colors, self.mm
        pl = self.fin.get("pl") or {}
        rows_by = {row["heading"]: row for row in pl.get("rows") or []}
        years = self.years()
        hc = len(years) > 1
        data = [["", self._period()] + [""] * (len(years) - 1), [""] + years]
        last = len(years)
        style = [("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                 ("SPAN", (1, 0), (last, 0)), ("ALIGN", (1, 0), (last, 0), "CENTER"), ("LINEBELOW", (1, 0), (last, 0), 0.7, c.black),
                 ("BACKGROUND", (1, 1), (1, -1), c.HexColor(GREY)), ("TOPPADDING", (0, 0), (-1, -1), 2.6), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.6),
                 ("ALIGN", (1, 1), (-1, 1), "CENTER"), ("BOTTOMPADDING", (0, 1), (-1, 1), 12)]

        def add(label, cy=None, py=None, kind="line"):
            i = len(data)
            if kind == "head":
                style.append(("TOPPADDING", (0, i), (-1, i), 12))
            cells = [r(cy)] + ([r(py)] if hc else []) if kind != "head" else [""] * len(years)
            big = kind in ("big", "net")
            if big:
                label_p = self.P(f"<font size=10><b>{escape(label)}</b></font>", "cell")
            else:
                label_p = self.P("&nbsp;" * 6 + escape(label) if kind == "line" else f"<b>{escape(label)}</b>", "cell")
            data.append([label_p] + cells)
            if kind in ("total", "big", "net"):
                style.extend([("FONTNAME", (1, i), (-1, i), "Helvetica-Bold"), ("LINEABOVE", (1, i), (-1, i), 0.7, c.black)])
            if big:
                style.extend([("FONTSIZE", (1, i), (-1, i), 9.5), ("TOPPADDING", (0, i), (-1, i), 7), ("BOTTOMPADDING", (0, i), (-1, i), 7)])
            if kind == "net":
                style.append(("LINEBELOW", (1, i), (-1, i), 2.2, c.black))

        def section(head, keys, sign, total_label, total_sign):
            lines = [ln for k in keys for ln in (rows_by.get(k) or {}).get("lines") or []]
            if not lines:
                return ZERO, ZERO
            add(head, kind="head")
            for ln in lines:
                add(ln["name"], sign * _d(ln["amount"]), sign * _d(ln.get("comparative")) if hc else None)
            cy = sum((sign * _d(ln["amount"]) for ln in lines), ZERO)
            py = sum((sign * _d(ln.get("comparative")) for ln in lines), ZERO)
            if total_label and (len(lines) > 1 or total_sign < 0):
                add(total_label, total_sign * cy, total_sign * py if hc else None, "total")
            return cy, py

        rev = section("Revenue", ["revenue"], -1, "Total revenue", 1)
        cos = section("Direct expenses", ["cost_of_sales"], 1, "Total direct expenses", -1)
        add("Gross profit / (loss)", rev[0] - cos[0], (rev[1] - cos[1]) if hc else None, "big")
        oth = section("Other income", ["other_income"], -1, "Total other income", 1)
        opx = section("Operating expenses", ["admin_expenses", "distribution_expenses", "finance_costs"], 1, "Total operating expenses", -1)
        net_cy, net_py = rev[0] - cos[0] + oth[0] - opx[0], rev[1] - cos[1] + oth[1] - opx[1]
        tax = section("Income tax", ["income_tax_expense"], 1, "", -1)
        if tax != (ZERO, ZERO):
            net_cy, net_py = net_cy - tax[0], net_py - tax[1]
        add("Net profit / (loss) for the year", net_cy, net_py if hc else None, "net")
        t = Table(data, colWidths=[108 * mm] + [31 * mm] * len(years), hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return [self.P(escape(self.legal), "pname"), self.P("Income Statement", "ptitle"), self.P("Amounts in Sri Lankan rupees (LKR)", "psmall"),
                self.P("", "psmall"), t]

    # --- the document ------------------------------------------------------------------------------------------------
    def story(self):
        if not self.full:
            return self.proprietor()
        out = self.cover() + self.contents()
        if self.audited:
            out += self.auditor()
        return out + self.income_statement() + self.financial_position() + self.changes_in_equity() + self.cash_flow() + self.policies() + \
            self.notes_pages()

    def section_at(self, page: int) -> tuple[str, int]:
        best = ("", 0)
        for key, start in self.layout.items():
            if start <= page and start >= best[1]:
                best = (key, start)
        return best

    def draw_page(self, canvas, doc):
        mm = self.mm
        canvas.saveState()
        p = doc.page
        if self.dummy:
            canvas.setFont("Helvetica-Bold", 8)
            canvas.setFillColorRGB(0.75, 0.1, 0.1)
            canvas.drawCentredString(105 * mm, 290 * mm, "ILLUSTRATIVE - DUMMY DATA MADE UP FROM A STORY; NOT A CLIENT'S ACCOUNTS")
            canvas.setFillColorRGB(0, 0, 0)
        if not self.full:
            canvas.restoreState()
            return
        sec, start = self.section_at(p)
        if sec == "auditor":
            self.letterhead(canvas, p, cont=p > start)
        elif sec in TITLES:
            canvas.setFont("Helvetica", 8.5)
            canvas.drawRightString(192 * mm, 280 * mm, f"Page {p - OFFSET}")
            canvas.setFont("Helvetica-Bold", 10.5)
            canvas.drawString(20 * mm, 271 * mm, self.name)
            canvas.setFont("Helvetica-Bold", 11)
            canvas.drawString(20 * mm, 263 * mm, TITLES[sec] + (" (contd)" if sec == "policies" and p > start else ""))
            if sec != "policies":
                canvas.setFont("Helvetica-Bold", 7.5)
                canvas.drawString(20 * mm, 256 * mm, "(all amounts in Sri Lanka Rupees)")
            if sec in STATEMENTS:
                canvas.setFont("Helvetica", 7.5)
                a, b = self.shown("policies", ""), self.shown("notes_end", "")
                canvas.drawString(20 * mm, 24 * mm, f"The accounting policies and notes on pages {a} to {b} form an integral part of these financial statements.")
                if self.audited:
                    x, y = self.shown("auditor", ""), self.shown("auditor_end", "")
                    canvas.drawString(20 * mm, 20.5 * mm, f"Report of the auditors on page {x}" if x == y else f"Report of the auditors on pages {x} and {y}")
        canvas.restoreState()

    def letterhead(self, canvas, p, cont):
        mm = self.mm
        canvas.setFont("Helvetica", 7.5)
        canvas.drawRightString(192 * mm, 280 * mm, "DRAFT TEMPLATE - NOT AN AUDIT OPINION")
        if LOGO.exists():
            canvas.drawImage(str(LOGO), 20 * mm, 262 * mm, width=38 * mm, height=16 * mm, preserveAspectRatio=True, anchor="sw", mask="auto")
        else:  # the firm's wordmark
            canvas.setFont("Helvetica-Bold", 17)
            canvas.drawString(26 * mm, 268 * mm, "AFIT")
            canvas.setFont("Helvetica", 7.5)
            canvas.drawString(31 * mm, 264.5 * mm, "connects")
        canvas.setFont("Times-Bold", 9.5)
        canvas.drawString(20 * mm, 255 * mm, "INDEPENDENT AUDITOR’S REPORT" + (" (CONTD)" if cont else ""))
        canvas.setLineWidth(0.7)
        canvas.line(20 * mm, 31 * mm, 192 * mm, 31 * mm)
        canvas.setFont("Times-Bold", 7)
        canvas.drawString(20 * mm, 28 * mm, FIRM["name"])
        canvas.setFont("Times-Roman", 7)
        for i, line in enumerate(FIRM["lines"]):
            canvas.drawString(20 * mm, (25 - 2.8 * i) * mm, line)
        canvas.setFont("Helvetica", 8.5)
        canvas.drawRightString(192 * mm, (25 - 2.8 * 3) * mm, f"Page {p - OFFSET}")

    def build(self) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate

        report, mm = self, self.mm

        class Doc(SimpleDocTemplate):
            def afterFlowable(self, flowable):
                key = getattr(flowable, "_toc", None)
                if key:
                    report.pages[key] = self.page
                sec = getattr(flowable, "_sec", None)
                if sec and sec not in report.starts:
                    report.starts[sec] = self.page

        top, bottom = (50 * mm, 34 * mm) if self.full else (22 * mm, 18 * mm)
        buf = io.BytesIO()
        for _ in range(2):  # the first pass finds each part's page for the contents, the headers and the footers
            self.starts = {}
            buf = io.BytesIO()
            Doc(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=18 * mm, topMargin=top, bottomMargin=bottom,
                title=f"{self.legal} - {'Financial statements' if self.full else 'Income statement'}", author="TASKO Local Tax workflow").build(
                self.story(), onFirstPage=self.draw_page, onLaterPages=self.draw_page)
            self.layout = dict(self.starts)
        return buf.getvalue()


def render(st: dict) -> bytes:
    """The financial statements as a PDF in AFIT's house format (the full set, or the income statement on its own)."""
    return _Report(st).build()
