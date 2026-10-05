"""Turn files into text and tables with libraries, never with a model (token rule 1: code
before model — parsing costs no tokens). Emails are read here too. The one exception is a
file with no text in it at all — a picture or a scanned PDF: this module only marks it
("vision"), and vision.py has the reader model write out what it says.

A parsed document is plain JSON so it can be cached by file id + version + parser version:

    {"blocks": [{"text", "loc", "section", "sheet", "row", "a1", "page"}],
     "tables": [{"name", "rows": [[row_number, [cell, ...]], ...]}]}

A block is one citable unit: a spreadsheet row, a paragraph, a line of a page. Readers cite
blocks, so every finding can point at an exact row or passage.
"""
import csv
import io
import re

from .config import get_settings

MAX_ROWS_PER_SHEET = 4000
MAX_COLS = 30
MAX_BLOCK_CHARS = 700

GOOGLE_EXPORTS = {
    "application/vnd.google-apps.spreadsheet": (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".xlsx",
    ),
    "application/vnd.google-apps.document": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".docx",
    ),
    "application/vnd.google-apps.presentation": ("application/pdf", ".pdf"),
}


_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def scrub(value):
    """Drop NUL and other control characters (keeping tab and new line) from every string in a
    parsed document. Postgres cannot store NUL in text, and none of them carry meaning."""
    if isinstance(value, str):
        return _CONTROL.sub("", value)
    if isinstance(value, list):
        return [scrub(v) for v in value]
    if isinstance(value, dict):
        return {k: scrub(v) for k, v in value.items()}
    return value


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".") if value != int(value) else str(int(value))
    return re.sub(r"\s+", " ", str(value)).strip()


def _col_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _sheet_blocks(name: str, rows: list[tuple[int, list]]):
    """Rows of one sheet -> (blocks, table). Empty rows are dropped."""
    blocks, table_rows = [], []
    for row_no, values in rows:
        cells = [_cell(v) for v in values[:MAX_COLS]]
        while cells and not cells[-1]:
            cells.pop()
        if not any(cells):
            continue
        table_rows.append([row_no, [v if isinstance(v, (int, float)) and not isinstance(v, bool) else _cell(v) for v in values[: len(cells)]]])
        text = f"row {row_no}: " + " | ".join(cells)
        blocks.append(
            {
                "text": text[:MAX_BLOCK_CHARS],
                "loc": f"sheet '{name}', row {row_no}",
                "section": f"sheet:{name}",
                "sheet": name,
                "row": row_no,
                "a1": f"A{row_no}:{_col_letter(max(len(cells) - 1, 0))}{row_no}",
                "page": None,
            }
        )
    return blocks, {"name": name, "rows": table_rows}


def _parse_xlsx(data: bytes) -> dict:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks, tables = [], []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if i > MAX_ROWS_PER_SHEET:
                break
            rows.append((i, list(row)))
        b, t = _sheet_blocks(ws.title, rows)
        blocks += b
        tables.append(t)
    return {"blocks": blocks, "tables": tables}


def _parse_csv(data: bytes, name: str) -> dict:
    text = data.decode("utf-8-sig", "replace")
    rows = [(i, row) for i, row in enumerate(csv.reader(io.StringIO(text)), start=1) if i <= MAX_ROWS_PER_SHEET]
    blocks, table = _sheet_blocks(name.rsplit(".", 1)[0], rows)
    return {"blocks": blocks, "tables": [table]}


def _text_block(text: str, loc: str, section: str, page=None):
    return {"text": text[:MAX_BLOCK_CHARS], "loc": loc, "section": section, "sheet": None, "row": None, "a1": None, "page": page}


def _parse_docx(data: bytes) -> dict:
    from docx import Document

    doc = Document(io.BytesIO(data))
    blocks, tables = [], []
    n = 0
    for para in doc.paragraphs:
        text = re.sub(r"\s+", " ", para.text).strip()
        if text:
            n += 1
            blocks.append(_text_block(text, f"paragraph {n}", "body"))
    for t_index, table in enumerate(doc.tables, start=1):
        rows = [(i, [c.text for c in row.cells]) for i, row in enumerate(table.rows, start=1)]
        b, t = _sheet_blocks(f"table {t_index}", rows)
        for block in b:
            block["loc"] = block["loc"].replace("sheet ", "", 1)
            block["sheet"], block["a1"] = None, None
        blocks += b
        tables.append(t)
    return {"blocks": blocks, "tables": tables}


def _parse_pdf(data: bytes) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        return {"blocks": [], "tables": [], "error": "This PDF is password-protected."}
    blocks = []
    for page_no, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        for line in text.splitlines():
            line = re.sub(r"\s+", " ", line).strip()
            if line:
                blocks.append(_text_block(line, f"page {page_no}", f"page:{page_no}", page=page_no))
    if sum(len(b["text"]) for b in blocks) < 25 * max(len(reader.pages), 1):
        return {"blocks": [], "tables": [], "vision": "pdf"}  # a scan: pages are pictures
    return {"blocks": blocks, "tables": []}


