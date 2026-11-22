"""The Local Tax workflow's documents (AFIT, 22 Nov 2026): the financial statements, the tax computation and the
draft return, as PDF (reportlab) and Excel (openpyxl), from the engine's figures. Every page says DRAFT and which
rules still need professional validation; the draft return says it is for entry into RAMIS, not submitted."""
import io
from decimal import Decimal

from django.utils import timezone

MAROON = "#800000"
FRAMEWORK = {"full": "Full LKAS/SLFRS", "smes": "SLFRS for SMEs", "smaller": "SLAS for Smaller Entities"}


def _m(v) -> str:
    if v in (None, ""):
        return ""
    n = Decimal(str(v))
    return f"({abs(n):,.2f})" if n < 0 else f"{n:,.2f}"


def _rows(doc: str, eng, st: dict) -> tuple[str, list[tuple[str, list[list], list[str]]]]:
    """(title, [(section title, rows, header)]): the document as tables, shared by the PDF and the workbook."""
    e = st["engagement"]
    if doc == "fs":
        fin = st.get("financials")
        if not fin:
            return "Financial statements", [("Not ready", [["Upload or enter the trial balance first."]], ["Note"])]
        if fin.get("kind") == "individual":
            rows = []
            for s in fin["sources"]:
                rows.append([f"{s['category'].replace('_', ' ').title()}: {s['description']}", _m(s["income"]), "", ""])
                for x in s["expenses"]:
                    rows.append([f"   Less: {x['description']} ({x['classification']})", "", _m(-x["amount"]), ""])
                rows.append(["   Net", "", "", _m(s["net"])])
            rows.append(["Total net income", _m(fin["total_income"]), _m(-fin["total_expenses"]), _m(fin["net"])])
            return "Statement of income and expenses", [("By income source", rows, ["Item", "Income", "Expenses", "Net"])]
        cur, comp = fin["pl"]["current"], fin["pl"].get("comparative") or {}
        pl_keys = [("revenue", "Revenue", 1), ("cost_of_sales", "Cost of sales", -1), ("gross_profit", "Gross profit", 1), ("other_income", "Other income", 1),
                   ("admin_expenses", "Administrative expenses", -1), ("distribution_expenses", "Selling and distribution expenses", -1),
                   ("finance_costs", "Finance costs", -1), ("pbt", "Profit before tax", 1), ("income_tax_expense", "Income tax expense", -1),
                   ("profit", "Profit for the year", 1), ("oci", "Other comprehensive income", 1), ("total_comprehensive_income", "Total comprehensive income", 1)]
        pl = [[label, _m(sign * cur[k]), _m(sign * comp[k]) if comp else ""] for k, label, sign in pl_keys if cur.get(k) or k in ("pbt", "profit")]
        bs = []
        for kind, title in (("asset", "Assets"), ("equity", "Equity"), ("liability", "Liabilities")):
            bs.append([title, "", ""])
            for h, v in fin["bs"].items():
                if v["kind"] == kind and (v["amount"] or v["comparative"]):
                    bs.append([f"   {v['label']}", _m(v["amount"]), _m(v["comparative"]) if v["comparative"] is not None else ""])
            if kind == "equity":
                bs.append(["   Profit for the year", _m(cur["total_comprehensive_income"]), ""])
        t = fin["totals"]
        bs += [["Total assets", _m(t["assets"]), ""], ["Total equity and liabilities", _m(t["equity"] + t["liabilities"]), ""]]
        checks = [[c["label"], "Passed" if c["passed"] else f"Difference {_m(c['difference'])}"] for c in fin["checks"]]
        year = e.get("fy_end") or ""
        sections = [
            (f"Statement of profit or loss and other comprehensive income (year ended {year})", pl, ["", "Current year (LKR)", "Comparative (LKR)"]),
            (f"Statement of financial position (as at {year})", bs, ["", "Current year (LKR)", "Comparative (LKR)"])]
        sections += depth_sections(st.get("statements") or {}, year)
        sections.append(("Checks", checks, ["Check", "Result"]))
        return "Financial statements", sections
    if doc == "computation":
        comp = st.get("computation")
        if not comp:
            return "Income tax computation", [("Not ready", [[a["text"]] for a in st["alerts"] if a["stage"] == "computation"], ["Note"])]
        rows = [[("   " * ln["level"]) + ln["label"], _m(ln["amount"]) if ln["amount"] is not None else "", ln["note"]] for ln in comp["lines"]]
        rules = [[r["rule"], r["ref"], "Validated" if r["validated"] else "REQUIRES VALIDATION"] for r in comp["rules"]]
        sections = [(f"Income tax computation - YA {e['year_of_assessment']}", rows, ["Description", "Amount (LKR)", "Note"]),
                    ("Rules applied", rules, ["Rule", "Reference", "Status"])]
        far = comp.get("capital_allowance_schedule")
        if far and far.get("rows"):
            sections.append(("Capital allowance schedule (fixed asset register)", [
                [r["description"], r["label"], _m(r["cost"]), _m(r["wdv_bf"]), _m(r["allowance"]),
                 _m(r["balancing_charge"] - r["balancing_allowance"]) if r["disposed"] else "", _m(r["wdv_cf"])] for r in far["rows"]] + [
                ["Total", "", _m(far["totals"]["cost"]), "", _m(far["totals"]["allowance"]),
                 _m(far["totals"]["balancing_charge"] - far["totals"]["balancing_allowance"]), _m(far["totals"]["wdv_cf"])]],
                ["Asset", "Class", "Cost", "Tax WDV b/f", "Allowance", "Balancing charge / (allowance)", "Tax WDV c/f"]))
        ls = comp.get("loss_schedule")
        if ls and ls.get("rows"):
            sections.append(("Tax loss schedule", [[r["ya"], _m(r["bf"]), _m(r["utilised"]), _m(r["cf"])] for r in ls["rows"]] +
                             [["Total", _m(ls["totals"]["bf"]), _m(ls["totals"]["utilised"]), _m(ls["totals"]["cf"])]],
                             ["Year of assessment", "Brought forward", "Utilised", "Carried forward"]))
        rev = st.get("reverse")
        if rev:
            sections.append(("Expected vs calculated tax", [["Expected tax", _m(rev["expected"])], ["Calculated tax", _m(rev["calculated"])],
                                                            ["Difference", _m(rev["variance"])],
                                                            ["Taxable income needed for the expected tax", _m(rev["required_taxable_income"]) or "Not reachable"]],
                             ["", "LKR"]))
        return "Income tax computation", sections
    ret = st.get("return")
    if not ret:
        return "Draft income tax return", [("Not ready", [["Complete the tax computation first."]], ["Note"])]
    sections = [(s["title"], [[f.get("official") or f"{f['code']}*", f["label"], _m(f["value"]) if f["kind"] == "amount" else (f["value"] or ""),
                               "MISSING" if f["missing"] else ""] for f in s["fields"]], ["Ref", "Field", "Value", ""]) for s in ret["sections"]]
    return "Draft income tax return", sections


