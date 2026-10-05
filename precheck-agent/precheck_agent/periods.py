"""Which financial year each document belongs to — in code, no model.

A job folder often holds two years side by side: last year's finished pack (final trial
balance, signed financial statements) and what the client has sent for this year. The
pre-check checks this year's documents and uses last year's as the baseline. Years are named by
the year they end in, as in "for the year ended 31 March 2026" = 2026.

Evidence for a document's year, strongest first:
1. a folder named for the year ("…/2025/", "FY2025", "FY25");
2. a date range in the file name ("…_2025-04-01_2026-03-31.xlsx" ends in 2026);
3. the period stated inside it ("For the year ended 31 March 2025", "As at 31 March 2025",
   "For the period 1 April 2024 to 31 March 2025");
4. a single year in the file name ("Medical Locum 2025 - SOE.pdf").
"""
import re
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"], start=1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DMY = rf"(\d{{1,2}})\s*{_MON}\s*,?\s*(20\d\d)"
_PERIOD = re.compile(rf"(?:year|period)\s*ended\s*{_DMY}|as\s*at\s*{_DMY}|to\s*{_DMY}", re.I)
_FOLDER_YEAR = re.compile(r"^(?:fy\s*)?(20\d\d)$|^fy\s*(\d\d)$", re.I)
_RANGE = re.compile(r"(20\d\d)-(\d\d)-(\d\d)\D{1,3}(20\d\d)-(\d\d)-(\d\d)")
_SINGLE = re.compile(r"(?<![\d-])(20\d\d)(?![\d-])")
_FY_NAME = re.compile(r"\bfy\s*(\d\d|20\d\d)\b", re.I)


def _month(text: str) -> int:
    text = text.lower()
    return next(n for name, n in MONTHS.items() if name.startswith(text[:3]))


def period_end(text: str) -> date | None:
    """The first "year ended / as at / to <date>" in the text."""
    m = _PERIOD.search(text)
    if not m:
        return None
    day, mon, year = next(g for g in (m.groups()[0:3], m.groups()[3:6], m.groups()[6:9]) if g[0])
    try:
        return date(int(year), _month(mon), int(day))
    except ValueError:
        return None


def _fy(two_or_four: str) -> int:
    n = int(two_or_four)
    return n if n > 100 else 2000 + n


def doc_year(file_row: dict, parsed: dict) -> tuple[int | None, str]:
    """(financial year the document belongs to, how that was decided)."""
    for part in reversed([p for p in (file_row.get("path") or "").split("/") if p]):
        m = _FOLDER_YEAR.match(part.strip())
        if m:
            return _fy(m.group(1) or m.group(2)), f"folder {part}"
    name = file_row.get("name", "")
    m = _RANGE.search(name)
    if m:
        return int(m.group(4)), "dates in the file name"
    head = " ".join(b["text"] for b in parsed.get("blocks", [])[:40])
    end = period_end(head)
    if end:
        return end.year, "period stated in the document"
    m = _FY_NAME.search(name)
    if m:
        return _fy(m.group(1)), "FY in the file name"
    years = _SINGLE.findall(name)
    if len(set(years)) == 1:
        return int(years[0]), "year in the file name"
    return None, ""


def assign_years(docs: list[dict], job: dict | None = None) -> dict:
    """{"current", "prior", "split", "by_file": {file_id: {"year", "role", "basis"}}}.

    The current year is the latest year any document belongs to — or the year in the job's
    title when it names one. "split" is True when the folder holds both years, which is when
    last year's documents become the baseline instead of something to check."""
    by_file = {}
    for d in docs:
        year, basis = doc_year(d["file"], d["parsed"])
        by_file[d["file"]["file_id"]] = {"year": year, "basis": basis}
    years = sorted({v["year"] for v in by_file.values() if v["year"]})
    title_year = None
    m = re.search(r"\bfy\s*(\d\d|20\d\d)\b|(?<!\d)(20\d\d)(?!\d)", (job or {}).get("title", ""), re.I)
    if m:
        title_year = _fy(m.group(1) or m.group(2))
    current = title_year or (years[-1] if years else None)
    prior = current - 1 if current else None
    for v in by_file.values():
        y = v["year"]
        v["role"] = ("unknown" if y is None else "current" if y >= (current or 0) else "prior" if y == prior else "older")
    split = any(v["role"] == "current" for v in by_file.values()) and any(v["role"] in ("prior", "older") for v in by_file.values())
    return {"current": current, "prior": prior, "split": split, "by_file": by_file}


def year_label(role: str, year: int | None) -> str:
    if role == "current":
        return f"this year (FY{year})"
    if role == "prior":
        return f"last year's pack (FY{year})"
    if role == "older":
        return f"an earlier year (FY{year})"
    return "year not stated"
