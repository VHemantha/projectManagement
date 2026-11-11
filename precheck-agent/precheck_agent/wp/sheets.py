"""Workpaper sheets the wages and imputation agents share, in the GST workpaper's house style
(gst/workbook.py): a status banner, a "label | amount | reference" statement with ruled totals, and
the sources and exceptions schedules."""
from decimal import Decimal

from openpyxl.styles import Alignment, Font, PatternFill

from ..gst import workbook as W


def banner(ws, row: int, status: str, last: str = "D") -> int:
    ws.merge_cells(f"A{row}:{last}{row}")
    W._put(ws, f"A{row}", f"Status: {status}", font=Font(name=W.FONT, size=13, bold=True, color=W.STATUS_FONT.get(status, "000000")),
           fill=PatternFill("solid", fgColor=W.STATUS_FILL.get(status, W.LIGHT)), align=Alignment(horizontal="left", vertical="center", indent=1))
    ws.row_dimensions[row].height = 26
    return row + 2


def statement(ws, row: int, lines: list[dict], *, title: str = "", value_head: str = "NZD") -> int:
    """Lines of {"label", "value", "ref"?, "strong"?, "input"?, "formula"?, "note"?, "indent"?}. A strong line is
    ruled single above, double below; an input line is shaded for the reviewer; a formula is written as one."""
    if title:
        W._put(ws, f"A{row}", title, font=W.F_SECTION)
        row += 1
    for c, h in zip("ABC", ("Item", value_head, "Reference / note")):
        W._put(ws, f"{c}{row}", h, font=W.F_HEAD, fill=W.FILL_HEAD, border=W.BOX, align=W.CENTER)
    cells = {}
    for ln in lines:
        row += 1
        if ln.get("heading"):
            W._put(ws, f"A{row}", ln["label"], font=W.F_BOLD)
            continue
        label = ("     " * ln.get("indent", 0)) + ln["label"]
        W._put(ws, f"A{row}", label, font=W.F_BOLD if ln.get("strong") else W.F_BASE, border=W.ROW_LINE)
        value = ln.get("formula") or ln.get("value")
        if isinstance(value, str) and value.startswith("="):
            for key, ref in cells.items():
                value = value.replace("{" + key + "}", ref)
        if ln.get("ratio"):
            W._put(ws, f"B{row}", value, fmt="0.0000", border=W.BOX, align=Alignment(horizontal="right"))
        else:
            W._money(ws, f"B{row}", value if value is not None else None, font=W.F_BOLD if ln.get("strong") else None,
                     border=W.TOTAL_RULE if ln.get("strong") else W.BOX, fill=W.FILL_INPUT if ln.get("input") else None)
        W._put(ws, f"C{row}", " · ".join(x for x in (ln.get("ref", ""), ln.get("note", "")) if x), font=W.F_SMALL, border=W.ROW_LINE,
               align=Alignment(wrap_text=True, vertical="top"))
        if ln.get("key"):
            cells[ln["key"]] = f"B{row}"
    return row


def exceptions_sheet(wb, su, meta, items: list[dict], ref: str):
    ws, row = W.sheet(wb, "Exceptions & evidence", ref, su, meta, {1: 13, 2: 11, 3: 12, 4: 70, 5: 52, 6: 14, 7: 46}, tab="C00000",
                      note="Every exception with the next evidence needed. Blocking ones keep the conclusion at Incomplete evidence.")
    order = {"blocking": 0, "review": 1, "info": 2}
    head = row
    W.table(ws, row, ["Id", "Severity", "Area", "Exception", "Next evidence needed", "Amount", "Sources"],
            [[x["id"], x["severity"].capitalize(), x.get("side", "") or "both", x["text"], x["next_evidence"], x.get("amount"), "; ".join(x["refs"])]
             for x in sorted(items, key=lambda e: order.get(e["severity"], 3))], money=(6,), wrap=(4, 5, 7))
    W._finish(ws, head)


def sources_sheet(wb, su, meta, sources: list[dict], ref: str):
    ws, row = W.sheet(wb, "Sources", ref, su, meta, {1: 7, 2: 46, 3: 18, 4: 26, 5: 12, 6: 9, 7: 8, 8: 40, 9: 46},
                      note="Every document read from the Drive link, what it was read as and how that was decided.")
    head = row
    W.table(ws, row, ["Id", "File", "Folder", "Read as", "Decided by", "Rows", "Pages", "Problem", "Link"],
            [[x["sid"], x["name"], x["path"], x["kind"].replace("_", " "), x["kind_how"], x["rows"], x["pages"], x["error"], x["url"]] for x in sources],
            wrap=(2, 8))
    for n, x in enumerate(sources, start=head + 1):
        if x["url"].startswith("http"):
            c = ws.cell(row=n, column=9)
            c.hyperlink = x["url"]
            c.font = Font(name=W.FONT, size=10, color="0563C1", underline="single")
    W._finish(ws, head)


def corrections_sheet(wb, su, meta, corrections: list[dict], ref: str, effects: tuple[tuple[str, str], ...]):
    ws, row = W.sheet(wb, "Proposed journals", ref, su, meta, {1: 13, 2: 34, 3: 30, 4: 14, 5: 14, 6: 15, 7: 15, 8: 56, 9: 44, 10: 18}, tab="C00000",
                      note="Evidence-supported corrections, proposed only: nothing is posted. Each shows its effect on the reconciliation.")
    rows = []
    for c in corrections:
        for n, ln in enumerate(c["lines"]):
            rows.append([c["id"] if n == 0 else "", c["title"] if n == 0 else "", ln["account"], ln["debit"] or None, ln["credit"] or None]
                        + [(c.get(k) if n == 0 else None) for k, _ in effects]
                        + [c["explanation"] if n == 0 else "", "; ".join(c["evidence"]) if n == 0 else "", c["status"] if n == 0 else ""])
    head = row
    W.table(ws, row, ["Id", "Correction", "Account", "Debit", "Credit", *[label for _, label in effects], "Explanation", "Evidence", "Status"], rows,
            money=tuple(range(4, 6 + len(effects))), wrap=(2, 6 + len(effects), 7 + len(effects)))
    W._finish(ws, head)


def money_or_none(value) -> Decimal | None:
    return value if isinstance(value, Decimal) else None