def render(doc: str, fmt: str, eng, st: dict) -> tuple[bytes, str]:
    title, sections = _rows(doc, eng, st)
    e = st["engagement"]
    base = f"{e['legal_name'] or eng.issue.key} - {title} - YA {e['year_of_assessment'].replace('/', '-')}"
    if fmt == "xlsx":
        return _xlsx(title, sections, e), f"{base}.xlsx"
    return _pdf(title, sections, e, st, doc), f"{base}.pdf"


def _xlsx(title: str, sections, e) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append([f"{e['legal_name']} - {title}"])
    ws["A1"].font = Font(bold=True, size=14, color="800000")
    ws.append([f"TIN {e['tin']} | YA {e['year_of_assessment']} | DRAFT - prepared by TASKO's Local Tax workflow; rules require professional validation"])
    for sec_title, rows, header in sections:
        ws.append([])
        ws.append([sec_title])
        ws.cell(ws.max_row, 1).font = Font(bold=True, size=12)
        ws.append(header)
        for c in ws[ws.max_row]:
            c.font, c.fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="800000")
        for r in rows:
            ws.append([_num(v) for v in r])
    ws.column_dimensions["A"].width = 60
    for col in "BCD":
        ws.column_dimensions[col].width = 22
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _num(v):
    """A money string back to a number for Excel (brackets negative); other text as it is."""
    if isinstance(v, str) and v and v.replace(",", "").replace(".", "").replace("(", "").replace(")", "").replace("-", "").isdigit():
        neg = v.startswith("(")
        n = float(v.strip("()").replace(",", ""))
        return -n if neg else n
    return v