def _parse_text(data: bytes) -> dict:
    blocks = []
    for i, line in enumerate(data.decode("utf-8-sig", "replace").splitlines(), start=1):
        line = line.strip()
        if line:
            blocks.append(_text_block(line, f"line {i}", "body"))
    return {"blocks": blocks, "tables": []}


def _lines(lines, label: str, section: str) -> dict:
    return {"blocks": [_text_block(line, f"{label} {i}", section) for i, line in enumerate(lines, start=1) if line], "tables": []}


def _parse_email(data: bytes, name: str) -> dict:
    """The email itself: who, when, subject, what is attached, then the body. Its attachments
    are documents of their own (see archives.attachments)."""
    from .emails import email_lines, read_email

    return _lines(email_lines(read_email(data, name)), "email line", "email")


def _parse_html(data: bytes) -> dict:
    from .emails import html_to_text

    return _lines(html_to_text(data.decode("utf-8-sig", "replace")).splitlines(), "line", "body")


def _parse_svg(data: bytes) -> dict:
    """A drawing saved as SVG is text already: its labels are read without a model."""
    from xml.etree import ElementTree

    root = ElementTree.fromstring(data)
    texts = [re.sub(r"\s+", " ", "".join(el.itertext())).strip() for el in root.iter() if el.tag.rsplit("}", 1)[-1] in ("text", "title", "desc")]
    parsed = _lines([t for t in texts if t], "label", "image")
    return parsed if parsed["blocks"] else {"blocks": [], "tables": [], "error": "This drawing has no text to read."}


def parse_file(data: bytes, name: str, mime_type: str = "") -> dict:
    """Parse by extension first, then MIME type. Unknown or unreadable files give no blocks and
    an "error" the rules report — they are never sent to a model as raw bytes. A picture or a
    scanned PDF comes back marked "vision": the caller decides whether to have it read."""
    from .emails import is_email
    from .vision import is_image

    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    try:
        if is_email(name, mime_type):
            return _parse_email(data, name)
        if ext == "svg" or "svg" in mime_type:
            return _parse_svg(data)
        if is_image(name, mime_type):
            return {"blocks": [], "tables": [], "vision": "image"}
        if ext in ("html", "htm") or mime_type == "text/html":
            return _parse_html(data)
        if ext in ("xlsx", "xlsm") or "spreadsheetml" in mime_type:
            return _parse_xlsx(data)
        if ext == "csv" or mime_type == "text/csv":
            return _parse_csv(data, name)
        if ext == "docx" or "wordprocessingml" in mime_type:
            return _parse_docx(data)
        if ext == "pdf" or mime_type == "application/pdf":
            return _parse_pdf(data)
        if ext in ("txt", "md") or mime_type.startswith("text/"):
            return _parse_text(data)
    except Exception as exc:  # corrupt or password-protected file
        return {"blocks": [], "tables": [], "error": f"Could not read this file ({type(exc).__name__})."}
    return {"blocks": [], "tables": [], "error": "This file type is not read by the pre-check."}


def _section_label(blocks: list[dict]) -> str:
    first, last = blocks[0], blocks[-1]
    if first.get("sheet"):
        if first["row"] == last["row"]:
            return f"sheet '{first['sheet']}', row {first['row']}"
        return f"sheet '{first['sheet']}', rows {first['row']}–{last['row']}"
    if first.get("page"):
        return f"page {first['page']}"
    return first["loc"] if first["loc"] == last["loc"] else f"{first['loc']}–{last['loc'].split(' ')[-1]}"


def _looks_like_header(block: dict) -> bool:
    cells = block["text"].split(": ", 1)[-1].split(" | ")
    texty = [c for c in cells if c and not re.fullmatch(r"[\d.,()\-£$€% ]+", c)]
    return len(texty) >= 2 and len(texty) >= len([c for c in cells if c]) * 0.6


def chunk_blocks(blocks: list[dict], chunk_tokens: int | None = None) -> list[dict]:
    """Group consecutive blocks of the same section into chunks of about `chunk_tokens`. In a
    sheet, the header row is repeated at the top of each later chunk so a row of numbers still
    says what its columns are."""
    from .textutil import est_tokens

    limit = chunk_tokens or get_settings().chunk_tokens
    chunks: list[dict] = []
    current: list[dict] = []
    size = 0
    header: dict | None = None
    section = None

    def flush():
        nonlocal current, size
        if current:
            chunks.append({"location": _section_label([b for b in current if not b.get("is_header")] or current), "blocks": current})
        current, size = [], 0

    for block in blocks:
        if block["section"] != section:
            flush()
            section, header = block["section"], None
            if block.get("sheet") and _looks_like_header(block):
                header = block
        tokens = est_tokens(block["text"])
        if current and size + tokens > limit:
            flush()
            if header is not None and block is not header:
                current.append({**header, "is_header": True})
                size += est_tokens(header["text"])
        current.append(block)
        size += tokens
    flush()
    return chunks
