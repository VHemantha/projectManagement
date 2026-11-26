"""The financial statements as a Word file (AFIT, 26 Nov 2026): the same document as the PDF (fs_report), page for page
- cover, contents, the statements, policies and notes, or the one-page income statement - converted from the PDF's
own paragraphs and tables, so the two never differ. The accountant edits the Word file as any other.

Individuals without books get their statement of income and expenses as simple tables (exports' sections).
"""
import io
import re
from xml.sax.saxutils import unescape


class DocxUnavailable(RuntimeError):
    pass


def _docx():
    try:
        import docx
    except ImportError as exc:  # installed on deploy (requirements.txt)
        raise DocxUnavailable("Word files can't be made on this server yet.") from exc
    return docx


def _plain(markup: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", markup or "")
    return unescape(re.sub(r"<[^>]+>", "", text), {"&nbsp;": " "})


def _bold(markup: str, font: str) -> bool:
    return "Bold" in (font or "") or bool(re.match(r"\s*<b>.*</b>\s*$", markup or "", re.S))


def _shade(cell, hex_color: str) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color.lstrip("#"))
    tc_pr.append(shd)


def _border(cell, side: str, size: int = 6) -> None:
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    tc_pr = cell._tc.get_or_add_tcPr()
    borders = tc_pr.find(qn("w:tcBorders"))
    if borders is None:
        borders = OxmlElement("w:tcBorders")
        tc_pr.append(borders)
    el = OxmlElement(f"w:{side}")
    el.set(qn("w:val"), "single")
    el.set(qn("w:sz"), str(size))
    el.set(qn("w:color"), "000000")
    borders.append(el)


def _hex(color) -> str | None:
    try:
        return color.hexval()[2:] if color is not None and hasattr(color, "hexval") else None
    except Exception:  # noqa: BLE001
        return None


ALIGN = {0: "LEFT", 1: "CENTER", 2: "RIGHT", 4: "JUSTIFY"}


def _paragraph(doc, fl, container=None) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    style = fl.style
    text = _plain(getattr(fl, "text", ""))
    target = container if container is not None else doc
    p = target.add_paragraph()
    run = p.add_run(text)
    run.bold = _bold(getattr(fl, "text", ""), style.fontName)
    run.font.size = Pt(max(7, min(float(style.fontSize), 18)))
    run.font.name = "Times New Roman" if "Times" in style.fontName else "Arial"
    p.alignment = getattr(WD_ALIGN_PARAGRAPH, ALIGN.get(style.alignment, "LEFT"))
    p.paragraph_format.space_after = Pt(min(float(getattr(style, "spaceAfter", 0) or 0), 14))


def _cell_text(value) -> tuple[str, bool | None]:
    from reportlab.platypus import Paragraph

    if isinstance(value, Paragraph):
        return _plain(value.text), _bold(value.text, value.style.fontName)
    if isinstance(value, (list, tuple)):
        parts = [_cell_text(v) for v in value]
        return "\n".join(t for t, _ in parts if t), any(b for _, b in parts if b)
    if value is None:
        return "", None
    return str(value), None


def _table(doc, fl) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    rows = fl._cellvalues
    if not rows:
        return
    ncols = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncols)
    styles = getattr(fl, "_cellStyles", None) or []
    for ri, row in enumerate(rows):
        for ci in range(ncols):
            value = row[ci] if ci < len(row) else ""
            text, bold = _cell_text(value)
            cell = table.cell(ri, ci)
            p = cell.paragraphs[0]
            run = p.add_run(text)
            cs = styles[ri][ci] if ri < len(styles) and ci < len(styles[ri]) else None
            font = getattr(cs, "fontname", "") if cs is not None else ""
            run.bold = bold if bold is not None else "Bold" in (font or "")
            size = getattr(cs, "fontsize", 8.5) if cs is not None else 8.5
            run.font.size = Pt(max(7, min(float(size or 8.5), 14)))
            align = (getattr(cs, "alignment", "LEFT") or "LEFT").upper() if cs is not None else "LEFT"
            p.alignment = getattr(WD_ALIGN_PARAGRAPH, {"DECIMAL": "RIGHT"}.get(align, align), WD_ALIGN_PARAGRAPH.LEFT)
    # shading (the current year's column) and the rules above and below totals
    def cells(start, stop):
        (c0, r0), (c1, r1) = start, stop
        c0, c1 = (c0 % ncols, c1 % ncols)
        r0, r1 = (r0 % len(rows), r1 % len(rows))
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                yield table.cell(r, c)

    for cmd in getattr(fl, "_bkgrndcmds", []) or []:
        if cmd[0] == "BACKGROUND" and (h := _hex(cmd[3])) and h.lower() not in ("ffffff",):
            for cell in cells(cmd[1], cmd[2]):
                _shade(cell, h)
    for cmd in getattr(fl, "_linecmds", []) or []:
        op = cmd[0]
        side = {"LINEABOVE": "top", "LINEBELOW": "bottom"}.get(op)
        if side:
            for cell in cells(cmd[1], cmd[2]):
                _border(cell, side, 8 if (cmd[3] or 0) > 0.8 else 4)


