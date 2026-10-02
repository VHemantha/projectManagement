"""Deterministic checks (graph node 4). No model, no tokens.

A rule that passes needs nothing further. A rule that fails becomes a finding with
source = "rule", quoting the rows it looked at. A few failures need judgment (is this
movement explained?), and those also become a reader task.

Each check returns a result dict:
    rule_id, label, passed (True | False), area, title, why, status, severity,
    needs_judgment, question, evidence: [(file_row, block), ...]
Checks that do not apply to a document return nothing and are not counted as run.
"""
import re

from .config import Settings
from .textutil import to_number

_STOP = {"schedule", "lead", "sheet", "workpaper", "working", "fy", "ye", "year", "final", "draft", "v1", "v2", "copy", "xlsx", "csv"}


def _fmt(n: float) -> str:
    return f"{n:,.2f}".rstrip("0").rstrip(".") if n != int(n) else f"{int(n):,}"


def _block_for(parsed: dict, table_name: str, row_no: int) -> dict | None:
    for b in parsed["blocks"]:
        if b.get("row") == row_no and (b.get("sheet") == table_name or b["section"].endswith(table_name) or table_name in b["loc"]):
            return b
    return None


def _header(table: dict) -> tuple[int, list[str]] | None:
    """(index in rows, lower-cased header cells) of the first row that looks like a header."""
    for i, (_, cells) in enumerate(table["rows"][:15]):
        texts = [str(c).strip().lower() for c in cells]
        if sum(1 for t in texts if t and to_number(t) is None) >= 2:
            return i, texts
    return None


def _col(header: list[str], *patterns: str) -> int | None:
    for idx, cell in enumerate(header):
        if any(re.search(p, cell) for p in patterns):
            return idx
    return None


def _name_of(cells: list, skip: set[int]) -> str:
    parts = [str(c).strip() for i, c in enumerate(cells) if i not in skip and c not in (None, "") and to_number(c) is None]
    return " ".join(parts)


def _is_total(name: str) -> bool:
    return bool(re.search(r"\btotals?\b|\bsum\b", name.lower()))


def _tb_rows(table: dict):
    """Yield (row_no, account name, debit, credit, prior) for the data rows of a trial balance
    table, or nothing when it has no debit/credit (or balance) columns."""
    found = _header(table)
    if not found:
        return None
    h_index, header = found
    dr = _col(header, r"^debit", r"^dr\b")
    cr = _col(header, r"^credit", r"^cr\b")
    bal = _col(header, r"balance|amount|current year|^cy\b|this year") if dr is None or cr is None else None
    prior = _col(header, r"prior|previous|last year|^py\b|comparative")
    if (dr is None or cr is None) and bal is None:
        return None
    rows = []
    numeric = {i for i in (dr, cr, bal, prior) if i is not None}
    for row_no, cells in table["rows"][h_index + 1 :]:
        get = lambda i: to_number(cells[i]) if i is not None and i < len(cells) else None  # noqa: E731
        name = _name_of(cells, numeric)
        if dr is not None and cr is not None:
            d, c = get(dr) or 0.0, get(cr) or 0.0
        else:
            value = get(bal) or 0.0
            d, c = (value, 0.0) if value >= 0 else (0.0, -value)
        if not name and not d and not c:
            continue
        rows.append((row_no, name, d, c, get(prior)))
    return rows


def _result(rule_id, label, passed, **kw) -> dict:
    base = dict(rule_id=rule_id, label=label, passed=passed, area="", title="", why="", status="exception",
                severity="medium", needs_judgment=False, question="", evidence=[])
    base.update(kw)
    return base


def rule_required_documents(docs, settings: Settings):
    classes = {d["file"]["document_class"] for d in docs}
    for cls in settings.required_classes:
        nice = cls.replace("_", " ")
        if cls in classes:
            yield _result(f"required:{cls}", f"A {nice} is in the folder", True)
        else:
            yield _result(
                f"required:{cls}", f"A {nice} is in the folder", False, area=nice, status="missing", severity="high",
                title=f"No {nice} in the job folder", why=f"The pre-check looked for a {nice} in the Drive folder and found none.",
            )


