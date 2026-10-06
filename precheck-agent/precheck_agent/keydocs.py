"""The three documents a pre-check cannot start without — found by code, no model.

1. This year's client questionnaire: it says what changed this year.
2. Last year's financial statements: this year's accounts start from them.
3. Last year's workpapers (trial balance, ledger, schedules, reconciliations): they show how last
   year's balances were built up.

If any is missing the pre-check stops there and drafts one email asking for what is missing,
with the reason for each (AFIT's rule, 5 Oct 2026). Documents inside zips and attached to emails
count: they are indexed as documents of their own.
"""
import re
from datetime import date

from .archives import SEP, display_name

QUESTIONNAIRE = re.compile(r"questionnaire|\bcq\b|year[\s_-]*end[\s_-]*checklist|client (information|details|checklist)|information (sheet|form)", re.I)
FS_CLASSES = ("financial_statements", "prior_year_statements")
WP_CLASSES = ("workpaper", "trial_balance", "general_ledger", "schedule", "reconciliation")

KEY = {
    "questionnaire": {
        "label": "Client questionnaire",
        "ask": "Your completed client questionnaire for {this_year}",
        "why": "It tells us what changed this year (properties, bank accounts, loans, assets, income), so we can work out "
               "exactly what else we need and ask you once rather than several times.",
    },
    "last_year_fs": {
        "label": "Last year's financial statements",
        "ask": "Last year's financial statements ({last_year})",
        "why": "This year's accounts start from last year's closing balances, and we compare the two years line by line.",
    },
    "last_year_workpapers": {
        "label": "Last year's workpapers",
        "ask": "Last year's workpapers ({last_year}): trial balance, general ledger and supporting schedules",
        "why": "They show how last year's balances were built up (fixed assets, loans, owner or shareholder accounts), "
               "so this year's opening position is right.",
    },
}


def _fy(year: int | None) -> str:
    return f"the year to 31 March {year}" if year else "this year"


_FILE_LINK = re.compile(r"/file/d/([\w-]{10,})|/(?:document|spreadsheets|presentation)/d/([\w-]{10,})|[?&]id=([\w-]{10,})")
_FOLDER_LINK = re.compile(r"/folders/([\w-]{10,})")


def _norm(path: str) -> str:
    """"\\2025\\Final TB.xlsx " -> "2025/final tb.xlsx": slashes, case and spaces do not matter."""
    parts = [" ".join(p.split()) for p in path.replace("\\", "/").lower().split("/")]
    return "/".join(p for p in parts if p)


def _in_place(files: list[dict], target: str, folders: dict) -> list[dict]:
    """The readable files at one place a person named: a Drive file or folder link, or a path in
    the task folder (a file, or a folder and everything under it, zips and emails included). A
    path may start with the task folder's own name or a parent's: leading parts are dropped
    until something matches."""
    m = _FILE_LINK.search(target)
    if m:
        fid = next(g for g in m.groups() if g)
        return [f for f in files if f["file_id"] == fid or f["file_id"].startswith(fid + SEP)]
    m = _FOLDER_LINK.search(target)
    if m:
        if m.group(1) not in folders:
            return []
        prefix = _norm(folders[m.group(1)])
        return [f for f in files if not prefix or _norm(f.get("path") or "").startswith(prefix)]
    parts = _norm(target).split("/")
    for i in range(len(parts)):
        want = "/".join(parts[i:])
        found = [f for f in files if (full := _norm((f.get("path") or "") + f["name"])) == want or full.startswith(want + "/")]
        if found:
            return found
    return []


def placed(docs: list[dict], text: str, folders: dict | None = None) -> tuple[list[dict], list[str]]:
    """(files, places that matched nothing) for what a person set on the task card: several
    places separated by ";" or new lines."""
    files = [d["file"] for d in docs if not d["file"].get("error") and d["file"].get("document_class") != "archive"]
    out, unmatched = [], []
    for target in (t.strip() for t in re.split(r"[;\n]", text or "")):
        if not target:
            continue
        found = _in_place(files, target, folders or {})
        if not found:
            unmatched.append(target)
        out += [f for f in found if f not in out]
    return out, unmatched


def find(docs: list[dict], periods: dict, paths: dict | None = None, folders: dict | None = None) -> dict:
    """{"documents": [{role, label, found, files, note, set_on_card}], "missing": [roles],
    "wrong_place": [roles]}. `docs` are {"file", "parsed"} with the file row carrying year_role
    (from periods). `paths` is where a person said each document is (task card): that decides it,
    whatever its year or name; a place that holds nothing makes the document missing, as a
    mistake on the card to correct, not something to ask the client for."""
    current, prior = periods.get("current"), periods.get("prior")
    by_role: dict[str, list[dict]] = {"questionnaire": [], "last_year_fs": [], "last_year_workpapers": []}
    older_questionnaires = []
    for d in docs:
        f = d["file"]
        if f.get("error"):
            continue  # an unreadable file does not count as received
        role = f.get("year_role", "unknown")
        is_q = f["document_class"] == "questionnaire" or bool(QUESTIONNAIRE.search(f["name"]))
        if is_q:
            (by_role["questionnaire"] if role in ("current", "unknown") else older_questionnaires).append(f)
            continue
        last_year = role == "prior" or (current is None and role == "unknown")
        if f["document_class"] in FS_CLASSES and (last_year or f["document_class"] == "prior_year_statements"):
            by_role["last_year_fs"].append(f)
        elif f["document_class"] in WP_CLASSES and last_year:
            by_role["last_year_workpapers"].append(f)
    out, wrong_place = [], []
    for role, files in by_role.items():
        note, on_card = "", (paths or {}).get(role, "").strip()
        if on_card:
            files, unmatched = placed(docs, on_card, folders)
            if not files:
                wrong_place.append(role)
                note = (f"Nothing in the task folder is where the task card says ({on_card}). Correct the place on the "
                        f"task card, or clear it to let the pre-check search the folder.")
            else:
                note = "Where the task card says." + (f" Nothing found at: {'; '.join(unmatched)}." if unmatched else "")
        elif role == "questionnaire" and not files and older_questionnaires:
            note = f"Only an earlier year's questionnaire was found ({display_name(older_questionnaires[0])}); this year's is needed."
        out.append({"role": role, "label": KEY[role]["label"], "found": bool(files), "set_on_card": bool(on_card),
                    "files": sorted(files, key=lambda f: f["name"].lower())[:6], "files_all": files, "note": note})
    return {"documents": out, "missing": [d["role"] for d in out if not d["found"]], "wrong_place": wrong_place,
            "this_year": _fy(current), "last_year": _fy(prior) if prior else "last year"}


def request_email(client_name: str, found: dict) -> dict:
    """The email asking for the missing key documents, written by code: each with its reason."""
    lines = []
    for role in [r for r in found["missing"] if r not in found.get("wrong_place", [])]:
        k = KEY[role]
        ask = k["ask"].format(this_year=found["this_year"], last_year=found["last_year"])
        lines.append(f"- {ask}. {k['why']}")
    if not lines:
        return {"subject": "", "body": ""}  # only the task card is wrong: nothing to ask the client
    body = (
        f"Hi {client_name or 'there'},\n\n"
        f"We are getting ready to prepare your accounts for {found['this_year']}. Before we can work out "
        f"everything we need from you, we need the following:\n\n"
        + "\n".join(lines)
        + "\n\nOnce we have these, we will send you one list of anything else we need, with the reason for each item.\n\n"
        "Thank you,\nAFIT"
    )
    return {"subject": f"Information needed to start your accounts for {found['this_year']}", "body": body}


def today() -> date:
    return date.today()