def _walk(doc, flowables) -> None:
    from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Paragraph, Spacer, Table

    from docx.shared import Pt

    from .fs_report import STATEMENTS, TITLES

    for fl in flowables:
        sec = getattr(fl, "_sec", None)
        if sec in TITLES:  # the PDF draws each part's title in its page header: here it heads the part
            p = doc.add_paragraph()
            r = p.add_run(TITLES[sec])
            r.bold, r.font.size = True, Pt(11)
            if sec in STATEMENTS or sec == "notes":
                small = doc.add_paragraph().add_run("(all amounts in Sri Lanka Rupees)")
                small.bold, small.font.size = True, Pt(7.5)
            continue
        if isinstance(fl, PageBreak) and not isinstance(fl, CondPageBreak):
            doc.add_page_break()
        elif isinstance(fl, Paragraph):
            _paragraph(doc, fl)
        elif isinstance(fl, Table):
            _table(doc, fl)
            doc.add_paragraph()
        elif isinstance(fl, KeepTogether):
            _walk(doc, getattr(fl, "_content", []))
        elif isinstance(fl, Spacer):
            if getattr(fl, "height", 0) > 20:
                doc.add_paragraph()
        elif hasattr(fl, "_content"):
            _walk(doc, fl._content)


def render(st: dict) -> bytes:
    """The financial statements (companies, partnerships and sole proprietors with books) as a .docx."""
    docx = _docx()
    from docx.shared import Mm, Pt

    from .fs_report import _Report

    report = _Report(st)
    report.build()  # two passes: the contents page gets its page numbers
    doc = docx.Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Mm(210), Mm(297)
    section.left_margin, section.right_margin, section.top_margin, section.bottom_margin = Mm(20), Mm(18), Mm(20), Mm(20)
    doc.styles["Normal"].font.name = "Arial"
    doc.styles["Normal"].font.size = Pt(9)
    header = section.header.paragraphs[0]
    header.text = report.legal + ("  —  DRAFT" if report.draft else "")
    if report.dummy:
        p = doc.add_paragraph()
        r = p.add_run("ILLUSTRATIVE - DUMMY DATA MADE UP FROM A STORY; NOT A CLIENT'S ACCOUNTS")
        r.bold = True
    _walk(doc, report.story())
    doc.core_properties.title = f"{report.legal} - Financial statements"
    doc.core_properties.author = "AFIT Connect"
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def render_sections(title: str, sections, e: dict) -> bytes:
    """Simple tables (an individual's statement of income and expenses) as a .docx."""
    docx = _docx()
    doc = docx.Document()
    doc.add_heading(f"{e.get('legal_name') or ''} - {title}", level=1)
    for sec_title, rows, header in sections:
        doc.add_heading(sec_title, level=2)
        table = doc.add_table(rows=1, cols=len(header))
        table.style = "Table Grid"
        for i, h in enumerate(header):
            table.rows[0].cells[i].text = str(h)
        for row in rows:
            cells = table.add_row().cells
            for i, v in enumerate(row[: len(header)]):
                cells[i].text = "" if v is None else str(v)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