def rule_unreadable(docs, settings: Settings):
    bad = [d for d in docs if d["file"].get("error")]
    if not bad:
        yield _result("readable", "Every file can be read", True)
    for d in bad:
        yield _result(
            f"readable:{d['file']['file_id']}", "Every file can be read", False, area=d["file"]["name"], status="unclear",
            severity="low", title=f"{d['file']['name']} could not be read", why=d["file"]["error"] + " A person should check it.",
        )


def rule_tb_balances(docs, settings: Settings):
    for d in docs:
        if d["file"]["document_class"] != "trial_balance":
            continue
        for table in d["parsed"]["tables"]:
            rows = _tb_rows(table)
            if not rows:
                continue
            data = [r for r in rows if not _is_total(r[1])]
            debit, credit = sum(r[2] for r in data), sum(r[3] for r in data)
            diff = round(debit - credit, 2)
            total_row = next((r for r in rows if _is_total(r[1])), None)
            ev_rows = [rows[0][0]] + ([total_row[0]] if total_row else [data[-1][0]])
            evidence = [(d["file"], b) for b in (_block_for(d["parsed"], table["name"], n) for n in ev_rows) if b]
            if abs(diff) <= settings.balance_tolerance:
                yield _result(f"tb_balances:{d['file']['file_id']}:{table['name']}", "Trial balance debits equal credits", True)
            else:
                yield _result(
                    f"tb_balances:{d['file']['file_id']}:{table['name']}", "Trial balance debits equal credits", False,
                    area="trial balance", severity="high", evidence=evidence,
                    title="Trial balance does not balance",
                    why=f"Debits total {_fmt(debit)} and credits total {_fmt(credit)}, a difference of {_fmt(abs(diff))}.",
                )


def rule_suspense(docs, settings: Settings):
    for d in docs:
        if d["file"]["document_class"] != "trial_balance":
            continue
        for table in d["parsed"]["tables"]:
            for row_no, name, debit, credit, _ in _tb_rows(table) or []:
                if re.search(r"suspense|unallocated|unknown|to be allocated", name.lower()):
                    balance = debit - credit
                    block = _block_for(d["parsed"], table["name"], row_no)
                    ok = abs(balance) <= settings.balance_tolerance
                    yield _result(
                        f"suspense:{d['file']['file_id']}:{row_no}", "Suspense accounts are cleared", ok,
                        area=name, severity="medium", evidence=[(d["file"], block)] if block else [],
                        title=f"{name} still has a balance", why=f"{name} shows {_fmt(abs(balance))} that has not been allocated.",
                    )


def rule_reconciliation_difference(docs, settings: Settings):
    for d in docs:
        if d["file"]["document_class"] != "reconciliation":
            continue
        for table in d["parsed"]["tables"]:
            for row_no, cells in table["rows"]:
                label = _name_of(cells, set()).lower()
                if re.search(r"\bdifference\b|unreconciled|out of balance", label):
                    numbers = [n for n in (to_number(c) for c in cells) if n is not None]
                    if not numbers:
                        continue
                    diff = numbers[-1]
                    block = _block_for(d["parsed"], table["name"], row_no)
                    yield _result(
                        f"rec_difference:{d['file']['file_id']}:{table['name']}:{row_no}", "Reconciliations show no difference",
                        abs(diff) <= settings.balance_tolerance, area=d["file"]["name"], severity="high",
                        evidence=[(d["file"], block)] if block else [],
                        title="Reconciliation has an unreconciled difference",
                        why=f"{d['file']['name']} shows a difference of {_fmt(abs(diff))} that is not reconciled.",
                    )


