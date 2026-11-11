"""The workpaper: an editable Excel workbook, formatted as a professional workpaper file (AFIT, 9 Nov 2026).

The first sheet follows the firm's CCH "L1 GST reconciliation" layout (Output.pdf); the supporting
schedules follow it, one sheet each, every one with the same workpaper header (firm, client, title,
reference, balance date, prepared/reviewed sign-off). Conventions: amounts in the accounting format
(negatives in brackets, nil as a dash), figures taken from the documents in blue and formulas in
black, reviewer-input cells shaded; totals ruled single above and double below; A4 landscape, fitted
to the page width, headings repeated on each printed page, page numbers in the footer.

GST payable is positive on every sheet except L1's "(Payment) / refund" column, which keeps the
template's sign."""
import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

# --- the house style ---------------------------------------------------------------------------------
FONT = "Calibri"
MAROON, GREY, LIGHT, ZEBRA, INPUT = "800000", "595959", "F2F2F2", "FAFAFA", "FFF8E1"
MONEY = '#,##0.00_);(#,##0.00);"-"_)'
DATE = "DD/MM/YYYY"
HAIR = Side(style="hair", color="BFBFBF")
THIN = Side(style="thin", color="7F7F7F")
DARK = Side(style="thin", color="000000")
DOUBLE = Side(style="double", color="000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
ROW_LINE = Border(bottom=HAIR)
TOTAL_RULE = Border(top=DARK, bottom=DOUBLE)
SUB_RULE = Border(top=DARK)
F_BASE = Font(name=FONT, size=10)
F_BOLD = Font(name=FONT, size=10, bold=True)
F_SMALL = Font(name=FONT, size=8, color=GREY)
F_NOTE = Font(name=FONT, size=9, italic=True, color=GREY)
F_TITLE = Font(name=FONT, size=16, bold=True, color=MAROON)
F_CLIENT = Font(name=FONT, size=12, bold=True)
F_FIRM = Font(name=FONT, size=9, bold=True, color=GREY)
F_REF = Font(name=FONT, size=20, bold=True, color=MAROON)
F_HEAD = Font(name=FONT, size=10, bold=True, color="FFFFFF")
F_INPUT = Font(name=FONT, size=10, color="0000CC")  # taken from the documents
F_SECTION = Font(name=FONT, size=11, bold=True, color=MAROON)
FILL_HEAD = PatternFill("solid", fgColor=MAROON)
FILL_BAR = PatternFill("solid", fgColor=LIGHT)
FILL_ZEBRA = PatternFill("solid", fgColor=ZEBRA)
FILL_INPUT = PatternFill("solid", fgColor=INPUT)
STATUS_FILL = {"Reconciled": "E2EFDA", "Reconciled subject to corrections": "FFF2CC", "Unreconciled": "FCE4D6", "Incomplete evidence": "FCE4D6"}
STATUS_FONT = {"Reconciled": "375623", "Reconciled subject to corrections": "7F6000", "Unreconciled": "9C0006", "Incomplete evidence": "9C0006"}
FREQ = {"monthly": "Monthly", "two_monthly": "2 monthly", "six_monthly": "6 monthly"}
BASIS = {"payments": "Payments", "invoice": "Invoice", "hybrid": "Hybrid"}
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
WRAP = Alignment(wrap_text=True, vertical="top")
RIGHT = Alignment(horizontal="right", vertical="top")


def _v(value):
    """A value for a cell: Decimals and dates as Excel numbers and dates."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _put(ws, ref, value, *, fmt=None, font=None, fill=None, border=None, align=None):
    c = ws[ref]
    c.value = _v(value)
    c.font = font or F_BASE
    if fmt:
        c.number_format = fmt
    if fill:
        c.fill = fill
    if border:
        c.border = border
    if align:
        c.alignment = align
    return c


def _money(ws, ref, value, *, font=None, border=None, fill=None):
    """An amount: blue when typed in from the documents, black for a formula."""
    is_formula = isinstance(value, str) and value.startswith("=")
    return _put(ws, ref, value, fmt=MONEY, font=font or (F_BASE if is_formula else F_INPUT), border=border, fill=fill,
                align=Alignment(horizontal="right", vertical="center"))


def _print_setup(ws, title_rows: str | None = None, landscape: bool = True):
    ws.sheet_view.showGridLines = False
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_margins = PageMargins(left=0.4, right=0.4, top=0.6, bottom=0.6, header=0.3, footer=0.3)
    ws.print_options.horizontalCentered = True
    if title_rows:
        ws.print_title_rows = title_rows
    ws.oddFooter.left.text = "&8&A"
    ws.oddFooter.right.text = "&8Page &P of &N"
    ws.oddFooter.center.text = "&8Prepared by the WP Agent for review"


def header(ws, su, meta, title: str, ref: str, last_col: int, note: str = "") -> int:
    """The workpaper header on every sheet. Returns the first free row."""
    last = get_column_letter(last_col)
    left = get_column_letter(max(last_col - 2, 2))
    _put(ws, "A1", su.firm, font=F_FIRM)
    _put(ws, "A2", su.entity or "Client", font=F_CLIENT)
    _put(ws, "A3", title, font=F_TITLE)
    _put(ws, "A4", note or f"Balance date {su.balance_date:%d %B %Y} · {BASIS.get(su.basis, su.basis)} basis · {FREQ.get(su.frequency, su.frequency)}",
         font=F_NOTE)
    _put(ws, f"{last}1", ref, font=F_REF, align=Alignment(horizontal="right", vertical="top"))
    ws.merge_cells(f"{last}1:{last}2")
    rows = [("Balance date", su.balance_date, DATE), ("Prepared by", f"{su.prepared_by or 'WP Agent'} · {meta['prep_date']:%d/%m/%Y}", None),
            ("Reviewed by", "", None)]
    for i, (label, value, fmt) in enumerate(rows, start=2):
        _put(ws, f"{left}{i + 1}", label, font=F_SMALL, align=Alignment(horizontal="right"))
        c = _put(ws, f"{last}{i + 1}", value, fmt=fmt, font=F_BOLD if label != "Reviewed by" else F_BASE,
                 border=Border(bottom=THIN), fill=FILL_INPUT if label == "Reviewed by" else None, align=Alignment(horizontal="left"))
        c.number_format = fmt or "@"
    for col in range(1, last_col + 1):
        ws.cell(row=5, column=col).border = Border(bottom=Side(style="medium", color=MAROON))
    ws.row_dimensions[3].height = 22
    return 7


def _bar(ws, row: int, text: str, last: str = "L"):
    for col in range(1, ws[f"{last}1"].column + 1):
        ws.cell(row=row, column=col).fill = FILL_BAR
        ws.cell(row=row, column=col).border = Border(top=THIN, bottom=THIN)
    _put(ws, f"A{row}", text, font=F_SECTION, fill=FILL_BAR, border=Border(top=THIN, bottom=THIN))
    ws.row_dimensions[row].height = 18


# --- L1: the CCH GST reconciliation layout ---------------------------------------------------------------

def l1_sheet(wb: Workbook, r: dict, su, meta: dict) -> None:
    ws = wb.active
    ws.title = "L1 GST reconciliation"
    ws.sheet_properties.tabColor = MAROON
    widths = {"A": 34, "B": 13, "C": 13, "D": 13, "E": 13, "F": 13, "G": 13, "H": 13, "I": 13, "J": 15, "K": 13, "L": 16}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    # The template's header (rows 1-5), with the sign-off boxes on the right.
    _put(ws, "A1", su.firm, font=F_FIRM)
    _put(ws, "A2", su.entity or "Client Name", font=F_CLIENT)
    _put(ws, "A3", "GST reconciliation", font=F_TITLE)
    _put(ws, "L1", "L1", font=F_REF, align=Alignment(horizontal="right", vertical="top"))
    ws.merge_cells("L1:L2")
    _put(ws, "J1", "Prep Date:", font=F_SMALL, align=Alignment(horizontal="right"))
    _put(ws, "K1", meta["prep_date"], fmt=DATE, font=F_BOLD)
    _put(ws, "J2", "Balance Date:", font=F_SMALL, align=Alignment(horizontal="right"))
    _put(ws, "K2", su.balance_date, fmt=DATE, font=F_BOLD)
    _put(ws, "A4", f"Prepared By: {su.prepared_by or 'WP Agent'}", font=F_SMALL)
    _put(ws, "D4", "Reviewed By:", font=F_SMALL, align=Alignment(horizontal="right"))
    _put(ws, "E4", "", fill=FILL_INPUT, border=Border(bottom=THIN))
    ws.merge_cells("E4:F4")
    _put(ws, "A5", f"Status: {r['status']}. GST payable shown positive (except the (Payment) / refund column). Figures from the documents in blue; "
                   f"formulas in black. Run {meta['run_id'][:8]}.", font=F_NOTE)
    for col in range(1, 13):
        ws.cell(row=5, column=col).border = Border(bottom=Side(style="medium", color=MAROON))
    _put(ws, "A6", "Accounting basis", font=F_BOLD, border=BOX, fill=FILL_BAR)
    _put(ws, "B6", BASIS.get(su.basis, su.basis), border=BOX, align=Alignment(horizontal="center"))
    ws.merge_cells("B6:C6")
    _put(ws, "A7", "Period", font=F_BOLD, border=BOX, fill=FILL_BAR)
    _put(ws, "B7", FREQ.get(su.frequency, su.frequency), border=BOX, align=Alignment(horizontal="center"))
    ws.merge_cells("B7:C7")

    _bar(ws, 9, "GST return information")
    heads = ["Period ended", "Total outputs", "Output tax", "Prior year adjustments", "Box 9 adjustments", "Total inputs", "Input tax",
             "Prior year adjustments", "Box 13 adjustments", "(Payment) / refund", "Paid/rec'd @ bal date"]
    for i, h in enumerate(heads, start=1):
        c = ws.cell(row=11, column=i, value=h)
        c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BOX, CENTER
    ws.row_dimensions[11].height = 30
    row = first = 12
    periods = [p for p in r["periods"] if not p["prior_year"] and p["period_end"] <= su.balance_date and p["origin"] == "return"]
    for n, p in enumerate(periods):
        fill = FILL_ZEBRA if n % 2 else None
        _put(ws, f"A{row}", p["period_end"], fmt=DATE, border=BOX, fill=fill, align=Alignment(horizontal="center"))
        for col, key in (("B", "total_sales"), ("C", "output"), ("E", "box9"), ("F", "total_purchases"), ("G", "input"), ("I", "box13")):
            _money(ws, f"{col}{row}", p.get(key) or 0, border=BOX, fill=fill)
        _money(ws, f"D{row}", 0, border=BOX, fill=fill)
        _money(ws, f"H{row}", 0, border=BOX, fill=fill)
        _money(ws, f"J{row}", f"=(G{row}+H{row}+I{row})-(C{row}+D{row}+E{row})", border=BOX, fill=fill)
        _put(ws, f"K{row}", p["paid_at_bd"], border=BOX, fill=fill, align=Alignment(horizontal="center"))
        row += 1
    last = max(row - 1, first)
    if row == first:
        row += 1
    totals = row + 1
    _put(ws, f"A{totals}", "Totals", font=F_BOLD, align=Alignment(horizontal="right"))
    for col in "BCDEFGHIJ":
        _money(ws, f"{col}{totals}", f"=SUM({col}{first}:{col}{last})", font=F_BOLD, border=TOTAL_RULE)
    a = r["analysis"]["year"]
    gl = totals + 2
    _put(ws, f"B{gl}", "GL output tax", align=Alignment(horizontal="right"))
    _money(ws, f"C{gl}", a["gl_output"], border=BOX)
    _put(ws, f"F{gl}", "GL input tax", align=Alignment(horizontal="right"))
    _money(ws, f"G{gl}", a["gl_input"], border=BOX)
    _put(ws, f"I{gl}", "Include variance in total?(y/n)", align=Alignment(horizontal="right"))
    _put(ws, f"K{gl}", "n", border=BOX, fill=FILL_INPUT, align=Alignment(horizontal="center"))
    var = gl + 2
    _put(ws, f"B{var}", "Variance", font=F_BOLD, align=Alignment(horizontal="right"))
    _money(ws, f"C{var}", f"=C{gl}-(C{totals}+D{totals}+E{totals})", border=TOTAL_RULE)
    _money(ws, f"G{var}", f"=G{gl}-(G{totals}+H{totals}+I{totals})", border=TOTAL_RULE)
    _money(ws, f"J{var}", f"=C{var}-G{var}", border=TOTAL_RULE)

    led = var + 2
    _bar(ws, led, "GST ledger information")
    lr = led + 1
    for acc in r["ledger"]["accounts"] or []:
        _put(ws, f"A{lr}", f"{acc.get('code') or ''} {acc['account']}".strip())
        _money(ws, f"J{lr}", -acc["balance"], border=BOX)
        _put(ws, f"K{lr}", acc["source"], font=F_SMALL)
        lr += 1
    _put(ws, f"A{lr}", f"Reported GST control balance (per {r['ledger']['how'] or 'not found'})", font=F_BOLD)
    _money(ws, f"J{lr}", r["bridge"]["reported"] if r["bridge"]["reported"] is not None else 0, font=Font(name=FONT, size=10, bold=True, color="0000CC"),
           border=BOX)
    ledger_cell = f"J{lr}"

    t = lr + 2
    _bar(ws, t, "Timing differences")
    _put(ws, f"I{t + 1}", "Ref", font=F_BOLD, align=Alignment(horizontal="center"))
    _put(ws, f"J{t + 1}", "$", font=F_BOLD, align=Alignment(horizontal="right"))
    b = r["bridge"]
    lines = [
        ("GST returns still outstanding at balance date", "L1.1", b["A_current"]),
        ("GST returns outstanding from prior year periods", "L1.1", b["A_prior"]),
        ("Accounts receivable per", "G1", b["B"]),
        ("Accounts payable per", "M1", -b["C"]),
        ("Unprocessed payments", "F1-10", 0),
        ("Unprocessed receipts", "F1-10", 0),
        ("GST on income (outputs) since last return", "", 0),
        ("GST on expenses (inputs) since last return", "", 0),
        ("Cash on hand (payments basis only)", "", 0),
        ("Income in advance", "", 0),
    ]
    row = first_timing = t + 2
    for label, ref, value in lines:
        _put(ws, f"A{row}", label, border=ROW_LINE)
        for col in "BCDEFGH":
            ws[f"{col}{row}"].border = ROW_LINE
        _put(ws, f"I{row}", ref, font=F_BOLD, align=Alignment(horizontal="center"), border=ROW_LINE)
        manual = label in ("Unprocessed payments", "Unprocessed receipts") or not ref
        _money(ws, f"J{row}", value, border=BOX, fill=FILL_INPUT if manual else None)
        if label == "Unprocessed payments":
            _put(ws, f"C{row}", "Include unprocessed payments and receipts in total?(y/n)", font=F_SMALL)
            _put(ws, f"H{row}", "y", border=BOX, fill=FILL_INPUT, align=Alignment(horizontal="center"))
        row += 1
    _put(ws, f"A{row}", "Total timing differences", font=F_BOLD)
    _money(ws, f"J{row}", f"=SUM(J{first_timing}:J{first_timing + 3})+IF(H{first_timing + 4}=\"y\",J{first_timing + 4}+J{first_timing + 5},0)"
                          f"+SUM(J{first_timing + 6}:J{row - 1})", font=F_BOLD, border=SUB_RULE)
    timing_total = f"J{row}"

    adj = row + 2
    _bar(ws, adj, "Adjustments required")
    for col, text, align in (("B", "Narration", "left"), ("I", "Ref", "center"), ("J", "$", "right")):
        _put(ws, f"{col}{adj + 1}", text, font=F_BOLD, align=Alignment(horizontal=align), border=Border(bottom=DARK))
    row = first_adj = adj + 2
    by_cat: dict[str, list[dict]] = {}
    for item in r["adjustments"]:
        if item.get("included", True):
            by_cat.setdefault(item["category"], []).append(item)

    def narr_row(rw, text, ref, value, fill=None):
        ws.merge_cells(f"B{rw}:H{rw}")
        _put(ws, f"B{rw}", text, border=BOX, fill=fill)
        for col in "CDEFGH":
            ws[f"{col}{rw}"].border = BOX
        _put(ws, f"I{rw}", ref, border=BOX, font=F_SMALL, align=Alignment(horizontal="center"), fill=fill)
        _money(ws, f"J{rw}", value, border=BOX, fill=fill)

    for cat in ("Income not declared", "Income declared in error", "Expenses not claimed", "Expenses claimed in error", "Private use adjustments"):
        items = by_cat.pop(cat, [])
        _put(ws, f"A{row}", cat, font=F_BOLD)
        for k in range(max(len(items), 2)):
            if k < len(items):
                it = items[k]
                narr_row(row, (it.get("description") or it["status"])[:110], it["id"], it["effect"])
            else:
                narr_row(row, None, None, None, fill=FILL_INPUT)
            row += 1
        row += 1
    _put(ws, f"A{row}", "Other adjustments", font=F_BOLD)
    for label, ref in (("Entertainment adjustment", "V1"), ("FBT reimbursement", "T1"), ("Use of home as office", "V2"),
                       ("Capital adjustments - debit", ""), ("Capital adjustments - credit", "")):
        narr_row(row, label, ref, 0, fill=FILL_INPUT)
        row += 1
    for items in by_cat.values():
        for it in items:
            narr_row(row, (it.get("description") or it["status"])[:110], it["id"], it["effect"])
            row += 1
    row += 1
    _put(ws, f"A{row}", "Return variance (per above)", font=F_BOLD)
    _money(ws, f"J{row}", f"=IF(K{gl}=\"y\",J{var},0)", border=BOX)
    last_adj = row
    row += 2
    _put(ws, f"H{row}", "Total adjustments", font=F_BOLD, align=Alignment(horizontal="right"))
    _money(ws, f"J{row}", f"=SUM(J{first_adj}:J{last_adj})", font=F_BOLD, border=SUB_RULE)
    total_adj = f"J{row}"
    row += 2
    _put(ws, f"H{row}", "Total", font=F_BOLD, align=Alignment(horizontal="right"))
    _money(ws, f"J{row}", f"={timing_total}+{total_adj}", font=F_BOLD, border=BOX)
    total = f"J{row}"
    row += 1
    _put(ws, f"H{row}", "Ledger totals", font=F_BOLD, align=Alignment(horizontal="right"))
    _money(ws, f"J{row}", f"={ledger_cell}", font=F_BOLD, border=BOX)
    ledger_total = f"J{row}"
    row += 1
    _put(ws, f"H{row}", "Proposed corrections (not posted)", align=Alignment(horizontal="right"))
    _money(ws, f"J{row}", b["corrections"], border=BOX)
    corr = f"J{row}"
    row += 1
    _put(ws, f"H{row}", "Adjusted ledger totals", font=F_BOLD, align=Alignment(horizontal="right"))
    _money(ws, f"J{row}", f"={ledger_total}+{corr}", font=F_BOLD, border=BOX)
    adjusted = f"J{row}"
    row += 2
    _put(ws, f"B{row}", "Create adjustment sheet: see 'Proposed corrections'", font=F_BOLD)
    _put(ws, f"H{row}", "Variance", font=F_BOLD, align=Alignment(horizontal="right"))
    _money(ws, f"J{row}", f"={adjusted}-{total}", font=F_BOLD, border=TOTAL_RULE)
    row += 2
    _put(ws, f"A{row}", "Variance = adjusted ledger totals less total; the target is nil. A balance that relies on proposed corrections stays conditional "
                        "until they are posted. Layout: CCH Business Fitness NZ (L1).", font=F_NOTE)
    row += 2
    signoff(ws, row, su, meta)
    _print_setup(ws, "11:11")


def signoff(ws, row: int, su, meta):
    """The sign-off block at the foot of the lead schedule."""
    _put(ws, f"A{row}", "Sign-off", font=F_SECTION)
    for i, (who, name, when) in enumerate((("Prepared by", su.prepared_by or "WP Agent", meta["prep_date"]), ("Reviewed by", "", None)), start=1):
        r = row + i
        _put(ws, f"A{r}", who, font=F_BOLD)
        _put(ws, f"B{r}", name, border=Border(bottom=THIN), fill=FILL_INPUT if not name else None)
        ws.merge_cells(f"B{r}:D{r}")
        _put(ws, f"E{r}", "Date", font=F_SMALL, align=Alignment(horizontal="right"))
        _put(ws, f"F{r}", when, fmt=DATE, border=Border(bottom=THIN), fill=FILL_INPUT if when is None else None)


# --- the supporting schedules ------------------------------------------------------------------------------

def table(ws, row: int, headers: list[str], rows: list[list], *, money: tuple[int, ...] = (), dates: tuple[int, ...] = (),
          wrap: tuple[int, ...] = (), totals: tuple[int, ...] = (), title: str = "") -> int:
    """A formatted table from `row`; returns the last row used. Money columns are right-aligned in the
    accounting format; `totals` columns get a SUM row ruled single above and double below."""
    if title:
        _put(ws, f"A{row}", title, font=F_SECTION)
        row += 1
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font, c.fill, c.alignment, c.border = F_HEAD, FILL_HEAD, CENTER, BOX
    ws.row_dimensions[row].height = 30
    head = row
    if not rows:
        row += 1
        _put(ws, f"A{row}", "None.", font=F_NOTE)
        return row
    for n, values in enumerate(rows):
        row += 1
        fill = FILL_ZEBRA if n % 2 else None
        for i, value in enumerate(values, start=1):
            c = ws.cell(row=row, column=i, value=_v(value))
            c.font, c.border = F_BASE, ROW_LINE
            if fill:
                c.fill = fill
            if i in money:
                c.number_format, c.alignment = MONEY, Alignment(horizontal="right", vertical="top")
            elif i in dates or isinstance(value, date):
                c.number_format, c.alignment = DATE, Alignment(horizontal="center", vertical="top")
            elif i in wrap:
                c.alignment = WRAP
            else:
                c.alignment = Alignment(vertical="top")
    if totals:
        row += 1
        _put(ws, f"A{row}", "Total", font=F_BOLD)
        for i in totals:
            col = get_column_letter(i)
            _money(ws, f"{col}{row}", f"=SUBTOTAL(9,{col}{head + 1}:{col}{row - 1})", font=F_BOLD, border=TOTAL_RULE)
    return row


def sheet(wb, title: str, ref: str, su, meta, widths: dict[int, int], note: str = "", tab: str = "7F7F7F"):
    ws = wb.create_sheet(title[:31])
    ws.sheet_properties.tabColor = tab
    for i, w in widths.items():
        ws.column_dimensions[get_column_letter(i)].width = w
    start = header(ws, su, meta, title, ref, max(widths), note)
    return ws, start


def _finish(ws, head_row: int):
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    _print_setup(ws, f"{head_row}:{head_row}")


def build(result: dict, su, meta: dict) -> bytes:
    r = result["recon"]
    wb = Workbook()
    l1_sheet(wb, r, su, meta)
    b = r["bridge"]

    # Summary
    ws, row = sheet(wb, "Summary", "L1.0", su, meta, {1: 8, 2: 58, 3: 18, 4: 34}, tab="404040")
    status = r["status"]
    ws.merge_cells(f"A{row}:D{row}")
    _put(ws, f"A{row}", f"Status: {status}", font=Font(name=FONT, size=13, bold=True, color=STATUS_FONT.get(status, "000000")),
         fill=PatternFill("solid", fgColor=STATUS_FILL.get(status, LIGHT)), align=Alignment(horizontal="left", vertical="center", indent=1))
    ws.row_dimensions[row].height = 26
    row += 2
    bridge = [
        ("A", "GST principal outstanding at balance date", b["A"], "L1.1 Returns & settlements", False),
        ("", "     of which current-year periods", b["A_current"], "", False),
        ("", "     of which prior-year periods", b["A_prior"], "", False),
        ("B", "Add: GST on unpaid receivables not yet returned", b["B"], "G1 Receivables GST", False),
        ("C", "Less: GST on unpaid payables not yet claimed", b["C"], "M1 Payables GST", False),
        ("D", "Other supported return and timing differences", b["D"], "Journals & late claims; Import GST", False),
        ("E", "Expected GST control balance (A + B − C + D)", b["E"], "", True),
        ("", "Reported GL GST control balance", b["reported"], "L1 ledger information", False),
        ("", "Proposed correction effects (not posted)", b["corrections"], "Proposed corrections", False),
        ("F", "Adjusted GST control balance", b["F"], "", True),
        ("", "Unexplained difference (F − E)", b["unexplained"], f"target nil; tolerance {b['tolerance']:,.2f}", True),
    ]
    for c, h in zip("ABCD", ("Ref", "Reconciliation component", "NZD", "Supporting schedule")):
        _put(ws, f"{c}{row}", h, font=F_HEAD, fill=FILL_HEAD, border=BOX, align=CENTER)
    for ref, label, value, where, strong in bridge:
        row += 1
        _put(ws, f"A{row}", ref, font=F_BOLD, align=Alignment(horizontal="center"), border=ROW_LINE)
        _put(ws, f"B{row}", label, font=F_BOLD if strong else F_BASE, border=ROW_LINE)
        _money(ws, f"C{row}", value, font=F_BOLD if strong else F_BASE, border=TOTAL_RULE if strong else ROW_LINE)
        _put(ws, f"D{row}", where, font=F_SMALL, border=ROW_LINE)
    row += 2
    _put(ws, f"A{row}", "Key figures", font=F_SECTION)
    facts = [("Open exceptions — blocking", r["counts"]["blocking"]), ("Open exceptions — to review", r["counts"]["review"]),
             ("Returns outstanding at balance date", r["counts"]["outstanding_returns"]), ("Proposed corrections", len(r["corrections"])),
             ("Documents read", len(result["sources"])), ("Preparation cut-off", meta["prep_date"]), ("Run", meta["run_id"]),
             ("Rules / skills", f"{meta['versions'].get('rules', '')}; {meta['versions'].get('skills', '')}")]
    for label, value in facts:
        row += 1
        _put(ws, f"B{row}", label, border=ROW_LINE)
        _put(ws, f"C{row}", _v(value), fmt=DATE if isinstance(value, date) else None, border=ROW_LINE, align=Alignment(horizontal="right"))
    row += 2
    _put(ws, f"A{row}", "Commentary", font=F_SECTION)
    row += 1
    ws.merge_cells(f"A{row}:D{row + 4}")
    _put(ws, f"A{row}", result.get("summary") or "", align=WRAP, border=BOX)
    row += 6
    _put(ws, f"A{row}", "Job settings used", font=F_SECTION)
    for k, v in result["settings"].items():
        row += 1
        _put(ws, f"B{row}", k, border=ROW_LINE)
        value = ", ".join(v) if isinstance(v, list) else _v(v)
        _put(ws, f"C{row}", value, fmt=DATE if isinstance(v, date) else None, border=ROW_LINE, align=Alignment(horizontal="right"))
    for side in ("ar", "ap"):
        paused = r[side].get("paused")
        if paused:
            row += 2
            _put(ws, f"A{row}", f"Paused: {paused['report']}", font=Font(name=FONT, size=11, bold=True, color="9C0006"))
            row += 1
            ws.merge_cells(f"A{row}:D{row + 5}")
            _put(ws, f"A{row}", paused["message"], align=WRAP, border=BOX, fill=PatternFill("solid", fgColor="FCE4D6"))
            row += 6
    _print_setup(ws, landscape=False)

    # L1.1 Returns & settlements
    ws, row = sheet(wb, "L1.1 Returns & settlements", "L1.1", su, meta,
                    {1: 12, 2: 12, 3: 11, 4: 11, 5: 13, 6: 11, 7: 13, 8: 11, 9: 14, 10: 14, 11: 14, 12: 22, 13: 14, 14: 14, 15: 18, 16: 44},
                    note="Component A: each return's principal, settlements effective on or before the balance date, and later settlements apart.")
    head = row
    end = table(ws, row, ["Period ended", "Version", "Filed", "Due", "Output tax", "Box 9", "Input tax", "Box 13", "Net GST (payable +)",
                          "Settled to balance date", "Outstanding at balance date", "Standing", "Settled after balance date", "Outstanding now",
                          "Origin", "Source"],
                [[p["period_end"], p["version"], p["filed"], p["due"], p["output"], p["box9"], p["input"], p["box13"], p["net"], p["settled_to_bd"],
                  p["outstanding_bd"], p["standing"], p["settled_after"], p["outstanding_now"],
                  "prior-year period" if p["prior_year"] else ("from prior-year reconciliation" if p["origin"] == "prior_year" else "return"), p["source"]]
                 for p in r["periods"]],
                money=(5, 6, 7, 8, 9, 10, 11, 13, 14), wrap=(12, 15, 16), totals=(9, 10, 11, 13, 14))
    table(ws, end + 3, ["IRD date", "Effective", "Transaction", "Category", "Period (per IRD)", "Movement (owed +)", "Allocated to", "Reference", "Source"],
          [[x["date"], x["effective"], x["type"], x["category"], x.get("period_end"), x["movement"], x.get("allocated_to"), x.get("reference", ""), x["source"]]
           for x in r["ird"]["lines"]], money=(6,), wrap=(3, 9), title="IRD GST account: every line and its period")
    _finish(ws, head)

    # Opening items
    py = result.get("prior_year") or {}
    ws, row = sheet(wb, "Opening items", "L1.2", su, meta, {1: 62, 2: 18, 3: 60},
                    note="Prior-year items traced into this year. Last year's AR/AP timing amounts explain movements; they are not added again.")
    rows = [["GL GST balance per last year's reconciliation", py.get("gl_gst_balance"), py.get("source", "")],
            ["IRD outstanding per last year's reconciliation", py.get("ird_outstanding"), ""],
            ["Opening GST per this year's GL", (r.get("opening") or {}).get("opening"), ""]]
    rows += [[f"Unpaid return {u['period_end']:%d/%m/%Y}" if u.get("period_end") else "Unpaid return", u["amount"], u["source"]] for u in py.get("unpaid_returns", [])]
    rows += [[f"Timing item: {u['item']}", u["amount"], u["source"]] for u in py.get("timing_items", [])]
    rows += [[f"Unresolved: {u['item']}", u["amount"], u["source"]] for u in py.get("unresolved", [])]
    head = row
    table(ws, row, ["Item", "NZD", "Source"], rows, money=(2,), wrap=(1, 3))
    _finish(ws, head)

    for side, title, ref in (("ar", "G1 Receivables GST", "G1"), ("ap", "M1 Payables GST", "M1")):
        s = r[side]
        ws, row = sheet(wb, title, ref, su, meta, {1: 32, 2: 14, 3: 12, 4: 15, 5: 13, 6: 22, 7: 38, 8: 10, 9: 36, 10: 44},
                        note=f"Source: {s['source'] or 'none'}. {s['basis_note']} "
                             + (f"In the bridge: {s['total']:,.2f}." if s["applies"] else "Not in the bridge for this basis."))
        head = row
        end = table(ws, row, ["Contact", "Reference", "Date", "Balance", "GST", "Category", "How", "Included", "Reason", "Source"],
                    [[i["contact"], i["ref"], i["date"], i["balance"], i["gst"], i["category"], i["how"], "Yes" if i["included"] else "No", i["reason"],
                      i["source"]] for i in s["items"]], money=(4, 5), wrap=(1, 6, 7, 9, 10), totals=(4, 5))
        ag = s.get("agreement") or {}
        if ag:
            row = end + 2
            _put(ws, f"A{row}", "Agreement to the general ledger", font=F_SECTION)
            for label, value, rule in (("Ageing total", ag.get("ageing_total"), ROW_LINE), ("GL control account", ag.get("gl_control"), ROW_LINE),
                                       ("Difference", ag.get("difference"), TOTAL_RULE)):
                row += 1
                _put(ws, f"A{row}", label, font=F_BOLD if label == "Difference" else F_BASE)
                _money(ws, f"D{row}", value, border=rule, font=F_BOLD if label == "Difference" else None)
            end = row
        if s.get("paused"):
            row = end + 2
            ws.merge_cells(f"A{row}:I{row + 6}")
            _put(ws, f"A{row}", s["paused"]["message"], align=WRAP, border=BOX, fill=PatternFill("solid", fgColor="FCE4D6"))
        _finish(ws, head)

    imp = r["imports"]
    ws, row = sheet(wb, "Import GST", "L1.3", su, meta, {1: 12, 2: 22, 3: 34, 4: 14, 5: 13, 6: 14, 7: 11, 8: 11, 9: 32, 10: 46, 11: 14, 12: 40},
                    note=imp.get("note") or "Each import GST transaction checked separately; counted once if it is also in M1 or a late claim.")
    head = row
    table(ws, row, ["Date", "Account", "Description", "Reference", "Amount", "Is import GST?", "In GL GST account", "In the return", "Finding",
                    "Treatment", "Counted in", "Source"],
          [[i["date"], i["account"], i["description"], i["ref"], i["amount"], i["component"], "Yes" if i["in_gl_gst"] else "No",
            "Yes" if i["in_return"] else "No", i["finding"], i["treatment"], i["counted_in"], i["source"]] for i in imp["items"]],
          money=(5,), wrap=(3, 9, 10, 12))
    _finish(ws, head)

    ws, row = sheet(wb, "Journals & late claims", "L1.4", su, meta,
                    {1: 14, 2: 22, 3: 14, 4: 14, 5: 14, 6: 15, 7: 26, 8: 46, 9: 22, 10: 13, 11: 9, 12: 10},
                    note="Every later return gone through: each late claim for the year taken with the sign the return shows, pluses and minuses "
                         "set off, the remainder taken to the reconciliation with the opposite sign (purchases as a plus, sales as a minus). Journals for the same "
                         "transactions are linked as evidence; a journal no late claim confirms stays a candidate, out of the bridge.")
    head = row
    end = table(ws, row, ["Adjustment", "Category", "Plus", "Minus", "Remainder set off", "Effect (payable +)", "Later returns", "Status",
                          "Journals linked", "Unmatched part", "Review", "In bridge"],
                [[a["id"], a["category"], a.get("plus"), a.get("minus"), a.get("net"), a["effect"],
                  ", ".join(d.strftime("%d/%m/%Y") for d in a.get("returns") or []), a["status"], ", ".join(a["journals"]), a.get("unmatched"),
                  "Yes" if a["review"] else "", "Yes" if a.get("included", True) else "No"] for a in r["adjustments"]],
                money=(3, 4, 5, 6, 10), wrap=(7, 8, 9))
    evidence = ([["Journal", x["id"], x["date"], x.get("created"), x.get("finalised"), x["description"], x["effect"], x["source"]] for x in r["journals"]]
                + [["Late claim (" + ("sales" if x["direction"] == "output" else "purchases") + ")", x["id"], x["date"], None, x.get("return_period_end"),
                    f"{x['ref']} {x['contact']} {x['description']}".strip(), x["gst"], x["source"]] for x in r["late_claims"]]
                + [["Evidence only", x["id"], x["date"], None, x.get("return_period_end"), f"{x['ref']} {x['description']} — {x['reason']}",
                    x["gst"], x["source"]] for x in r["late_claims_evidence"][:500]])
    table(ws, end + 3, ["Evidence", "Id", "Date", "Entered", "Return finalised / later return", "Description", "GST (as in the return; journals: effect)",
                        "Source"], evidence, money=(7,), wrap=(6, 8),
          title="Evidence: late claims in every later return (plus and minus, set off above) and journals entered after the return")
    _finish(ws, head)

    ws, row = sheet(wb, "Payment matching", "L1.5", su, meta, {1: 12, 2: 11, 3: 15, 4: 12, 5: 16, 6: 24, 7: 12, 8: 16, 9: 36, 10: 18, 11: 38, 12: 38})
    head = row
    table(ws, row, ["IRD date", "Type", "Amount (owed +)", "Period", "IRD reference", "GL account", "GL date", "GL reference", "Result", "Confidence",
                    "IRD source", "GL source"],
          [[p["ird_date"], p["ird_type"], p["amount"], p["period"], p["ird_ref"], (p["gl"] or {}).get("account"), (p["gl"] or {}).get("date"),
            (p["gl"] or {}).get("ref"), p["result"], p["confidence"], p["ird_source"], (p["gl"] or {}).get("source")] for p in r["payments"]["rows"]],
          money=(3,), wrap=(9, 11, 12))
    _finish(ws, head)

    ws, row = sheet(wb, "Proposed corrections", "L1.6", su, meta, {1: 13, 2: 34, 3: 30, 4: 14, 5: 14, 6: 15, 7: 56, 8: 44, 9: 18},
                    note="Financial statement corrections, outside timing and return differences. Proposed only: nothing is posted. Use the "
                         "software's no-GST treatment for a control-account reclassification.", tab="C00000")
    rows = []
    for c in r["corrections"]:
        for n, ln in enumerate(c["lines"]):
            rows.append([c["id"] if n == 0 else "", c["title"] if n == 0 else "", ln["account"], ln["debit"] or None, ln["credit"] or None,
                         c["gst_effect"] if n == 0 else None, c["explanation"] if n == 0 else "", "; ".join(c["evidence"]) if n == 0 else "",
                         c["status"] if n == 0 else ""])
    head = row
    table(ws, row, ["Id", "Correction", "Account", "Debit", "Credit", "GST control effect", "Explanation", "Evidence", "Status"], rows,
          money=(4, 5, 6), wrap=(2, 7, 8), totals=(4, 5, 6) if rows else ())
    _finish(ws, head)

    an = r["analysis"]
    ws, row = sheet(wb, "Period analysis", "L1.7", su, meta, {1: 14, 2: 15, 3: 15, 4: 15, 5: 15, 6: 15, 7: 15},
                    note=an.get("note") or "Output and input compared separately; principal payments kept out.")
    head = row
    end = table(ws, row, ["Period ended", "Return output", "GL output", "Output residual", "Return input", "GL input", "Input residual"],
                [[x["period_end"], x["return_output"], x["gl_output"], x["output_residual"], x["return_input"], x["gl_input"], x["input_residual"]]
                 for x in an["rows"]], money=(2, 3, 4, 5, 6, 7), totals=(2, 3, 4, 5, 6, 7))
    _finish(ws, head)

    ws, row = sheet(wb, "Exceptions & evidence", "L1.8", su, meta, {1: 13, 2: 11, 3: 70, 4: 52, 5: 14, 6: 50}, tab="C00000")
    head = row
    order = {"blocking": 0, "review": 1, "info": 2}
    table(ws, row, ["Id", "Severity", "Exception", "Next evidence needed", "Amount", "Sources"],
          [[x["id"], x["severity"].capitalize(), x["text"], x["next_evidence"], x.get("amount"), "; ".join(str(s) for s in x["refs"] if s)]
           for x in sorted(r["exceptions"], key=lambda e: order.get(e["severity"], 3))], money=(5,), wrap=(3, 4, 6))
    for rr in range(head + 1, ws.max_row + 1):
        sev = ws.cell(row=rr, column=2)
        if sev.value in ("Blocking", "Review"):
            sev.font = Font(name=FONT, size=10, bold=True, color="9C0006" if sev.value == "Blocking" else "7F6000")
    _finish(ws, head)

    ws, row = sheet(wb, "Sources", "L1.9", su, meta, {1: 7, 2: 46, 3: 18, 4: 22, 5: 12, 6: 9, 7: 8, 8: 40, 9: 46})
    head = row
    table(ws, row, ["Id", "File", "Folder", "Read as", "Decided by", "Rows", "Pages", "Problem", "Link"],
          [[x["sid"], x["name"], x["path"], x["kind"].replace("_", " "), x["kind_how"], x["rows"], x["pages"], x["error"], x["url"]]
           for x in result["sources"]], wrap=(2, 8))
    for n, x in enumerate(result["sources"], start=head + 1):
        if x["url"].startswith("http"):
            c = ws.cell(row=n, column=9)
            c.hyperlink = x["url"]
            c.font = Font(name=FONT, size=10, color="0563C1", underline="single")
    _finish(ws, head)

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
