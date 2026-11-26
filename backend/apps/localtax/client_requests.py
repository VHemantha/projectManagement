"""Changes a client asked for, made through the AI Assistant's chat (AFIT, 26 Nov 2026).

The accountant passes on the client's request ("rent should be Rs. 1.2 million", "the address is now ..."). Local_Tax_AI
answers with the changes it would make; this module checks each one against the engagement and works out what it
changes from and to. Nothing changes until the accountant applies it (views.ClientChangeView), one change at a time:

- field: the client information (name, TIN, address, year end, directors, ...) - applied as the same edit made by hand.
- journal: a figure in the statements, by a balanced journal. The agent names the accounts and the balance the client
  gives ("6100 | =1200000; 2110 | balance"); code works out the difference from the account's current balance and the
  balancing line, so no figure is the AI's arithmetic. Applied as a PROPOSED journal (JE-nnn): it changes the statements
  only once a reviewer approves it in the journal register, like any other.
- tax_adjustment: a tax computation line's amount - a PROPOSED tax adjustment, approved like any other.
- note / policy: the wording of a note the accountant writes, or of an accounting policy.
- heading: where a trial balance account is shown.
A change that names something the engagement does not have is dropped, and the answer says so.
"""
import re
from decimal import Decimal, InvalidOperation

from . import validation as V
from .engine import depth as DP
from .engine import fs as FS

TYPES = ("field", "journal", "tax_adjustment", "note", "policy", "heading")
MAX_CHANGES = 12

# The client information the chat may change: key -> (label, model field or data section).
FIELDS = {
    "legal_name": ("Legal name", "field"), "client_name": ("Client name", "field"), "tin": ("TIN", "field"),
    "nic_or_reg": ("NIC / registration no.", "field"), "address": ("Address", "field"), "activity": ("Business activity", "field"),
    "fy_end": ("Financial year end", "field"), "reporting_framework": ("Reporting framework", "field"), "audited": ("Audited", "field"),
    "expected_tax": ("Expected tax payment", "field"), "directors": ("Directors", "data"), "company_secretary": ("Company secretary", "data"),
    "shares_issued": ("Shares issued", "data"), "fs_scope": ("Financial statements required", "data"),
}
NOTES = {"events": "Events after the reporting period", "contingencies": "Contingent liabilities and commitments",
         "related": "Related party transactions"}


class Stale(ValueError):
    """The balances moved since the journal was proposed: it has been worked out again for the accountant to check."""


def policy_keys() -> dict[str, str]:
    return {p[0]: p[1] for p in DP.POLICY_TEXT}


def _standard_policy(key: str) -> str:
    return next((p[4] for p in DP.POLICY_TEXT if p[0] == key), "")


def current_field(eng, key: str) -> str:
    where = FIELDS[key][1]
    v = getattr(eng, key) if where == "field" else (eng.data or {}).get(key)
    if isinstance(v, bool):
        return "yes" if v else "no"
    return "" if v is None else str(v)


def client_info(eng) -> dict:
    """What the agent sees of the client information, with the keys it may change."""
    return {k: current_field(eng, k) for k in FIELDS}


def notes_editable(eng) -> dict:
    texts = (eng.data or {}).get("note_text") or {}
    return {k: texts.get(k, "") for k in NOTES}


def field_payload(key: str, value: str) -> dict:
    """The PATCH a field change makes (validation.update checks it)."""
    v = value.strip()
    if key == "audited":
        v = v.lower() in ("yes", "true", "audited", "1")
    elif key == "expected_tax":
        v = v.replace(",", "").replace("Rs.", "").replace("LKR", "").strip()
    return {key: v} if FIELDS[key][1] == "field" else {"data": {key: v}}


def _amount(text: str) -> Decimal:
    s = str(text).strip().replace(",", "").replace(" ", "")
    s = re.sub(r"^(rs\.?|lkr)", "", s, flags=re.I)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    return Decimal(s).quantize(Decimal("0.01"))