def _tb_accounts(docs):
    for d in docs:
        if d["file"]["document_class"] == "trial_balance":
            for table in d["parsed"]["tables"]:
                for row_no, name, debit, credit, _ in _tb_rows(table) or []:
                    if name and not _is_total(name):
                        yield d, table, row_no, name, debit - credit


def _words(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z]{3,}", text.lower())} - _STOP


def rule_schedules_agree(docs, settings: Settings):
    accounts = list(_tb_accounts(docs))
    if not accounts:
        return
    for d in docs:
        if d["file"]["document_class"] != "schedule":
            continue
        name_words = _words(d["file"]["name"])
        best = max(accounts, key=lambda a: len(name_words & _words(a[3])), default=None)
        if not best or not (name_words & _words(best[3])):
            continue
        tb_doc, tb_table, tb_row, account, tb_balance = best
        total = None
        for table in d["parsed"]["tables"]:
            for row_no, cells in table["rows"]:
                if _is_total(_name_of(cells, set())):
                    numbers = [n for n in (to_number(c) for c in cells) if n is not None]
                    if numbers:
                        total = (table, row_no, numbers[-1])
        if total is None:
            continue
        table, row_no, value = total
        agrees = abs(abs(value) - abs(tb_balance)) <= settings.balance_tolerance
        blocks = [(d["file"], _block_for(d["parsed"], table["name"], row_no)), (tb_doc["file"], _block_for(tb_doc["parsed"], tb_table["name"], tb_row))]
        yield _result(
            f"schedule_agrees:{d['file']['file_id']}", "Schedules agree to the trial balance", agrees,
            area=account, severity="medium", evidence=[(f, b) for f, b in blocks if b],
            title=f"{d['file']['name']} does not agree to the trial balance",
            why=f"The schedule totals {_fmt(abs(value))} but {account} in the trial balance is {_fmt(abs(tb_balance))}.",
        )


def rule_variances(docs, settings: Settings):
    """Large year-on-year movements. Not wrong in themselves: each becomes a question for a
    reader ("is this explained?"). Capped at three so they cannot use up the run's budget."""
    movers = []
    checked = False
    for d in docs:
        if d["file"]["document_class"] != "trial_balance":
            continue
        for table in d["parsed"]["tables"]:
            for row_no, name, debit, credit, prior in _tb_rows(table) or []:
                if prior is None or _is_total(name) or not name:
                    continue
                checked = True
                current = debit - credit
                change = abs(abs(current) - abs(prior))
                pct = (change / abs(prior) * 100) if prior else 100.0
                if change >= settings.variance_min_amount and pct >= settings.variance_pct:
                    movers.append((change, d, table, row_no, name, current, prior, pct))
    if not checked:
        return
    if not movers:
        yield _result("variance:none", "Large movements against last year", True)
    for change, d, table, row_no, name, current, prior, pct in sorted(movers, key=lambda m: -m[0])[:3]:
        block = _block_for(d["parsed"], table["name"], row_no)
        yield _result(
            f"variance:{d['file']['file_id']}:{row_no}", "Large movements against last year", False,
            area=name, status="exception", severity="low", needs_judgment=True,
            evidence=[(d["file"], block)] if block else [],
            title=f"{name} moved {pct:.0f}% against last year",
            why=f"{name} is {_fmt(abs(current))} this year and was {_fmt(abs(prior))} last year.",
            question=f"{name} moved from {_fmt(abs(prior))} to {_fmt(abs(current))}. Is this movement explained anywhere in the workpapers?",
        )


ALL_RULES = [rule_required_documents, rule_unreadable, rule_tb_balances, rule_suspense, rule_reconciliation_difference, rule_schedules_agree, rule_variances]


def run_rules(docs: list[dict], settings: Settings) -> list[dict]:
    results = []
    for rule in ALL_RULES:
        results.extend(rule(docs, settings) or [])
    return results
