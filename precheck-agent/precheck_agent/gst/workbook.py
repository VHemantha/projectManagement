"""The workpaper: an editable Excel workbook. Its first sheet follows the firm's CCH "L1 GST
reconciliation" layout (Output.pdf); the supporting schedules follow it, one sheet each. Totals on L1
are Excel formulas, so a reviewer can change an input and the sheet recalculates. GST payable is
positive on every sheet except L1's "(Payment) / refund" column, which keeps the template's sign."""
import io
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

MONEY = '#,##0.00;(#,##0.00);"-"'
DATE = "DD/MM/YY"
THIN = Side(style="thin", color="999999")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
TOP2 = Border(top=Side(style="thin", color="000000"), bottom=Side(style="double", color="000000"))
BAR = PatternFill("solid", fgColor="F2F2F2")
HEAD = PatternFill("solid", fgColor="800000")
WHITE = Font(bold=True, color="FFFFFF")
BOLD = Font(bold=True)
FREQ = {"monthly": "Monthly", "two_monthly": "2 monthly", "six_monthly": "6 monthly"}
BASIS = {"payments": "Payments", "invoice": "Invoice", "hybrid": "Hybrid"}


def _v(value):
    """A value for a cell: Decimals and dates as Excel numbers and dates."""
    if isinstance(value, Decimal):
        return float(value)
    return value


def _put(ws, ref, value, *, fmt=None, bold=False, box=False, fill=None, wrap=False, font=None):
    c = ws[ref]
    c.value = _v(value)
    if fmt:
        c.number_format = fmt
    if bold:
        c.font = BOLD
    if font:
        c.font = font
    if box:
        c.border = BOX
    if fill:
        c.fill = fill
    if wrap:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    return c


def _bar(ws, row, text, last="L"):
    ws.merge_cells(f"A{row}:{last}{row}")
    c = _put(ws, f"A{row}", text, bold=True, fill=BAR)
    c.border = BOX