def journal_lines(value: str, balances: dict[str, dict]) -> list[dict]:
    """The journal's lines from the agent's text, with the amounts worked out by code. `balances`: code -> the account's
    current (adjusted) TB line. Raises ValueError with a reason the accountant can read."""
    lines, balancing = [], None
    for n, part in enumerate(p for p in str(value).split(";") if p.strip()):
        cells = [c.strip() for c in part.split("|")]
        if len(cells) == 2:
            code, name, heading, amount = cells[0], "", "", cells[1]
        elif len(cells) == 4:
            code, name, heading, amount = cells
        else:
            raise ValueError(f"Line {n + 1} of the journal can't be read.")
        known = balances.get(code)
        if known:
            name, heading = known.get("name") or name, known.get("heading") or heading
        elif not name or heading not in FS.HEADINGS:
            raise ValueError(f"Account {code} isn't in the trial balance: a new account needs a name and a heading.")
        line = {"code": code, "name": name, "heading": heading}
        a = amount.strip().lower()
        if a == "balance":
            if balancing is not None:
                raise ValueError("Only one line of the journal can take the balance.")
            balancing = line
            lines.append(line)
            continue
        try:
            if a.startswith("="):
                current = Decimal(str((known or {}).get("amount") or 0))
                line["amount"] = _amount(a[1:]) - current
                line["sets"] = str(_amount(a[1:]))
                line["was"] = str(current)
            else:
                line["amount"] = _amount(a)
        except (InvalidOperation, ValueError):
            raise ValueError(f"Line {n + 1} of the journal has no amount.") from None
        lines.append(line)
    if balancing is not None:
        balancing["amount"] = -sum((ln["amount"] for ln in lines if ln is not balancing), Decimal("0"))
    lines = [ln for ln in lines if ln["amount"] != 0]
    if not lines:
        raise ValueError("The accounts already have the balances asked for: there is nothing to post.")
    if len(lines) < 2:
        raise ValueError("A journal needs a debit and a credit.")
    total = sum((ln["amount"] for ln in lines), Decimal("0"))
    if total != 0:
        raise ValueError(f"The journal doesn't balance: it is out by {total:,.2f}.")
    return [{**ln, "amount": str(ln["amount"])} for ln in lines]


def balances(fs_result) -> dict[str, dict]:
    return {str(ln["code"]): ln for ln in (fs_result or {}).get("lines") or [] if not ln.get("edit")}  # not the statement edits


def check(eng, st: dict, change: dict, fs_result) -> dict:
    """One change checked and described: {type, target, value, label, from, to, lines?, reason}. Raises ValueError."""
    kind, target, value = change.get("type"), str(change.get("target") or "").strip()[:200], str(change.get("value") or "").strip()[:4000]
    reason = " ".join(str(change.get("reason") or "").split())[:500] or "As the client asked."
    out = {"type": kind, "target": target, "value": value, "reason": reason, "status": "proposed"}
    if kind == "field":
        if target not in FIELDS:
            raise ValueError(f"“{target}” isn't client information the assistant can change.")
        try:
            V.update(field_payload(target, value))
        except V.Invalid as exc:
            raise ValueError("; ".join(str(v) for v in exc.errors.values())) from None
        return {**out, "label": FIELDS[target][0], "from": current_field(eng, target), "to": value}
    if kind == "journal":
        lines = journal_lines(value, balances(fs_result))
        return {**out, "label": target or "Journal for the client's request", "lines": lines, "from": "", "to": ""}
    if kind == "tax_adjustment":
        lever = next((lv for lv in st.get("levers") or [] if lv["key"] == target), None)
        if lever is None:
            raise ValueError(f"The computation has no line “{target}”.")
        if lever.get("scope") != "tax":
            raise ValueError(f"{lever['label']} is an accounting figure: it is changed with a journal.")
        try:
            to = _amount(value)
        except (InvalidOperation, ValueError):
            raise ValueError(f"No new amount was given for {lever['label']}.") from None
        return {**out, "label": lever["label"], "from": str(lever.get("amount") or ""), "to": str(to)}
    if kind == "note":
        if target not in NOTES:
            raise ValueError(f"“{target}” isn't a note the accountant writes.")
        return {**out, "label": f"Note: {NOTES[target]}", "from": notes_editable(eng)[target], "to": value}
    if kind == "policy":
        keys = policy_keys()
        if target not in keys:
            raise ValueError(f"“{target}” isn't one of the accounting policies.")
        current = ((eng.data or {}).get("policy_text") or {}).get(target) or _standard_policy(target)
        return {**out, "label": f"Policy: {keys[target]}", "from": current, "to": value}
    if kind == "heading":
        line = eng.tb_lines.filter(code=target).first()
        if line is None:
            raise ValueError(f"Account {target} isn't in the trial balance.")
        if value not in FS.HEADINGS:
            raise ValueError(f"“{value}” isn't a statement heading.")
        return {**out, "label": f"Heading of {line.code} {line.name}", "from": FS.HEADINGS.get(line.heading, ("", line.heading or "Not mapped"))[1],
                "to": FS.HEADINGS[value][1], "heading": value}
    raise ValueError("TASKO can't make that kind of change.")


def propose(eng, st: dict, raw: list, fs_result) -> tuple[list[dict], list[str]]:
    """The agent's changes checked: (the changes to show, why any were left out)."""
    out, dropped = [], []
    for change in (raw or [])[:MAX_CHANGES]:
        if not isinstance(change, dict) or change.get("type") not in TYPES:
            continue
        try:
            out.append(check(eng, st, change, fs_result))
        except ValueError as exc:
            dropped.append(str(exc)[:300])
    for n, c in enumerate(out):
        c["n"] = n
    return out, dropped
