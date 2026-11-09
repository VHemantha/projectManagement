"""The documents of a GST reconciliation, from the Google Drive link(s) the accountant gives: a folder
(read with everything inside it) or single files, several separated by ";" or new lines. Read-only;
nothing is written to Drive.

Each file becomes a Source: S1, S2, ... in a stable order (by path and name), with its sheets read
in full (every row, values as the file holds them) or, for a PDF or document, its text by page.
"""
import csv
import io
import re
from dataclasses import dataclass, field

from ..drive import DriveError, DriveFile, get_drive
from ..parsing import parse_file

MAX_ROWS = 200_000  # a year's general ledger fits
MAX_FILES = 80
TABLE_EXT = ("xlsx", "xlsm", "csv")
_FILE = re.compile(r"/file/d/([\w-]{10,})|/(?:document|spreadsheets|presentation)/d/([\w-]{10,})|[?&]id=([\w-]{10,})")
_FOLDER = re.compile(r"/folders/([\w-]{10,})")


class SourceProblem(Exception):
    """A link that can't be read: shown to the accountant as it is."""


@dataclass
class Source:
    sid: str
    name: str
    path: str
    url: str
    version: str
    ext: str
    sheets: list[dict] = field(default_factory=list)  # [{"name", "rows": [(row_no, [values])]}]
    text: list[dict] = field(default_factory=list)  # [{"text", "loc", "page"}]
    error: str = ""
    kind: str = "other"
    kind_how: str = ""  # name | headings | ai | accountant
    role: str = ""  # an accountant's own link for "ar_ageing" / "ap_ageing"

    def ref(self, sheet: str = "", row: int | None = None, page: int | None = None) -> str:
        where = f", sheet '{sheet}' row {row}" if sheet else (f", page {page}" if page else "")
        return f"{self.sid} {self.name}{where}"

    def brief(self) -> dict:
        return {"sid": self.sid, "name": self.name, "path": self.path, "url": self.url, "kind": self.kind, "kind_how": self.kind_how,
                "error": self.error, "rows": sum(len(s["rows"]) for s in self.sheets), "pages": len({t.get("page") for t in self.text})}


def parse_links(text: str) -> list[tuple[str, str]]:
    """[("folder" | "file", id)] from what the accountant pasted. Local links (tests, demo):
    local://<folder> or local://<folder>/<path to a file>."""
    out = []
    for part in [p.strip() for p in re.split(r"[;\n]+", text or "") if p.strip()]:
        if part.startswith("local://"):
            rest = part[len("local://"):].strip("/")
            folder, _, rel = rest.partition("/")
            out.append(("file", f"{folder}:{rel}") if rel else ("folder", folder))
            continue
        if m := _FOLDER.search(part):
            out.append(("folder", m.group(1)))
        elif m := _FILE.search(part):
            out.append(("file", next(g for g in m.groups() if g)))
        elif re.fullmatch(r"[\w-]{20,}", part):
            out.append(("folder", part))  # a bare Drive id: taken as a folder
        else:
            raise SourceProblem(f"“{part[:80]}” isn't a Google Drive folder or file link. Copy the link from Drive's Share button.")
    return out


def _rows_xlsx(data: bytes) -> list[dict]:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if i > MAX_ROWS:
                break
            values = list(row)
            while values and values[-1] in (None, ""):
                values.pop()
            if values and any(v not in (None, "") for v in values):
                rows.append((i, values))
        sheets.append({"name": ws.title, "rows": rows})
    return sheets


def _rows_csv(data: bytes) -> list[dict]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1252", errors="replace")
    rows = []
    for i, values in enumerate(csv.reader(io.StringIO(text)), start=1):
        if i > MAX_ROWS:
            break
        while values and not values[-1].strip():
            values.pop()
        if values:
            rows.append((i, values))
    return [{"name": "CSV", "rows": rows}]


def read(file: DriveFile, data: bytes, name: str, mime: str, sid: str, path: str = "") -> Source:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    src = Source(sid=sid, name=file.name, path=path or file.path, url=file.web_url, version=file.version, ext=ext)
    if not data:
        src.error = "The file is empty, too large or a Google file type that can't be read."
        return src
    try:
        if ext in ("xlsx", "xlsm") or "spreadsheetml" in mime:
            src.ext, src.sheets = "xlsx", _rows_xlsx(data)
        elif ext == "csv" or mime == "text/csv":
            src.ext, src.sheets = "csv", _rows_csv(data)
        else:
            parsed = parse_file(data, name, mime)
            if parsed.get("error"):
                src.error = parsed["error"]
            elif parsed.get("vision"):
                src.error = "A scanned image: export the report as PDF text, Excel or CSV and add it again."
            src.text = [{"text": b["text"], "loc": b.get("loc", ""), "page": b.get("page")} for b in parsed.get("blocks", [])]
            if not src.text and not src.error:
                src.error = "No text could be read (a scan?). Export the report as PDF text, Excel or CSV."
    except Exception as exc:  # corrupt or password-protected
        src.error = f"Could not read this file ({type(exc).__name__})."
    return src


def gather(links: str, extra: dict[str, str] | None = None, drive=None) -> list[Source]:
    """Every file behind the links, read. extra: {"ar_ageing": link, "ap_ageing": link} for the
    ageing reports the accountant gave separately (their role is then fixed)."""
    drive = drive or get_drive()
    found: list[tuple[DriveFile, str]] = []
    seen: set[str] = set()

    def add(text: str, role: str = ""):
        try:
            refs = parse_links(text)
        except SourceProblem:
            raise
        for kind, ident in refs:
            try:
                files = drive.list_folder(ident) if kind == "folder" else [drive.get_file(ident)]
            except DriveError as exc:
                raise SourceProblem(str(exc)) from exc
            for f in files:
                if f.id not in seen:
                    seen.add(f.id)
                    found.append((f, role))
                elif role:  # the same file given again for a role: keep the role
                    found[:] = [(g, role if g.id == f.id else r) for g, r in found]

    add(links)
    for role, link in (extra or {}).items():
        if link and link.strip():
            add(link, role)
    if not found:
        raise SourceProblem("No files were found behind the link. Check the folder holds the documents and is shared with the service.")
    found.sort(key=lambda fr: (fr[0].path.lower(), fr[0].name.lower()))
    sources = []
    for n, (f, role) in enumerate(found[:MAX_FILES], start=1):
        try:
            data, name, mime = drive.download(f)
        except Exception as exc:  # one unreadable file never stops the run
            data, name, mime = b"", f.name, f.mime_type
            src = Source(sid=f"S{n}", name=f.name, path=f.path, url=f.web_url, version=f.version, ext="", error=f"Download failed ({type(exc).__name__}).")
        else:
            src = read(f, data, name, mime, f"S{n}")
        src.role = role
        sources.append(src)
    return sources


def table_rows(src: Source) -> list[tuple[str, int, list]]:
    """Every row of every sheet: (sheet, row number, values)."""
    return [(sh["name"], row_no, values) for sh in src.sheets for row_no, values in sh["rows"]]


def full_text(src: Source, limit: int = 60_000) -> str:
    """The text of a document (or a sheet written out), each line with its place, for the model."""
    lines = []
    if src.text:
        for t in src.text:
            lines.append(f"[{t['loc'] or ('page ' + str(t['page']))}] {t['text']}")
    else:
        for sheet, row_no, values in table_rows(src):
            lines.append(f"[sheet '{sheet}' row {row_no}] " + " | ".join("" if v is None else str(v) for v in values))
    text = "\n".join(lines)
    return text[:limit]
