"""Figures edited on the statements themselves (AFIT, 26 Nov 2026).

The accountant may overwrite a line of the statements - revenue, administrative expenses, trade receivables... - but
never a total (gross profit, profit for the year, total assets: those always follow from the lines). An edit is kept
by heading as the change it makes in trial balance signs (debit +), shown on the statements at once as an extra line
under that heading ("EDIT:<heading>"), and flagged:

- while the edits do not net to nil, the statements are out of balance: a blocking alert, and the Financial
  Statements stage can't be marked ready or approved, until the other side is edited too;
- once they balance, Local_Tax_AI chooses which trial balance account under each heading takes each change (code
  falls back to the heading's largest account), and the edits are posted to the trial balance as one journal
  ("auto:fs_edits"), proposed and approved like any other. On approval the edits are cleared: the trial balance now
  carries them. Editing again while that journal waits replaces it.

An income-statement-only engagement has no financial position to balance against: its edits are posted with the
difference to retained earnings, said so on the journal.
"""
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from .engine import fs as FS

ZERO = Decimal("0")
PREFIX = "EDIT:"
AUTO = "auto:fs_edits"
EDITABLE = {k for k, v in FS.HEADINGS.items() if k not in ("oci",)}


def sign(heading: str) -> int:
    """+1 where the statements show a debit balance as positive (assets, expenses), -1 for credits."""
    return 1 if FS.HEADINGS[heading][2] in ("asset", "expense") else -1


def stored(eng) -> dict:
    return dict((eng.data or {}).get("fs_edits") or {})


def edit_lines(eng) -> list[dict]:
    """The edits as extra trial balance lines, one per heading."""
    out = []
    for h, e in (stored(eng).get("items") or {}).items():
        if h in FS.HEADINGS:
            out.append({"code": f"{PREFIX}{h}", "name": f"Edited on the statements: {FS.HEADINGS[h][1]}", "amount": Decimal(e["delta"]),
                         "original": ZERO, "comparative": None, "heading": h, "adjusted": True, "edit": True})
    return out


def heading_balance(lines: list[dict], heading: str) -> Decimal:
    return sum((Decimal(str(ln.get("amount") or 0)) for ln in lines if ln.get("heading") == heading and not ln.get("edit")), ZERO)


def set_edit(eng, user, heading: str, value, base_lines: list[dict]) -> dict:
    """The line under `heading` shown at `value` (as the statements show it). Returns the edit (None when it's undone)."""
    if heading not in EDITABLE:
        raise ValueError("That line can't be edited: totals follow from the lines.")
    try:
        target = Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        raise ValueError("Give the amount as a number.") from None
    base = heading_balance(base_lines, heading)
    delta = sign(heading) * target - base
    data = dict(eng.data or {})
    edits = stored(eng)
    items = dict(edits.get("items") or {})
    if delta == 0:
        items.pop(heading, None)
        item = None
    else:
        item = {"delta": str(delta), "from": str(sign(heading) * base), "to": str(target), "by": user.display_name, "at": timezone.now().isoformat()}
        items[heading] = item
    edits["items"] = items
    replaced = _withdraw_pending(eng, edits)
    data["fs_edits"] = edits
    eng.data = data
    return {"item": item, "replaced": replaced}


def _withdraw_pending(eng, edits: dict):
    """An edit made while the edits' journal waits for approval: that journal no longer matches, so it is withdrawn."""
    from .models import Adjustment

    jid = edits.get("journal")
    if not jid:
        return None
    adj = eng.adjustments.filter(pk=jid, status=Adjustment.Status.PROPOSED).first()
    edits["journal"] = None
    if adj:
        adj.status, adj.decided_at, adj.decision_note = Adjustment.Status.REJECTED, timezone.now(), "Withdrawn: the statements were edited again."
        adj.save()
        return adj.ref
    return None


def clear(eng, heading: str | None = None) -> None:
    data = dict(eng.data or {})
    edits = stored(eng)
    items = dict(edits.get("items") or {})
    if heading:
        items.pop(heading, None)
    else:
        items = {}
    edits["items"] = items
    _withdraw_pending(eng, edits)
    data["fs_edits"] = edits
    eng.data = data


def summary(eng, full: bool) -> dict | None:
    """What the screen shows: each edit, the difference, and whether the edits can go to the trial balance."""
    from .models import Adjustment

    edits = stored(eng)
    items = edits.get("items") or {}
    journal = None
    if edits.get("journal"):
        adj = eng.adjustments.filter(pk=edits["journal"]).first()
        if adj:
            journal = {"id": adj.id, "ref": adj.ref, "status": adj.status}
    if not items and not journal:
        return None
    difference = sum((Decimal(e["delta"]) for e in items.values()), ZERO)
    balanced = difference == 0 or not full
    pending = bool(journal and journal["status"] == Adjustment.Status.PROPOSED)
    return {"items": [{"heading": h, "label": FS.HEADINGS[h][1], **e} for h, e in items.items() if h in FS.HEADINGS],
            "difference": str(difference), "balanced": balanced, "needs_balance": full, "journal": journal,
            "can_post": bool(items) and balanced and not pending}


def alerts(s: dict | None) -> list[dict]:
    if not s or not s["items"]:
        return []
    if not s["balanced"]:
        return [{"stage": "fs", "severity": "blocking",
                 "text": f"Statement figures were edited and are out of balance by {Decimal(s['difference']):,.2f}: edit the other side before you "
                         "continue."}]
    if s["journal"] and s["journal"]["status"] == "proposed":
        return [{"stage": "fs", "severity": "review", "text": f"The statement edits are in {s['journal']['ref']}, waiting for approval to update the trial balance."}]
    return [{"stage": "fs", "severity": "review",
             "text": f"{len(s['items'])} statement edit(s) balance but are not in the trial balance yet: use Update the TB."}]


def default_account(lines: list[dict], heading: str) -> dict | None:
    """The heading's largest account (by size) - where an edit goes when no better account is chosen."""
    under = [ln for ln in lines if ln.get("heading") == heading and not ln.get("edit")]
    return max(under, key=lambda ln: abs(Decimal(str(ln.get("amount") or 0))), default=None)


def journal_lines(eng, base_lines: list[dict], picks: dict[str, str], full: bool) -> tuple[list[dict], list[str]]:
    """The journal posting the edits: each heading's change to the chosen account (a new account when the heading has
    none). Returns (lines, notes)."""
    notes = []
    by_code = {str(ln["code"]): ln for ln in base_lines if not ln.get("edit")}
    lines = []
    for h, e in (stored(eng).get("items") or {}).items():
        code = picks.get(h)
        acct = by_code.get(code) if code else None
        if acct is None or acct.get("heading") != h:
            acct = default_account(base_lines, h)
        if acct is None:
            lines.append({"code": f"FS-{h}"[:40], "name": f"{FS.HEADINGS[h][1]} (edited on the statements)", "heading": h, "amount": e["delta"]})
            notes.append(f"{FS.HEADINGS[h][1]} had no account in the trial balance: a new one is opened.")
        else:
            lines.append({"code": str(acct["code"]), "name": acct.get("name") or "", "heading": h, "amount": e["delta"]})
    difference = sum((Decimal(ln["amount"]) for ln in lines), ZERO)
    if difference and not full:
        re_acct = default_account(base_lines, "retained_earnings")
        lines.append({"code": str(re_acct["code"]) if re_acct else "FS-retained_earnings", "name": (re_acct or {}).get("name") or "Retained earnings",
                      "heading": "retained_earnings", "amount": str(-difference)})
        notes.append("Income statement only: the net change is taken to retained earnings.")
    return lines, notes
