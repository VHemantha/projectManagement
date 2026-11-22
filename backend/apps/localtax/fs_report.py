"""The financial statements as a document, in AFIT's house format (Team 3 > Local cards).

Laid out as AFIT's signed statements are: a cover page; contents; the independent auditor's report (audited
engagements - a labelled template, never an opinion); the comprehensive income statement; the statement of financial
position with the accountant's certificate and the directors' approval; the statement of changes in equity; the cash
flow statement; the accounting policies; and the numbered notes, each statement line pointing to its note. Every page
carries the company's name and its page number; amounts are whole rupees, negatives in brackets, the current year
shaded. An income-statement-only engagement has the income statement, the policies and its notes.

All figures come from the engine's statements (services.state); nothing is computed here but presentation totals.
The statements say DRAFT until the Financial Statements stage is approved.
"""
import io
import re
from datetime import date, timedelta
from decimal import Decimal
from xml.sax.saxutils import escape

ZERO = Decimal("0")
GREY = "#e8e8e8"


def r(v) -> str:
    """Whole rupees: 1234567.5 -> "1,234,568"; negatives in brackets; nothing -> "-"."""
    if v in (None, ""):
        return ""
    n = Decimal(str(v)).quantize(Decimal("1"))
    if n == 0:
        return "-"
    return f"({abs(n):,})" if n < 0 else f"{n:,}"


def _d(v) -> Decimal:
    return Decimal(str(v)) if v not in (None, "") else ZERO


