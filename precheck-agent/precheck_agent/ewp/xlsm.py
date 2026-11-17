"""Writing values into a macro-enabled workbook without disturbing it (AFIT, 16 Nov 2026).

openpyxl rewrites a whole workbook when it saves: on the firm's template it drops the custom XML, the
dynamic-array metadata, the VBA project's relationships, the printer settings and the links to the
sheets' controls and drawings. So cells are written here straight into each sheet's XML inside the
.xlsm: every other part of the file is copied byte for byte, and Excel recalculates every formula
when the file is opened (calcPr fullCalcOnLoad).

A cell holding a formula (plain, shared or array) is never overwritten, nor a cell inside a merged
range other than its first cell. Those are refused and reported back."""
from __future__ import annotations

import io
import re
import zipfile
from datetime import date, datetime
from decimal import Decimal

from lxml import etree

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_Q = "{%s}" % NS
_CELL = re.compile(r"^([A-Z]{1,3})(\d+)$")


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def split(coord: str) -> tuple[int, int]:
    m = _CELL.match(coord.upper().replace("$", ""))
    if not m:
        raise ValueError(f"Not a cell reference: {coord}")
    return col_index(m.group(1)), int(m.group(2))


def sheet_paths(z: zipfile.ZipFile) -> dict[str, str]:
    """{sheet name: path of its XML part}."""
    wb = etree.fromstring(z.read("xl/workbook.xml"))
    rels = etree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    targets = {r.get("Id"): r.get("Target") for r in rels.findall(f"{{{PKG_REL}}}Relationship")}
    out = {}
    for s in wb.iter(f"{_Q}sheet"):
        target = targets.get(s.get(f"{{{REL}}}id"), "")
        out[s.get("name")] = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
    return out


def _date1904(z: zipfile.ZipFile) -> bool:
    pr = etree.fromstring(z.read("xl/workbook.xml")).find(f"{_Q}workbookPr")
    return pr is not None and pr.get("date1904") in ("1", "true")


def serial(d: date, date1904: bool = False) -> float:
    base = datetime(1904, 1, 1) if date1904 else datetime(1899, 12, 30)
    dt = d if isinstance(d, datetime) else datetime(d.year, d.month, d.day)
    return (dt - base).total_seconds() / 86400


def _merged(root) -> list[tuple[int, int, int, int]]:
    out = []
    for m in root.iter(f"{_Q}mergeCell"):
        a, _, b = m.get("ref", "").partition(":")
        if a and b:
            (c1, r1), (c2, r2) = split(a), split(b)
            out.append((r1, c1, r2, c2))
    return out


def _row(sheet_data, r: int):
    rows = sheet_data.findall(f"{_Q}row")
    for row in rows:
        n = int(row.get("r", "0"))
        if n == r:
            return row
        if n > r:
            new = etree.Element(f"{_Q}row", r=str(r))
            row.addprevious(new)
            return new
    new = etree.SubElement(sheet_data, f"{_Q}row", r=str(r))
    return new


def _cell(row, coord: str, col: int):
    for c in row.findall(f"{_Q}c"):
        cc, _ = split(c.get("r"))
        if cc == col:
            return c
        if cc > col:
            new = etree.Element(f"{_Q}c", r=coord)
            c.addprevious(new)
            return new
    new = etree.SubElement(row, f"{_Q}c", r=coord)
    return new


