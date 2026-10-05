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

from .archives import display_name

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


def find(docs: list[dict], periods: dict) -> dict:
    """{"documents": [{role, label, found, files, note}], "missing": [roles]}. `docs` are
    {"file", "parsed"} with the file row carrying year_role (from periods)."""
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
    out = []
    for role, files in by_role.items():
        note = ""
        if role == "questionnaire" and not files and older_questionnaires:
            note = f"Only an earlier year's questionnaire was found ({display_name(older_questionnaires[0])}); this year's is needed."
        out.append({"role": role, "label": KEY[role]["label"], "found": bool(files),
                    "files": sorted(files, key=lambda f: f["name"].lower())[:6], "note": note})
    return {"documents": out, "missing": [d["role"] for d in out if not d["found"]],
            "this_year": _fy(current), "last_year": _fy(prior) if prior else "last year"}


def request_email(client_name: str, found: dict) -> dict:
    """The email asking for the missing key documents, written by code: each with its reason."""
    lines = []
    for role in found["missing"]:
        k = KEY[role]
        ask = k["ask"].format(this_year=found["this_year"], last_year=found["last_year"])
        lines.append(f"- {ask}. {k['why']}")
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