class _Report:
    def __init__(self, st: dict):
        from reportlab.lib import colors
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

        self.st, self.colors = st, colors
        e = st["engagement"]
        self.e = e
        self.fin = st.get("financials") or {}
        self.dp = st.get("statements") or {}
        self.full = (self.dp.get("scope") or "full") == "full"
        self.name = (e.get("legal_name") or e.get("task") or "").upper()
        ye = date.fromisoformat(e["fy_end"]) if e.get("fy_end") else None
        self.ye = ye
        self.cy = str(ye.year) if ye else "Current"
        self.py = str(ye.year - 1) if ye else "Prior"
        self.ye_text = f"{ye.day} {ye:%B %Y}" if ye else "[year end]"
        start = (ye.replace(year=ye.year - 1) + timedelta(days=1)) if ye else None
        self.start_text = f"{start.day} {start:%B %Y}" if start else "[start of year]"
        self.has_comp = bool(self.fin.get("has_comparative"))
        self.draft = (e.get("stages") or {}).get("fs", {}).get("status") != "approved"
        base = getSampleStyleSheet()
        self.s = {
            "cover": ParagraphStyle("cover", parent=base["Normal"], fontName="Times-Bold", fontSize=13, alignment=1, leading=18),
            "co": ParagraphStyle("co", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=14),
            "title": ParagraphStyle("title", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=11, leading=15, spaceBefore=2),
            "small": ParagraphStyle("small", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=7.5, leading=10),
            "body": ParagraphStyle("body", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=11.5, alignment=4),
            "h": ParagraphStyle("h", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=9, leading=12, spaceBefore=8, spaceAfter=3),
            "sub": ParagraphStyle("sub", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8.5, leading=11, spaceBefore=4),
            "cell": ParagraphStyle("cell", parent=base["Normal"], fontName="Helvetica", fontSize=8.5, leading=10.5),
            "foot": ParagraphStyle("foot", parent=base["Normal"], fontName="Helvetica", fontSize=7.5, leading=10),
            "draft": ParagraphStyle("draft", parent=base["Normal"], fontName="Helvetica-Bold", fontSize=8, textColor=colors.HexColor("#b42318")),
        }
        self.pages: dict[str, int] = {}
        self.notes: dict[str, int] = {}
        self._number_notes()

    # --- notes numbering: P&L lines first, then the financial position, as in the house format -------------------
    def _number_notes(self):
        n = 1
        rows = {row["heading"]: row for row in (self.fin.get("pl") or {}).get("rows") or []}
        for h in ("revenue", "cost_of_sales", "other_income", "admin_expenses", "distribution_expenses", "finance_costs"):
            lines = rows.get(h, {}).get("lines") or []
            if lines and not (h == "other_income" and len(lines) == 1):  # a single other income line is shown on the face
                self.notes[h] = n
                n += 1
        if self.full:
            for h in ("ppe", "intangibles", "investments", "other_non_current_assets", "inventories", "trade_receivables", "other_current_assets", "cash",
                      "borrowings_non_current", "trade_payables", "borrowings_current", "other_current_liabilities"):
                v = (self.fin.get("bs") or {}).get(h)
                if v and v.get("lines") and (v.get("amount") or v.get("comparative")):
                    self.notes[h] = n
                    n += 1
        self.next_note = n

    # --- building blocks -------------------------------------------------------------------------------------------
    def P(self, text, style="body"):
        from reportlab.platypus import Paragraph

        return Paragraph(text, self.s[style])

    def head(self, title: str, key: str):
        from reportlab.platypus import Paragraph, Spacer

        p = Paragraph(escape(title), self.s["title"])
        p._toc = key
        return [p, Spacer(1, 4)]  # the company's name is in every page's header

    def table(self, rows: list[dict], period: str, cols: int = 2, note_col: bool = True):
        """rows: {"label", "note", "cy", "py", "kind": head|line|sub|total|grand|blank, "indent"}."""
        from reportlab.lib.units import mm
        from reportlab.platypus import Table, TableStyle

        c = self.colors
        years = [self.cy, self.py][:cols] if self.has_comp else [self.cy]
        header1 = ["", "Notes" if note_col else ""] + [period] + [""] * (len(years) - 1)
        header2 = ["", ""] + years
        data = [header1, header2]
        style = [("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                 ("ALIGN", (1, 0), (1, -1), "CENTER"), ("SPAN", (2, 0), (-1, 0)), ("ALIGN", (2, 0), (-1, 0), "CENTER"),
                 ("LINEBELOW", (2, 0), (-1, 0), 0.6, c.black), ("BACKGROUND", (2, 1), (2, -1), c.HexColor(GREY)),
                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3)]
        for i, row in enumerate(rows, start=2):
            kind = row.get("kind", "line")
            label = ("&nbsp;" * 4 * row.get("indent", 0)) + escape(row.get("label", ""))
            vals = [row.get("cy"), row.get("py")][: len(years)]
            data.append([self.P(label, "cell") if kind not in ("head", "total", "grand", "sub") else self.P(f"<b>{label}</b>", "cell"),
                         str(row.get("note") or "")] + [r(v) if kind != "head" else "" for v in vals])
            if kind in ("total", "grand", "sub"):
                style.append(("FONTNAME", (2, i), (-1, i), "Helvetica-Bold"))
                style.append(("LINEABOVE", (2, i), (-1, i), 0.8, c.black))
            if kind == "grand":
                style.append(("LINEBELOW", (2, i), (-1, i), 1.6, c.black))
            if kind == "total":
                style.append(("LINEBELOW", (2, i), (-1, i), 0.8, c.black))
        widths = [92 * mm, 16 * mm] + [32 * mm] * len(years)
        t = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=2)
        t.setStyle(TableStyle(style))
        return t

    def plain_table(self, header: list[str], rows: list[list], widths_mm: list[float], bold_last: bool = False, shade_col: int | None = 1):
        from reportlab.lib.units import mm
        from reportlab.platypus import Table, TableStyle

        c = self.colors
        data = [header] + [[self.P(escape(str(x)), "cell") if i == 0 else x for i, x in enumerate(row)] for row in rows]
        style = [("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5), ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                 ("LINEBELOW", (1, 0), (-1, 0), 0.6, c.black), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5), ("TOPPADDING", (0, 0), (-1, -1), 2.5)]
        if shade_col is not None:
            style.append(("BACKGROUND", (shade_col, 0), (shade_col, -1), c.HexColor(GREY)))
        if bold_last and rows:
            style += [("FONTNAME", (1, -1), (-1, -1), "Helvetica-Bold"), ("LINEABOVE", (1, -1), (-1, -1), 0.8, c.black),
                      ("LINEBELOW", (1, -1), (-1, -1), 1.2, c.black)]
        t = Table(data, colWidths=[w * mm for w in widths_mm], hAlign="LEFT")
        t.setStyle(TableStyle(style))
        return t

    def footer_line(self):
        audited = self.e.get("audited")
        pages = self.pages
        if audited and "auditor" in pages:
            a, b = pages["auditor"], pages.get("auditor_end", pages["auditor"])
            return self.P(f"Report of the auditors on page {a}" if a == b else f"Report of the auditors on pages {a} &amp; {b}", "foot")
        return self.P(f"The accounting policies and notes on pages {pages.get('policies', '')} to {pages.get('notes_end', pages.get('notes', ''))} "
                      "form an integral part of these financial statements.", "foot")

    # --- the pages ---------------------------------------------------------------------------------------------------
    def cover(self):
        from reportlab.platypus import PageBreak, Spacer

        return [Spacer(1, 190), self.P(escape(self.name), "cover"), Spacer(1, 160),
                self.P(f"FINANCIAL STATEMENTS - {self.ye_text.upper()}" if self.full else f"INCOME STATEMENT - YEAR ENDED {self.ye_text.upper()}", "cover"),
                Spacer(1, 30)] + ([self.P("DRAFT - for review", "cover")] if self.draft else []) + [PageBreak()]

    def contents(self):
        from reportlab.platypus import PageBreak, Spacer

        items = []
        if self.e.get("audited"):
            items.append(("Independent auditor's report", "auditor", "auditor_end"))
        items.append(("Comprehensive income statement", "is", None))
        if self.full:
            items += [("Statement of financial position", "sofp", None), ("Statement of changes in equity", "soce", None), ("Cash flow statement", "cf", None)]
        items += [("Accounting policies", "policies", "policies_end"), ("Notes to the financial statements", "notes", "notes_end")]
        rows = []
        for label, k, k_end in items:
            a, b = self.pages.get(k, ""), self.pages.get(k_end, "") if k_end else ""
            rows.append([label, f"{a} - {b}" if b and b != a else str(a)])
        out = [self.P(escape(self.name), "co"), self.P(f"FINANCIAL STATEMENTS - {self.ye_text.upper()}", "co"), Spacer(1, 30),
               self.P("<b>CONTENTS</b>", "title"), Spacer(1, 8), self.plain_table(["", "PAGE"], rows, [130, 30], shade_col=None), PageBreak()]
        out[0]._toc = "contents"
        return out

    def auditor(self):
        from reportlab.platypus import PageBreak, Spacer

        ar = self.dp.get("audit_report") or {}
        out = [self.P("<b>INDEPENDENT AUDITOR'S REPORT</b>", "title"), self.P(f"<b>{escape(ar.get('label', 'DRAFT TEMPLATE - NOT AN AUDIT OPINION'))}</b>", "draft"),
               Spacer(1, 6), self.P(escape(ar.get("addressee", "")), "body")]
        out[0]._toc = "auditor"
        for sec in ar.get("sections") or []:
            out.append(self.P(escape(sec["title"]), "h"))
            if sec.get("text"):
                out.append(self.P(escape(sec["text"]), "body"))
        out += [Spacer(1, 24), self.P(escape(ar.get("signature", "")).replace("\n", "<br/>"), "body")]
        marker = self.P("", "foot")
        marker._toc = "auditor_end"
        return out + [marker, PageBreak()]

    def income_statement(self):
        from reportlab.platypus import PageBreak, Spacer

        pl = self.fin.get("pl") or {}
        cur, comp = pl.get("current") or {}, pl.get("comparative") or {}
        other_names = [ln["name"] for row in pl.get("rows") or [] if row["heading"] == "other_income" for ln in row["lines"]]
        other_label = "Interest income" if other_names and all(re.search(r"interest", x, re.I) for x in other_names) else "Other income"
        n = self.notes

        def row(label, key, sign=1, kind="line", note_key=None, indent=0):
            return {"label": label, "cy": sign * _d(cur.get(key)), "py": sign * _d(comp.get(key)) if comp else None, "kind": kind,
                    "note": n.get(note_key or key, ""), "indent": indent}

        rows = [row("Revenue", "revenue"), row("Cost of sales", "cost_of_sales", -1), row("Gross profit", "gross_profit", kind="sub")]
        if cur.get("other_income") or comp.get("other_income"):
            rows.append(row(other_label, "other_income"))
        rows.append({"label": "Operating expenses", "kind": "head"})
        for key, label in (("admin_expenses", "Administrative expenses"), ("distribution_expenses", "Distribution expenses"),
                           ("finance_costs", "Finance and other expenses")):
            if cur.get(key) or comp.get(key):
                rows.append(row(label, key, -1))
        rows += [row("Profit from operating activities", "pbt", kind="sub"), row("Tax expense", "income_tax_expense", -1),
                 row("Profit for the year", "profit", kind="grand")]
        if cur.get("oci") or comp.get("oci"):
            rows += [row("Other comprehensive income", "oci"), row("Total comprehensive income for the year", "total_comprehensive_income", kind="grand")]
        return self.head("Comprehensive income statement", "is") + [self.P("(all amounts in Sri Lanka Rupees)", "small"), Spacer(1, 6),
                                                                      self.table(rows, self._period()),
                                                                      Spacer(1, 30), self.footer_line(), PageBreak()]

    def _period(self) -> str:
        return f"Year ended {self.ye.day} {self.ye:%B}" if self.ye else "Year ended"

    def financial_position(self):
        from reportlab.platypus import PageBreak, Spacer

        bs = self.fin.get("bs") or {}
        pl = self.fin.get("pl") or {}
        cur_tci = _d((pl.get("current") or {}).get("total_comprehensive_income"))
        comp_tci = _d((pl.get("comparative") or {}).get("total_comprehensive_income")) if pl.get("comparative") else ZERO
        n = self.notes

        def amt(h, which="amount"):
            return _d((bs.get(h) or {}).get(which))

        def row(label, h, kind="line"):
            return {"label": label, "cy": amt(h), "py": amt(h, "comparative") if self.has_comp else None, "note": n.get(h, ""), "kind": kind}

        def present(*hs):
            return [h for h in hs if amt(h) or (self.has_comp and amt(h, "comparative"))]

        rows = [{"label": "ASSETS", "kind": "head"}]
        groups = [("Non-current assets", [("Property, plant and equipment", "ppe"), ("Intangible assets", "intangibles"), ("Investments", "investments"),
                                          ("Other non-current assets", "other_non_current_assets")]),
                  ("Current assets", [("Inventories", "inventories"), ("Trade and other receivables", "trade_receivables"),
                                      ("Other current assets", "other_current_assets"), ("Cash and cash equivalents", "cash")])]
        for title, items in groups:
            keep = [(lb, h) for lb, h in items if h in present(h)]
            if not keep:
                continue
            rows.append({"label": title, "kind": "head"})
            rows += [row(lb, h) for lb, h in keep]
            if title == "Current assets":
                rows.append({"label": "", "cy": sum(amt(h) for _, h in keep), "py": sum(amt(h, "comparative") for _, h in keep) if self.has_comp else None,
                             "kind": "sub"})
        rows.append({"label": "Total assets", "cy": self.fin["totals"]["assets"],
                     "py": sum(amt(h, "comparative") for h, v in bs.items() if v["kind"] == "asset") if self.has_comp else None, "kind": "total"})
        # equity: retained earnings at the year end = brought forward + the year's result + dividends
        re_cy = amt("retained_earnings") + cur_tci + amt("dividends")
        re_py = amt("retained_earnings", "comparative") + comp_tci + amt("dividends", "comparative") if self.has_comp else None
        eq = [{"label": "Stated capital", "cy": amt("share_capital"), "py": amt("share_capital", "comparative") if self.has_comp else None}]
        if present("reserves"):
            eq.append({"label": "Reserves", "cy": amt("reserves"), "py": amt("reserves", "comparative") if self.has_comp else None})
        eq.append({"label": "Retained earnings", "cy": re_cy, "py": re_py})
        rows += [{"label": "EQUITY & LIABILITIES", "kind": "head"}] + eq
        eq_cy, eq_py = sum(x["cy"] for x in eq), (sum(x["py"] for x in eq) if self.has_comp else None)
        rows.append({"label": "", "cy": eq_cy, "py": eq_py, "kind": "total"})
        liab_total_cy, liab_total_py = ZERO, ZERO
        for title, items in (("Non-current liabilities", [("Borrowings", "borrowings_non_current"), ("Deferred tax", "deferred_tax")]),
                             ("Current liabilities", [("Trade and other payables", "trade_payables"), ("Income tax payable", "tax_payable"),
                                                      ("Shareholder's current account", "shareholder_current_account"), ("Borrowings", "borrowings_current"),
                                                      ("Other current liabilities", "other_current_liabilities")])):
            keep = [(lb, h) for lb, h in items if h in present(h)]
            if not keep:
                continue
            rows.append({"label": title, "kind": "head"})
            rows += [row(lb, h) for lb, h in keep]
            s_cy, s_py = sum(amt(h) for _, h in keep), sum(amt(h, "comparative") for _, h in keep)
            liab_total_cy += s_cy
            liab_total_py += s_py
            rows.append({"label": "", "cy": s_cy, "py": s_py if self.has_comp else None, "kind": "sub"})
        rows += [{"label": "Total liabilities", "cy": liab_total_cy, "py": liab_total_py if self.has_comp else None, "kind": "total"},
                 {"label": "Total equity & liabilities", "cy": eq_cy + liab_total_cy, "py": (eq_py + liab_total_py) if self.has_comp else None, "kind": "grand"}]
        sign = [Spacer(1, 16),
                self.P("I certify that these Financial Statements are in compliance with the requirements of the Companies Act No. 7 of 2007.", "body"),
                Spacer(1, 22), self.P(".................................<br/>Accountant", "body"), Spacer(1, 6), self.P("Date: ........................", "body"), Spacer(1, 12),
                self.P("The Board of Directors is responsible for the preparation and presentation of these Financial Statements.", "body"),
                self.P("Signed for and on behalf of the Board.", "body"), Spacer(1, 22),
                self.P(".................................&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;.................................<br/>"
                       "Director&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
                       "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Director", "body"), Spacer(1, 10)]
        return self.head("Statement of financial position", "sofp") + [self.P("(all amounts in Sri Lanka Rupees)", "small"), Spacer(1, 6),
                                                                       self.table(rows, f"As at {self.ye.day} {self.ye:%B}" if self.ye else "As at")] + sign + \
            [self.footer_line(), PageBreak()]

    def changes_in_equity(self):
        from reportlab.platypus import PageBreak, Spacer

        eq = self.dp.get("equity") or {}
        rows_in = eq.get("rows") or []
        with_reserves = any(_d(x.get("reserves")) for x in rows_in)
        header = ["", "Stated capital"] + (["Reserves"] if with_reserves else []) + ["Retained earnings", "Total"]
        rows = []
        for x in rows_in:
            label = {"Balance at the start of the year": f"Balance at {self.start_text}", "Balance at the end of the year": f"Balance at {self.ye_text}"}.get(
                x["label"], x["label"])
            rows.append([label, r(x["share_capital"]) if x.get("kind") else (r(x["share_capital"]) if _d(x["share_capital"]) else "Nil")] +
                        ([r(x["reserves"])] if with_reserves else []) + [r(x["retained_earnings"]), r(x["total"])])
        t = self.plain_table(header, rows, [70] + [30] * (len(header) - 1), bold_last=True, shade_col=None)
        return self.head("Statement of changes in equity", "soce") + [self.P("(all amounts in Sri Lanka Rupees)", "small"), Spacer(1, 10), t,
                                                                      Spacer(1, 30), self.footer_line(), PageBreak()]

    def cash_flow(self):
        from reportlab.platypus import PageBreak, Spacer

        cf = self.dp.get("cash_flows") or {}
        if not cf.get("available"):
            return self.head("Cash flow statement", "cf") + [self.P(escape(cf.get("reason", "")), "body"), PageBreak()]
        rows = []
        for sec in cf["sections"]:
            title = {"operating": "Operating activities", "investing": "Investing activities", "financing": "Financing activities"}[sec["key"]]
            rows.append({"label": title, "kind": "head"})
            # Zero lines are left out; the finance costs added back and the interest paid cancel, so neither is shown.
            items = [x for x in sec["rows"] if _d(x["amount"]) or x["label"] == "Profit before tax"]
            if sec["key"] == "operating":
                items = [x for x in items if x["label"] != "Finance costs"]
                sec = {**sec, "after": [x for x in sec.get("after") or [] if x["label"] != "Interest paid" and _d(x["amount"])]}
                rows.append({"label": items[0]["label"], "cy": items[0]["amount"]})
                adj = [x for x in items[1:] if not x["label"].startswith(("(Increase)", "Increase"))]
                wc = [x for x in items[1:] if x["label"].startswith(("(Increase)", "Increase"))]
                if adj:
                    rows.append({"label": "Adjustments", "kind": "head"})
                    rows += [{"label": x["label"], "cy": x["amount"], "indent": 0} for x in adj]
                rows += [{"label": x["label"], "cy": x["amount"]} for x in sec.get("after") or []]
                if wc:
                    rows.append({"label": "Changes in working capital", "kind": "head"})
                    rows += [{"label": x["label"].replace("(Increase) / decrease in ", "").replace("Increase / (decrease) in ", "").capitalize(), "cy": x["amount"]}
                             for x in wc]
            else:
                rows += [{"label": x["label"], "cy": x["amount"]} for x in items]
            rows.append({"label": sec["total"]["label"], "cy": sec["total"]["amount"], "kind": "total"})
        rows += [{"label": "Increase / (decrease) in cash and cash equivalents", "cy": cf["net_change"], "kind": "total"},
                 {"label": "Movement in cash and cash equivalents", "kind": "head"},
                 {"label": "At start of year", "cy": cf["opening_cash"]}, {"label": "Increase / (decrease)", "cy": cf["net_change"]},
                 {"label": "At end of year", "cy": cf["closing_cash"], "kind": "grand", "note": self.notes.get("cash", "")}]
        has = self.has_comp
        self.has_comp = False  # the comparative year's cash flows need the year before's balances
        t = self.table(rows, self._period())
        self.has_comp = has
        return self.head("Cash flow statement", "cf") + [self.P("(all amounts in Sri Lanka Rupees)", "small"), Spacer(1, 6), t, Spacer(1, 24),
                                                         self.footer_line(), PageBreak()]

    def policies(self):
        from reportlab.platypus import PageBreak

        e = self.e
        notes = self.dp.get("notes") or []
        pol = next((x["policies"] for x in notes if x["key"] == "policies"), [])
        out = self.head("Accounting policies", "policies")
        out.append(self.P("1&nbsp;&nbsp;&nbsp;Corporate information", "h"))
        out.append(self.P(escape(f"{e.get('legal_name') or '[Company]'} ({e.get('nic_or_reg') or '[registration no.]'}) is a company incorporated under the "
                                 f"Companies Act No. 07 of 2007 and domiciled in Sri Lanka. The registered and principal office of the Company is located at "
                                 f"{e.get('address') or '[address]'}."), "body"))
        out.append(self.P("Principal activities &amp; the nature of operations", "sub"))
        out.append(self.P(escape(e.get("activity") or "[Principal activities]"), "body"))
        out.append(self.P("Directors", "sub"))
        directors = (e.get("data") or {}).get("directors") or ""
        out.append(self.P(escape(f"The Directors present herewith the financial statements for the year ended {self.ye_text}. The Directors are responsible "
                                 "for preparing and presenting the financial statements.") + "<br/>" + escape(directors or "[Directors' names]"), "body"))
        for i, p in enumerate(pol, start=2):
            out.append(self.P(f"{i}&nbsp;&nbsp;&nbsp;{escape(p['title'])}", "h"))
            out.append(self.P(escape(p["text"]), "body"))
        marker = self.P("", "foot")
        marker._toc = "policies_end"
        return out + [marker, PageBreak()]

    def notes_pages(self):
        from reportlab.platypus import KeepTogether, Spacer

        fin = self.fin
        out = self.head("Notes to the financial statements", "notes")
        out.append(self.P("(In the notes all amounts are shown in Sri Lanka Rupees unless otherwise stated)", "small"))
        rows_by_heading = {row["heading"]: row for row in (fin.get("pl") or {}).get("rows") or []}
        labels = {"revenue": "Revenue", "cost_of_sales": "Cost of sales", "other_income": "Other income", "admin_expenses": "Administrative expenses",
                  "distribution_expenses": "Distribution expenses", "finance_costs": "Finance & other costs", "ppe": "Property, plant and equipment",
                  "intangibles": "Intangible assets", "investments": "Investments", "other_non_current_assets": "Other non-current assets",
                  "inventories": "Inventories", "trade_receivables": "Trade and other receivables", "other_current_assets": "Other current assets",
                  "cash": "Cash and cash equivalents", "borrowings_non_current": "Non-current borrowings", "trade_payables": "Trade and other payables",
                  "borrowings_current": "Current borrowings", "other_current_liabilities": "Other current liabilities"}
        for h, no in self.notes.items():
            if h in rows_by_heading:
                row = rows_by_heading[h]
                sign = -1 if row["kind"] == "income" else 1
                lines = [(ln["name"], sign * _d(ln["amount"]), sign * _d(ln["comparative"]) if ln.get("comparative") is not None else None) for ln in row["lines"]]
                total = (row["amount"], row["comparative"])
            else:
                v = fin["bs"][h]
                sign = -1 if v["kind"] in ("equity", "liability") else 1
                if h == "ppe":
                    block = self.ppe_note(v)
                    if block:
                        out.append(KeepTogether([self.P(f"{no}&nbsp;&nbsp;&nbsp;{labels[h]}", "h"), block]))
                        continue
                lines = [(ln["name"], sign * _d(ln["amount"]), sign * _d(ln["comparative"]) if ln.get("comparative") is not None else None) for ln in v["lines"]]
                total = (v["amount"], v["comparative"])
            header = ["", self.cy] + ([self.py] if self.has_comp else [])
            body = [[name, r(a)] + ([r(c)] if self.has_comp else []) for name, a, c in lines] + [["", r(total[0])] + ([r(total[1])] if self.has_comp else [])]
            out.append(KeepTogether([self.P(f"{no}&nbsp;&nbsp;&nbsp;{labels[h]}", "h"),
                                     self.plain_table(header, body, [100, 32] + ([32] if self.has_comp else []), bold_last=True)]))
        n = self.next_note
        texts = (self.e.get("data") or {}).get("note_text") or {}
        defaults = {"contingencies": "[To be confirmed by the accountant] There were no material contingent liabilities outstanding at the statement of "
                                     "financial position date.",
                    "commitments": "[To be confirmed by the accountant] There were no material capital and financial commitments outstanding at the "
                                   "statement of financial position date.",
                    "events": "[To be confirmed by the accountant] No events have occurred since the statement of financial position date which would "
                              "require adjustments to, or disclosure in, the financial statements."}
        for key, title in (("commitments", "Commitments"), ("contingencies", "Contingent liabilities"), ("events", "Events after the end of reporting date"),
                           ("related", "Related party transactions")):
            if key == "related" and not texts.get(key):
                continue
            if not self.full and key in ("commitments", "contingencies"):
                continue
            out += [self.P(f"{n}&nbsp;&nbsp;&nbsp;{title}", "h"), self.P(escape(texts.get(key) or defaults[key]), "body")]
            n += 1
        marker = self.P("", "foot")
        marker._toc = "notes_end"
        return out + [Spacer(1, 6), marker]

    def ppe_note(self, v):
        """Cost, accumulated depreciation and the year's movement, by class, from the PPE accounts (cost accounts and
        their accumulated depreciation accounts); None when the accounts can't be paired into classes."""
        classes: dict[str, dict] = {}
        for ln in v["lines"]:
            name = ln["name"]
            dep = bool(re.search(r"accum|acc\.|depreciation|provision for dep", name, re.I))
            key = re.sub(r"(?i)\b(accumulated|acc\.?|provision for|depreciation|at cost|cost|on|of|-|–|\(|\))\b", " ", name)
            key = " ".join(re.sub(r"[^A-Za-z& ]", " ", key).split()).title() or "Other"
            c = classes.setdefault(key, {"cost": ZERO, "dep": ZERO, "cost_p": ZERO, "dep_p": ZERO})
            c["dep" if dep else "cost"] += _d(ln["amount"])
            c["dep_p" if dep else "cost_p"] += _d(ln.get("comparative"))
        if not classes or len(classes) > 5 or not any(c["dep"] for c in classes.values()):
            return None
        names = list(classes)
        cols = names + (["Total"] if len(names) > 1 else [])

        def vals(fn):
            xs = [fn(classes[k]) for k in names]
            return [r(x) for x in xs] + ([r(sum(xs, ZERO))] if len(names) > 1 else [])

        rows = []
        if self.has_comp:
            rows += [[f"At {self.ye.day if self.ye else ''} {self.ye:%B} {self.py}" if self.ye else "At the start of the year"] + [""] * len(cols),
                     ["Cost"] + vals(lambda c: c["cost_p"]), ["Accumulated depreciation"] + vals(lambda c: c["dep_p"]),
                     ["Net book amount"] + vals(lambda c: c["cost_p"] + c["dep_p"]),
                     [f"Year ended {self.ye_text}"] + [""] * len(cols),
                     ["Opening balance"] + vals(lambda c: c["cost_p"] + c["dep_p"]),
                     ["Additions / (disposals) at cost"] + vals(lambda c: c["cost"] - c["cost_p"]),
                     ["Depreciation charge"] + vals(lambda c: c["dep"] - c["dep_p"]),
                     ["Closing net book amount"] + vals(lambda c: c["cost"] + c["dep"])]
        rows += [[f"At {self.ye_text}"] + [""] * len(cols), ["Cost"] + vals(lambda c: c["cost"]),
                 ["Accumulated depreciation"] + vals(lambda c: c["dep"]), ["Net book amount"] + vals(lambda c: c["cost"] + c["dep"])]
        width = max(18.0, 100.0 / len(cols))
        return self.plain_table([""] + cols, rows, [62] + [width] * len(cols), bold_last=True, shade_col=None)

    # --- the document ------------------------------------------------------------------------------------------------
    def story(self):
        out = self.cover() + self.contents()
        if self.e.get("audited"):
            out += self.auditor()
        out += self.income_statement()
        if self.full:
            out += self.financial_position() + self.changes_in_equity() + self.cash_flow()
        out += self.policies() + self.notes_pages()
        return out

    def build(self) -> bytes:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate

        report = self

        class Doc(SimpleDocTemplate):
            def afterFlowable(self, flowable):
                key = getattr(flowable, "_toc", None)
                if key:
                    report.pages[key] = self.page

        def page(canvas, doc):
            canvas.saveState()
            if doc.page > 1:
                canvas.setFont("Helvetica", 8)
                canvas.drawRightString(194 * mm, 287 * mm, f"Page {doc.page}")
            a = report.pages.get("auditor", 0)
            in_report = a and a <= doc.page <= report.pages.get("auditor_end", a)
            if doc.page > 2 and not in_report:
                canvas.setFont("Helvetica-Bold", 10.5)
                canvas.drawString(18 * mm, 284 * mm, report.name)
            if report.draft:
                canvas.setFont("Helvetica-Bold", 7)
                canvas.setFillColorRGB(0.7, 0.14, 0.1)
                canvas.drawString(18 * mm, 8 * mm, "DRAFT - prepared in TASKO's Local Tax workflow; not approved")
            canvas.restoreState()

        for _ in range(2):  # the first pass finds each part's page for the contents and the footers
            buf = io.BytesIO()
            Doc(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=16 * mm, topMargin=18 * mm, bottomMargin=16 * mm,
                title=f"{self.name} - Financial statements", author="TASKO Local Tax workflow").build(self.story(), onFirstPage=page, onLaterPages=page)
        return buf.getvalue()


def render(st: dict) -> bytes:
    """The financial statements as a PDF in AFIT's house format."""
    return _Report(st).build()