def _pdf(title: str, sections, e, st: dict, doc: str) -> bytes:
    from xml.sax.saxutils import escape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()

    def stamp(canvas, _doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(16 * mm, 9 * mm, f"DRAFT - {e['legal_name']} - TIN {e['tin']} - YA {e['year_of_assessment']} - prepared "
                                          f"{timezone.localtime():%d %b %Y} - rules and return references require professional validation")
        canvas.drawRightString(194 * mm, 9 * mm, f"Page {canvas.getPageNumber()}")
        canvas.restoreState()

    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=16 * mm, bottomMargin=16 * mm, title=title,
                            author="TASKO Local Tax workflow")
    styles = getSampleStyleSheet()
    styles["Title"].textColor = colors.HexColor(MAROON)
    story = [Paragraph(escape(e["legal_name"] or ""), styles["Title"]), Paragraph(escape(title), styles["Heading2"]),
             Paragraph(f"TIN {escape(e['tin'] or '-')} &nbsp;|&nbsp; Year of assessment {escape(e['year_of_assessment'])} &nbsp;|&nbsp; "
                       f"{escape(FRAMEWORK.get(e.get('reporting_framework'), ''))} &nbsp;|&nbsp; "
                       f"{'Audited' if e.get('audited') else 'Unaudited'}", styles["Normal"]), Spacer(1, 4 * mm)]
    if doc == "return":
        checked = (st.get("return") or {}).get("validated")
        story.append(Paragraph("<b>DRAFT for accountant review.</b> Prepared for entry into RAMIS by the accountant; not submitted. " +
                               ("Every field reference has been checked against the year's RAMIS return." if checked else
                                "Field references marked * are placeholders to be checked against the year's RAMIS return."), styles["Normal"]))
        story.append(Spacer(1, 3 * mm))
    for sec_title, rows, header in sections:
        story.append(Paragraph(escape(sec_title), styles["Heading3"]))
        table = Table([header] + [[Paragraph(escape(str(c)), styles["BodyText"]) if i == 0 or len(str(c)) > 40 else escape(str(c))
                                   for i, c in enumerate(r)] for r in rows], repeatRows=1, hAlign="LEFT",
                      colWidths={3: [95 * mm, 40 * mm, 43 * mm], 2: [62 * mm, 116 * mm]}.get(len(header)))
        style = [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(MAROON)), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                 ("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                 ("ALIGN", (1, 1), (-1, -1), "RIGHT"), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        for n, r in enumerate(rows, start=1):
            first = str(r[0]).strip().lower()
            if first.startswith(("total", "taxable income", "final tax", "tax refundable", "profit", "gross profit", "income tax")):
                style.append(("BACKGROUND", (0, n), (-1, n), colors.HexColor("#f6e7e7")))
                style.append(("FONTNAME", (0, n), (-1, n), "Helvetica-Bold"))
            if "MISSING" in [str(c) for c in r]:
                style.append(("TEXTCOLOR", (0, n), (-1, n), colors.HexColor("#b42318")))
        table.setStyle(TableStyle(style))
        story += [table, Spacer(1, 5 * mm)]
    pdf.build(story, onFirstPage=stamp, onLaterPages=stamp)
    return buf.getvalue()



def depth_sections(dp: dict, year: str) -> list:
    """Phase 3: the statement of changes in equity, cash flows, notes, policies and the draft audit report."""
    out = []
    eq = dp.get("equity")
    if eq:
        out.append((f"Statement of changes in equity (year ended {year})",
                    [[r["label"], _m(r["share_capital"]), _m(r["reserves"]), _m(r["retained_earnings"]), _m(r["total"])] for r in eq["rows"]],
                    ["", "Stated capital", "Reserves", "Retained earnings", "Total"]))
    cf = dp.get("cash_flows")
    if cf and cf.get("available"):
        rows = []
        for sec in cf["sections"]:
            rows.append([sec["title"], ""])
            rows += [[f"   {r['label']}", _m(r["amount"])] for r in sec["rows"]]
            if sec.get("subtotal"):
                rows.append([sec["subtotal"]["label"], _m(sec["subtotal"]["amount"])])
            rows += [[f"   {r['label']}", _m(r["amount"])] for r in sec.get("after") or []]
            rows.append([sec["total"]["label"], _m(sec["total"]["amount"])])
        rows += [["Net increase / (decrease) in cash", _m(cf["net_change"])], ["Cash at the start of the year", _m(cf["opening_cash"])],
                 ["Cash at the end of the year", _m(cf["closing_cash"])]]
        out.append((f"Statement of cash flows (year ended {year})", rows, ["", "LKR"]))
    elif cf:
        out.append(("Statement of cash flows", [[cf.get("reason", "")]], ["Note"]))
    for n in dp.get("notes") or []:
        if n.get("policies"):
            out.append((f"{n['no']}. {n['title']}", [[p["title"], p["text"]] for p in n["policies"]], ["Policy", "Text"]))
        elif n.get("lines"):
            out.append((f"{n['no']}. {n['title']}", [[f"{ln['code']} {ln['name']}", _m(ln["amount"]),
                                                      _m(ln["comparative"]) if ln["comparative"] is not None else ""] for ln in n["lines"]] +
                        [["Total", _m(n["total"]), _m(n["total_comparative"]) if n["total_comparative"] is not None else ""]],
                        ["Account", "Current year", "Comparative"]))
        elif n.get("rows"):
            out.append((f"{n['no']}. {n['title']}", [[r["label"], _m(r["amount"])] for r in n["rows"]], ["", "LKR"]))
        else:
            out.append((f"{n['no']}. {n['title']}", [[n.get("text", "")]], ["Note"]))
    ar = dp.get("audit_report")
    if ar:
        out.append((f"{ar['title']} - {ar['label']}", [[ar["addressee"], ""]] + [[x["title"], x["text"]] for x in ar["sections"]] +
                    [["Signed", ar["signature"]]], ["Section", "Text"]))
    return out