def _number(v) -> str:
    if isinstance(v, bool):
        return "1" if v else "0"
    d = Decimal(str(v))
    text = format(d.normalize(), "f") if d == d.to_integral() else format(d, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _set(c, value, kind: str, date1904: bool) -> None:
    for child in list(c):
        c.remove(child)
    c.attrib.pop("t", None)
    if value is None or value == "":
        return
    if kind == "formula":
        f = etree.SubElement(c, f"{_Q}f")
        f.text = str(value).lstrip("=")
        return
    if kind == "date":
        if isinstance(value, str):
            value = date.fromisoformat(value[:10])
        etree.SubElement(c, f"{_Q}v").text = _number(round(serial(value, date1904), 6))
        return
    if kind in ("money", "number", "percent") or (kind == "" and isinstance(value, (int, float, Decimal)) and not isinstance(value, bool)):
        etree.SubElement(c, f"{_Q}v").text = _number(value)
        return
    c.set("t", "inlineStr")
    is_ = etree.SubElement(c, f"{_Q}is")
    t = etree.SubElement(is_, f"{_Q}t")
    t.text = str(value)
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")


def _xml(root) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def patch(data: bytes, cells: list[dict], protected: dict[str, set[str]] | None = None) -> tuple[bytes, list[dict]]:
    """Write cells [{"sheet", "cell", "value", "kind"}] (kind: money | number | percent | date | text |
    formula) into the workbook. Returns (the new workbook, the cells refused with their reason).
    `protected` is the template's own formula cells by sheet: when given, those are refused (and a
    value the agent wrote earlier as a sum can be changed); without it, any cell holding a formula is."""
    src = zipfile.ZipFile(io.BytesIO(data))
    paths = sheet_paths(src)
    d1904 = _date1904(src)
    refused, by_sheet = [], {}
    for c in cells:
        if c["sheet"] not in paths:
            refused.append({**c, "reason": f"The workbook has no sheet '{c['sheet']}'."})
            continue
        by_sheet.setdefault(c["sheet"], []).append(c)
    changed: dict[str, bytes] = {}
    for sheet, items in by_sheet.items():
        root = etree.fromstring(src.read(paths[sheet]), parser=etree.XMLParser(huge_tree=True, remove_blank_text=False))
        data_el = root.find(f"{_Q}sheetData")
        merged = _merged(root)
        for item in items:
            try:
                col, r = split(item["cell"])
            except ValueError as exc:
                refused.append({**item, "reason": str(exc)})
                continue
            inside = next(((r1, c1) for r1, c1, r2, c2 in merged if r1 <= r <= r2 and c1 <= col <= c2), None)
            if inside and inside != (r, col):
                refused.append({**item, "reason": "Inside a merged range (only its first cell takes a value)."})
                continue
            coord = item["cell"].upper()
            if protected is not None:
                guarded = coord in protected.get(sheet, set())
            else:
                existing = next((c for c in data_el.iter(f"{_Q}c") if c.get("r") == coord), None)
                guarded = existing is not None and existing.find(f"{_Q}f") is not None
            if guarded:
                refused.append({**item, "reason": "The template has a formula here; it is never overwritten."})
                continue
            _set(_cell(_row(data_el, r), coord, col), item.get("value"), item.get("kind", ""), d1904)
        changed[paths[sheet]] = _xml(root)
    if changed:
        wb = etree.fromstring(src.read("xl/workbook.xml"))
        calc = wb.find(f"{_Q}calcPr")
        if calc is None:
            calc = etree.SubElement(wb, f"{_Q}calcPr")
        calc.set("fullCalcOnLoad", "1")
        changed["xl/workbook.xml"] = _xml(wb)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as dst:
        for info in src.infolist():
            body = changed.get(info.filename)
            if body is None:
                dst.writestr(info, src.read(info.filename))
            else:
                dst.writestr(info, body, compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue(), refused


def formula_cells(data: bytes, sheet: str) -> set[str]:
    """The cells of a sheet holding a formula (plain, shared or array)."""
    z = zipfile.ZipFile(io.BytesIO(data))
    root = etree.fromstring(z.read(sheet_paths(z)[sheet]), parser=etree.XMLParser(huge_tree=True))
    return {c.get("r") for c in root.iter(f"{_Q}c") if c.find(f"{_Q}f") is not None}


def read(data: bytes, sheet: str, coords: list[str]) -> dict[str, object]:
    """Cell values as stored (numbers as floats, inline/shared strings as text, formulas as "=..."): for checks and tests."""
    z = zipfile.ZipFile(io.BytesIO(data))
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in etree.fromstring(z.read("xl/sharedStrings.xml")).iter(f"{_Q}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{_Q}t")))
    root = etree.fromstring(z.read(sheet_paths(z)[sheet]), parser=etree.XMLParser(huge_tree=True))
    want = {c.upper() for c in coords}
    out: dict[str, object] = {c: None for c in want}
    for c in root.iter(f"{_Q}c"):
        r = c.get("r")
        if r not in want:
            continue
        f = c.find(f"{_Q}f")
        if f is not None:
            out[r] = "=" + (f.text or "")
            continue
        t = c.get("t")
        if t == "inlineStr":
            out[r] = "".join(x.text or "" for x in c.iter(f"{_Q}t"))
        elif t == "s":
            v = c.find(f"{_Q}v")
            out[r] = shared[int(v.text)] if v is not None else None
        else:
            v = c.find(f"{_Q}v")
            out[r] = (float(v.text) if t not in ("str", "b", "e") else v.text) if v is not None and v.text is not None else None
    return out