def l1_sheet(wb: Workbook, r: dict, su, meta: dict) -> None:
    ws = wb.active
    ws.title = "L1 GST reconciliation"
    widths = [12, 13, 13, 13, 13, 13, 13, 13, 13, 14, 12, 14]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.column_dimensions["A"].width = 30
    _put(ws, "A1", su.firm, font=Font(bold=True, size=9))
    _put(ws, "J1", "Prep Date:", font=Font(bold=True, size=9))
    _put(ws, "K1", meta["prep_date"], fmt="DD/MM/YYYY", bold=True)
    _put(ws, "A2", su.entity or "Client Name", font=Font(bold=True, size=12))
    _put(ws, "J2", "Balance Date:", font=Font(bold=True, size=9))
    _put(ws, "K2", su.balance_date, fmt="DD/MM/YYYY", bold=True)
    _put(ws, "A3", "GST reconciliation", font=Font(bold=True, size=16))
    _put(ws, "L3", "L1", font=Font(size=22))
    _put(ws, "A4", f"Prepared By: {su.prepared_by or 'WP Agent'}", font=Font(bold=True, size=9))
    _put(ws, "D4", "Reviewed By:", font=Font(bold=True, size=9))
    _put(ws, "A5", f"Status: {r['status']}. GST payable is shown positive except in the (Payment) / refund column. Prepared by the WP Agent "
                   f"(run {meta['run_id'][:8]}); not reviewed until signed off.", font=Font(italic=True, size=8, color="666666"))
    _put(ws, "A6", "Accounting basis", bold=True, box=True)
    _put(ws, "B6", BASIS.get(su.basis, su.basis), box=True)
    _put(ws, "A7", "Period", bold=True, box=True)
    _put(ws, "B7", FREQ.get(su.frequency, su.frequency), box=True)

    _bar(ws, 9, "GST return information")
    heads = ["Period ended", "Total outputs", "Output tax", "Prior year adjustments", "Box 9 adjustments", "Total inputs", "Input tax",
             "Prior year adjustments", "Box 13 adjustments", "(Payment) / refund", "Paid/rec'd @ bal date"]
    for i, h in enumerate(heads, start=1):
        c = ws.cell(row=11, column=i, value=h)
        c.font, c.border, c.alignment = BOLD, BOX, Alignment(wrap_text=True, horizontal="center", vertical="center")
    ws.row_dimensions[11].height = 30
    row = 12
    periods = [p for p in r["periods"] if not p["prior_year"] and p["period_end"] <= su.balance_date and p["origin"] == "return"]
    first = row
    for p in periods:
        _put(ws, f"A{row}", p["period_end"], fmt=DATE, box=True)
        for col, key in (("B", "total_sales"), ("C", "output"), ("E", "box9"), ("F", "total_purchases"), ("G", "input"), ("I", "box13")):
            _put(ws, f"{col}{row}", p.get(key) or 0, fmt=MONEY, box=True)
        _put(ws, f"D{row}", 0, fmt=MONEY, box=True)
        _put(ws, f"H{row}", 0, fmt=MONEY, box=True)
        _put(ws, f"J{row}", f"=(G{row}+H{row}+I{row})-(C{row}+D{row}+E{row})", fmt=MONEY, box=True)
        _put(ws, f"K{row}", p["paid_at_bd"], box=True).alignment = Alignment(horizontal="center")
        row += 1
    last = max(row - 1, first)
    if row == first:
        row += 1
    totals = row + 1
    _put(ws, f"A{totals}", "Totals", bold=True)
    for col in "BCDEFGHIJ":
        _put(ws, f"{col}{totals}", f"=SUM({col}{first}:{col}{last})", fmt=MONEY, bold=True).border = TOP2
    a = r["analysis"]["year"]
    gl = totals + 2
    _put(ws, f"B{gl}", "GL output tax")
    _put(ws, f"C{gl}", a["gl_output"], fmt=MONEY, box=True)
    _put(ws, f"F{gl}", "GL input tax")
    _put(ws, f"G{gl}", a["gl_input"], fmt=MONEY, box=True)
    _put(ws, f"I{gl}", "Include variance in total?(y/n)")
    _put(ws, f"K{gl}", "n", box=True)
    var = gl + 2
    _put(ws, f"B{var}", "Variance")
    _put(ws, f"C{var}", f"=C{gl}-(C{totals}+D{totals}+E{totals})", fmt=MONEY).border = TOP2
    _put(ws, f"G{var}", f"=G{gl}-(G{totals}+H{totals}+I{totals})", fmt=MONEY).border = TOP2
    _put(ws, f"J{var}", f"=C{var}-G{var}", fmt=MONEY).border = TOP2

    led = var + 2
    _bar(ws, led, "GST ledger information")
    lr = led + 1
    for acc in r["ledger"]["accounts"] or []:
        _put(ws, f"A{lr}", f"{acc.get('code') or ''} {acc['account']}".strip())
        _put(ws, f"J{lr}", -acc["balance"], fmt=MONEY, box=True)
        _put(ws, f"K{lr}", acc["source"], font=Font(size=8, color="666666"))
        lr += 1
    _put(ws, f"A{lr}", f"Reported GST control balance (per {r['ledger']['how'] or 'not found'})", bold=True)
    _put(ws, f"J{lr}", r["bridge"]["reported"] if r["bridge"]["reported"] is not None else 0, fmt=MONEY, box=True, bold=True)
    ledger_cell = f"J{lr}"

    t = lr + 2
    _bar(ws, t, "Timing differences")
    _put(ws, f"I{t + 1}", "Ref", bold=True)
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
    row = t + 2
    first_timing = row
    for label, ref, value in lines:
        _put(ws, f"A{row}", label)
        _put(ws, f"I{row}", ref, bold=True)
        _put(ws, f"J{row}", value, fmt=MONEY, box=True)
        if label == "Unprocessed payments":
            _put(ws, f"D{row}", "Include unprocessed payments and receipts in total?(y/n)")
            _put(ws, f"H{row}", "y", box=True)
        row += 1
    _put(ws, f"A{row}", "Total timing differences", bold=True)
    _put(ws, f"J{row}", f"=SUM(J{first_timing}:J{first_timing + 3})+IF(H{first_timing + 4}=\"y\",J{first_timing + 4}+J{first_timing + 5},0)"
                        f"+SUM(J{first_timing + 6}:J{row - 1})", fmt=MONEY, bold=True).border = TOP2
    timing_total = f"J{row}"

    adj = row + 2
    _bar(ws, adj, "Adjustments required")
    _put(ws, f"B{adj + 1}", "Narration", bold=True)
    _put(ws, f"I{adj + 1}", "Ref", bold=True)
    _put(ws, f"J{adj + 1}", "$", bold=True)
    row = adj + 2
    first_adj = row
    by_cat: dict[str, list[dict]] = {}
    for item in r["adjustments"]:
        by_cat.setdefault(item["category"], []).append(item)
    for cat in ("Income not declared", "Income declared in error", "Expenses not claimed", "Expenses claimed in error", "Private use adjustments"):
        items = by_cat.pop(cat, [])
        _put(ws, f"A{row}", cat)
        for k in range(max(len(items), 2)):
            if k < len(items):
                it = items[k]
                _put(ws, f"B{row}", (it.get("description") or it["status"])[:90], box=True)
                _put(ws, f"I{row}", it["id"], box=True)
                _put(ws, f"J{row}", it["effect"], fmt=MONEY, box=True)
            else:
                for col in ("B", "I", "J"):
                    _put(ws, f"{col}{row}", None, box=True)
            row += 1
        row += 1
    _put(ws, f"A{row}", "Other adjustments")
    for label, ref in (("Entertainment adjustment", "V1"), ("FBT reimbursement", "T1"), ("Use of home as office", "V2"),
                       ("Capital adjustments - debit", ""), ("Capital adjustments - credit", "")):
        _put(ws, f"B{row}", label, box=True)
        _put(ws, f"I{row}", ref, box=True)
        _put(ws, f"J{row}", 0, fmt=MONEY, box=True)
        row += 1
    for items in by_cat.values():
        for it in items:
            _put(ws, f"B{row}", (it.get("description") or it["status"])[:90], box=True)
            _put(ws, f"I{row}", it["id"], box=True)
            _put(ws, f"J{row}", it["effect"], fmt=MONEY, box=True)
            row += 1
    row += 1
    _put(ws, f"A{row}", "Return variance (per above)")
    _put(ws, f"J{row}", f"=IF(K{gl}=\"y\",J{var},0)", fmt=MONEY, box=True)
    last_adj = row
    row += 2
    _put(ws, f"H{row}", "Total adjustments", bold=True)
    _put(ws, f"J{row}", f"=SUM(J{first_adj}:J{last_adj})", fmt=MONEY, bold=True).border = TOP2
    total_adj = f"J{row}"
    row += 2
    _put(ws, f"H{row}", "Total", bold=True)
    _put(ws, f"J{row}", f"={timing_total}+{total_adj}", fmt=MONEY, bold=True, box=True)
    total = f"J{row}"
    row += 1
    _put(ws, f"H{row}", "Ledger totals", bold=True)
    _put(ws, f"J{row}", f"={ledger_cell}", fmt=MONEY, bold=True, box=True)
    ledger_total = f"J{row}"
    row += 1
    _put(ws, f"H{row}", "Proposed corrections (not posted)")
    _put(ws, f"J{row}", b["corrections"], fmt=MONEY, box=True)
    corr = f"J{row}"
    row += 1
    _put(ws, f"H{row}", "Adjusted ledger totals", bold=True)
    _put(ws, f"J{row}", f"={ledger_total}+{corr}", fmt=MONEY, bold=True, box=True)
    adjusted = f"J{row}"
    row += 2
    _put(ws, f"B{row}", "Create adjustment sheet: see 'Proposed corrections'", bold=True)
    _put(ws, f"H{row}", "Variance", bold=True)
    _put(ws, f"J{row}", f"={adjusted}-{total}", fmt=MONEY, bold=True).border = TOP2
    _put(ws, f"A{row + 2}", "CCH Business Fitness NZ layout. Variance = adjusted ledger less total (target: nil). "
                            "A balance that relies on proposed corrections stays conditional until they are posted.",
         font=Font(italic=True, size=8, color="666666"))
    ws.sheet_view.showGridLines = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1


