"""A document attached to a Local Tax card, as the model reads it (AFIT, 22 Nov 2026): a PDF or an image is sent as
it is (Claude reads text, tables and scans); a spreadsheet or CSV is written out as rows, each with its sheet and
row number so the model can cite it; text as text."""
import base64
import csv
import io

IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
MAX_ROWS = 2500


class Unreadable(ValueError):
    pass


def blocks(name: str, data: bytes) -> list[dict]:
    """Anthropic content blocks for the document, then an instruction is added by the caller."""
    lower = name.lower()
    ext = lower[lower.rfind("."):] if "." in lower else ""
    if ext == ".pdf":
        return [{"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": base64.b64encode(data).decode()},
                 "title": name}]
    if ext in IMAGE_TYPES:
        return [{"type": "image", "source": {"type": "base64", "media_type": IMAGE_TYPES[ext], "data": base64.b64encode(data).decode()}}]
    if ext in (".xlsx", ".xlsm"):
        return [{"type": "text", "text": f"DOCUMENT {name}\n" + _workbook(data)}]
    if ext == ".csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig", errors="replace"))))[:MAX_ROWS]
        return [{"type": "text", "text": f"DOCUMENT {name}\n" + "\n".join(f"row {n} | " + " | ".join(r) for n, r in enumerate(rows, start=1))}]
    if ext in (".txt", ".md"):
        return [{"type": "text", "text": f"DOCUMENT {name}\n" + data.decode("utf-8", errors="replace")[:200000]}]
    raise Unreadable("This kind of document can't be read: use PDF, an image, Excel, CSV or text.")


def _workbook(data: bytes) -> str:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise Unreadable("The workbook could not be opened.") from exc
    out, count = [], 0
    for ws in wb.worksheets:
        out.append(f"== sheet {ws.title} ==")
        for n, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if count >= MAX_ROWS:
                out.append("(more rows not shown)")
                return "\n".join(out)
            if any(c not in (None, "") for c in row):
                out.append(f"{ws.title}!row {n} | " + " | ".join("" if c is None else str(c) for c in row))
                count += 1
    return "\n".join(out)