def table(wb: Workbook, title: str, headers: list[str], rows: list[list], *, note: str = "", money: tuple[int, ...] = (), dates: tuple[int, ...] = (),
          widths: dict[int, int] | None = None, start_row: int = 1, ws=None):
    ws = ws or wb.create_sheet(title[:31])
    row = start_row
    if note:
        _put(ws, f"A{row}", note, wrap=False, font=Font(italic=True, size=9, color="444444"))
        row += 2
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=i, value=h)
        c.font, c.fill, c.alignment = WHITE, HEAD, Alignment(wrap_text=True, vertical="center")
    head_row = row
    for values in rows:
        row += 1
        for i, value in enumerate(values, start=1):
            c = ws.cell(row=row, column=i, value=_v(value))
            if i in money:
                c.number_format = MONEY
            elif i in dates or isinstance(value, date):
                c.number_format = DATE
    for i in range(1, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = (widths or {}).get(i, 16)
    if start_row == 1:
        ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    return ws, row


def build(result: dict, su, meta: dict) -> bytes:
    r = result["recon"]
    wb = Workbook()
    l1_sheet(wb, r, su, meta)
    b = r["bridge"]

    # Summary
    ws = wb.create_sheet("Summary")
    rows = [
        ["Status", r["status"], ""],
        ["A  GST principal outstanding at balance date", b["A"], "L1.1 Returns & settlements"],
        ["     of which current-year periods", b["A_current"], ""],
        ["     of which prior-year periods", b["A_prior"], ""],
        ["B  GST on unpaid receivables not yet returned (added)", b["B"], "G1 Receivables GST"],
        ["C  GST on unpaid payables not yet claimed (deducted)", b["C"], "M1 Payables GST"],
        ["D  Other supported return and timing differences", b["D"], "Journals & late claims; Import GST"],
        ["E  Expected GST control balance (A + B - C + D)", b["E"], ""],
        ["Reported GL GST control balance", b["reported"], "L1 ledger information"],
        ["Proposed / posted correction effects", b["corrections"], "Proposed corrections"],
        ["F  Adjusted GST control balance", b["F"], ""],
        ["Unexplained difference (F - E)", b["unexplained"], "target: nil"],
        ["Approved tolerance", b["tolerance"], "default nil"],
        ["Open exceptions: blocking / review", f"{r['counts']['blocking']} / {r['counts']['review']}", "Exceptions & evidence"],
        ["Outstanding returns at balance date", r["counts"]["outstanding_returns"], ""],
        ["Preparation cut-off", meta["prep_date"], ""],
        ["Run", meta["run_id"], f"rules {meta['versions'].get('rules', '')}; skills {meta['versions'].get('skills', '')}"],
    ]
    table(wb, "Summary", ["Item", "NZD", "Where"], rows, money=(2,), widths={1: 58, 2: 18, 3: 40}, ws=ws,
          note=f"{su.entity} — GST reconciliation at {su.balance_date:%d/%m/%Y} ({BASIS.get(su.basis, su.basis)} basis, {FREQ.get(su.frequency, su.frequency)}). "
               "GST payable positive, receivable negative.")
    row = len(rows) + 5
    _put(ws, f"A{row}", "Summary", bold=True)
    _put(ws, f"A{row + 1}", result.get("summary") or "", wrap=True)
    ws.merge_cells(f"A{row + 1}:C{row + 6}")
    row += 8
    _put(ws, f"A{row}", "Job settings used", bold=True)
    for k, v in result["settings"].items():
        row += 1
        _put(ws, f"A{row}", k)
        _put(ws, f"B{row}", ", ".join(v) if isinstance(v, list) else _v(v))
    for side in ("ar", "ap"):
        paused = r[side].get("paused")
        if paused:
            row += 2
            _put(ws, f"A{row}", f"Paused: {paused['report']}", bold=True)
            _put(ws, f"A{row + 1}", paused["message"], wrap=True)
            ws.merge_cells(f"A{row + 1}:C{row + 5}")
            row += 5

    # L1.1 Returns & settlements
    ws, end = table(wb, "L1.1 Returns & settlements",
                    ["Period ended", "Version", "Filed", "Due", "Output tax", "Box 9", "Input tax", "Box 13", "Net GST (payable +)", "Settled to balance date",
                     "Outstanding at balance date", "Standing", "Settled after balance date", "Outstanding now", "Origin", "Source"],
                    [[p["period_end"], p["version"], p["filed"], p["due"], p["output"], p["box9"], p["input"], p["box13"], p["net"], p["settled_to_bd"],
                      p["outstanding_bd"], p["standing"], p["settled_after"], p["outstanding_now"],
                      "prior-year period" if p["prior_year"] else ("from prior-year reconciliation" if p["origin"] == "prior_year" else "return"), p["source"]]
                     for p in r["periods"]],
                    money=(5, 6, 7, 8, 9, 10, 11, 13, 14), widths={12: 26, 15: 22, 16: 50},
                    note="Component A: each return's principal, settlements effective on or before the balance date, and later settlements apart.")
    table(wb, "", ["IRD date", "Effective", "Type", "Category", "Period (per IRD)", "Movement (owed +)", "Allocated to", "Reference", "Source"],
          [[x["date"], x["effective"], x["type"], x["category"], x.get("period_end"), x["movement"], x.get("allocated_to"), x.get("reference", ""), x["source"]]
           for x in r["ird"]["lines"]], money=(6,), ws=ws, start_row=end + 3, widths={3: 30, 9: 50})

    # Opening items
    py = result.get("prior_year") or {}
    rows = [["GL GST balance per last year's reconciliation", py.get("gl_gst_balance"), py.get("source", "")],
            ["IRD outstanding per last year's reconciliation", py.get("ird_outstanding"), ""],
            ["Opening GST per this year's GL", (r.get("opening") or {}).get("opening"), ""]]
    rows += [[f"Unpaid return {u['period_end']:%d/%m/%Y}" if u.get("period_end") else "Unpaid return", u["amount"], u["source"]] for u in py.get("unpaid_returns", [])]
    rows += [[f"Timing item: {u['item']}", u["amount"], u["source"]] for u in py.get("timing_items", [])]
    rows += [[f"Unresolved: {u['item']}", u["amount"], u["source"]] for u in py.get("unresolved", [])]
    table(wb, "Opening items", ["Item", "NZD", "Source"], rows, money=(2,), widths={1: 60, 3: 60},
          note="Prior-year items traced into this year. Last year's AR/AP timing amounts explain movements; they are not added again to the closing bridge.")

    for side, title in (("ar", "G1 Receivables GST"), ("ap", "M1 Payables GST")):
        s = r[side]
        ws, end = table(wb, title, ["Contact", "Reference", "Date", "Balance", "GST", "Category", "How", "Included", "Reason", "Source"],
                        [[i["contact"], i["ref"], i["date"], i["balance"], i["gst"], i["category"], i["how"], "Yes" if i["included"] else "No", i["reason"], i["source"]]
                         for i in s["items"]], money=(4, 5), widths={1: 28, 6: 22, 7: 40, 9: 40, 10: 46},
                        note=f"Source: {s['source'] or 'none'}. {s['basis_note']} "
                             f"{'Included in the bridge: ' + format(s['total'], ',.2f') if s['applies'] else 'Not in the bridge for this basis.'}")
        ag = s.get("agreement") or {}
        if ag:
            _put(ws, f"A{end + 2}", "Ageing total", bold=True)
            _put(ws, f"D{end + 2}", ag.get("ageing_total"), fmt=MONEY)
            _put(ws, f"A{end + 3}", "GL control account", bold=True)
            _put(ws, f"D{end + 3}", ag.get("gl_control"), fmt=MONEY)
            _put(ws, f"A{end + 4}", "Difference", bold=True)
            _put(ws, f"D{end + 4}", ag.get("difference"), fmt=MONEY)
        if s.get("paused"):
            _put(ws, f"A{end + 6}", s["paused"]["message"], wrap=True)
            ws.merge_cells(f"A{end + 6}:I{end + 12}")

    imp = r["imports"]
    table(wb, "Import GST", ["Date", "Account", "Description", "Reference", "Amount", "Is import GST?", "In GL GST account", "In the return", "Finding",
                             "Treatment", "Counted in", "Source"],
          [[i["date"], i["account"], i["description"], i["ref"], i["amount"], i["component"], "Yes" if i["in_gl_gst"] else "No",
            "Yes" if i["in_return"] else "No", i["finding"], i["treatment"], i["counted_in"], i["source"]] for i in imp["items"]],
          money=(5,), widths={3: 36, 9: 34, 10: 50, 12: 46},
          note=imp.get("note") or "Each identified import GST transaction checked separately; counted once if it is also in M1 or a late claim.")

    ws, end = table(wb, "Journals & late claims", ["Adjustment", "Category", "Effect (payable +)", "Status", "Journals", "Late claims", "Later return",
                                                   "Unmatched part", "Review"],
                    [[a["id"], a["category"], a["effect"], a["status"], ", ".join(a["journals"]), ", ".join(a["late_claims"]), a.get("subsequent_return"),
                      a.get("unmatched"), "Yes" if a["review"] else ""] for a in r["adjustments"]],
                    money=(3, 8), widths={4: 46, 5: 22, 6: 22},
                    note="One adjustment per underlying GST difference, linked to every journal and late claim behind it. A later late claim is "
                         "clearance evidence: it doesn't remove the year-end difference.")
    evidence = ([["Journal", x["id"], x["date"], x.get("created"), x.get("finalised"), x["description"], x["effect"], x["source"]] for x in r["journals"]]
                + [["Late claim", x["id"], x["date"], None, x.get("return_period_end"), f"{x['ref']} {x['contact']} {x['description']}".strip(),
                    x["gst"] if x["direction"] == "output" else -x["gst"], x["source"]] for x in r["late_claims"]]
                + [["Evidence only", x["id"], x["date"], None, x.get("return_period_end"), f"{x['ref']} {x['description']} — {x['reason']}",
                    x["gst"], x["source"]] for x in r["late_claims_evidence"]])
    table(wb, "", ["Evidence", "Id", "Date", "Created", "Return finalised / later return", "Description", "GST", "Source"], evidence, money=(7,), ws=ws,
          start_row=end + 3, widths={6: 46, 8: 46})

    table(wb, "Payment matching", ["IRD date", "Type", "Amount (owed +)", "Period", "IRD reference", "GL account", "GL date", "GL reference", "Result",
                                   "Confidence", "IRD source", "GL source"],
          [[p["ird_date"], p["ird_type"], p["amount"], p["period"], p["ird_ref"], (p["gl"] or {}).get("account"), (p["gl"] or {}).get("date"),
            (p["gl"] or {}).get("ref"), p["result"], p["confidence"], p["ird_source"], (p["gl"] or {}).get("source")] for p in r["payments"]["rows"]],
          money=(3,), widths={9: 40, 11: 40, 12: 40})

    rows = []
    for c in r["corrections"]:
        for n, ln in enumerate(c["lines"]):
            rows.append([c["id"] if n == 0 else "", c["title"] if n == 0 else "", ln["account"], ln["debit"] or None, ln["credit"] or None,
                         c["gst_effect"] if n == 0 else None, c["explanation"] if n == 0 else "", "; ".join(c["evidence"]) if n == 0 else "",
                         c["status"] if n == 0 else ""])
    table(wb, "Proposed corrections", ["Id", "Correction", "Account", "Debit", "Credit", "GST control effect", "Explanation", "Evidence", "Status"], rows,
          money=(4, 5, 6), widths={2: 34, 3: 30, 7: 60, 8: 50},
          note="Financial statement corrections, outside timing and return differences. Proposed only: nothing is posted. Use the software's no-GST "
               "treatment for a control-account reclassification.")

    an = r["analysis"]
    table(wb, "Period analysis", ["Period ended", "Return output", "GL output", "Output residual", "Return input", "GL input", "Input residual"],
          [[x["period_end"], x["return_output"], x["gl_output"], x["output_residual"], x["return_input"], x["gl_input"], x["input_residual"]] for x in an["rows"]]
          + [["Year", an["year"]["return_output"], an["year"]["gl_output"], an["year"]["gl_output"] - an["year"]["return_output"], an["year"]["return_input"],
              an["year"]["gl_input"], an["year"]["gl_input"] - an["year"]["return_input"]]],
          money=(2, 3, 4, 5, 6, 7), note=an.get("note") or "Output and input compared separately; principal payments kept out.")

    table(wb, "Exceptions & evidence", ["Id", "Severity", "Exception", "Next evidence needed", "Amount", "Sources"],
          [[x["id"], x["severity"], x["text"], x["next_evidence"], x.get("amount"), "; ".join(str(s) for s in x["refs"] if s)] for x in r["exceptions"]],
          money=(5,), widths={3: 70, 4: 50, 6: 50})

    ws, _ = table(wb, "Sources", ["Id", "File", "Folder", "Read as", "Decided by", "Rows", "Pages", "Problem", "Link"],
                  [[x["sid"], x["name"], x["path"], x["kind"], x["kind_how"], x["rows"], x["pages"], x["error"], x["url"]] for x in result["sources"]],
                  widths={2: 40, 4: 22, 8: 40, 9: 50})
    for n, x in enumerate(result["sources"], start=2):
        if x["url"].startswith("http"):
            ws.cell(row=n, column=9).hyperlink = x["url"]
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
