"""What the wages and imputation agents share: their job settings, the myIR "Transaction Summary"
layout (the payroll EMP account and the income tax account export the same way), IRD transaction
categories, matching IRD payments to the ledger, exceptions and the result envelope."""
import base64
import hashlib
import re
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..budget import cost_usd, empty_usage
from ..config import get_settings
from ..gst import ai as A
from ..gst import readers as R
from ..gst.money import ZERO, amount, day, month_first, q
from ..gst.run import GstStop, jsonable
from ..gst.sources import Source, table_rows
from ..llm import model_id
from ..skills_loader import all_skills

BANK = re.compile(r"\bbank\b|cheque|savings|current\s*account|credit\s*card|\bcash\b", re.I)

# myIR's transaction summary: Period ending | Account type | Date | Transaction | Amount (charges +, payments -).
R.FIELDS["myir_transactions"] = {
    "period": ["period ending", "period end", "period", "return period", "tax year", "year ending"],
    "account_type": ["account type", "tax type"],
    "date": ["date", "transaction date", "processed"],
    "effective": ["effective date", "effective"],
    "type": ["transaction", "transaction type", "type", "description", "details"],
    "amount": ["amount", "net amount"],
    "debit": ["debit", "dr"],
    "credit": ["credit", "cr"],
}
R.REQUIRED["myir_transactions"] = ["date", "type"]
A.SCHEMAS["myir_transactions"] = A._obj({"lines": A._list({
    "period_end": A._STR, "account_type": A._STR, "date": A._STR, "effective_date": A._STR, "transaction": A._STR, "amount": A._STR, "source": A._STR})})
A.ASK["myir_transactions"] = ("List every line of the IRD (myIR) transaction summary in order: its period ending, account type, date, transaction and "
                              "amount (charges positive, payments and credits negative, as the statement shows them in brackets). Columns may continue on "
                              "a later page in the same row order: join them row by row. Dates as YYYY-MM-DD; myIR writes them month first (3/31/2026).")


class WpStop(GstStop):
    """A problem the accountant must fix before the run can go on (shown as it is)."""


def _id(prefix: str, *parts) -> str:
    return f"{prefix}-" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8]


@dataclass
class WpSetup:
    entity: str
    balance_date: date
    fy_start: date
    ird_number: str = ""
    software: str = "Xero"
    currency: str = "NZD"
    gl_version: str = ""
    first_year: bool = False
    tolerance: Decimal = ZERO
    prep_date: date | None = None
    firm: str = "BDS Chartered Accountants Ltd"
    prepared_by: str = ""
    extra: dict = field(default_factory=dict)
    basis: str = ""  # for the shared workpaper header
    frequency: str = ""

    def accounts(self, key: str) -> list[str]:
        """An accountant's account list ("200, 477 Wages; PAYE payable"), lower case."""
        raw = self.extra.get(key) or ""
        return [a.strip().lower() for a in re.split(r"[,;\n]+", str(raw)) if a.strip()]

    def money(self, key: str) -> Decimal | None:
        return amount(self.extra.get(key))


def setup_from(options: dict, job: dict, extra_keys: tuple[str, ...]) -> WpSetup:
    raw = options.get("setup") or {}
    bd = day(raw.get("balance_date"))
    if bd is None:
        raise WpStop("Give the balance date (the financial year end) in the job settings.")
    start = day(raw.get("fy_start"))
    if start is None:
        try:
            start = date(bd.year - 1, bd.month, bd.day) + timedelta(days=1)
        except ValueError:
            start = date(bd.year - 1, bd.month, 28) + timedelta(days=1)
    if start >= bd:
        raise WpStop("The financial year start must be before the balance date.")
    return WpSetup(entity=raw.get("entity") or job.get("client_name") or "", balance_date=bd, fy_start=start, ird_number=str(raw.get("ird_number") or ""),
                   software=str(raw.get("software") or "Xero"), currency=str(raw.get("currency") or "NZD"), gl_version=str(raw.get("gl_version") or ""),
                   first_year=bool(raw.get("first_year")), tolerance=abs(amount(raw.get("tolerance")) or ZERO), prep_date=date.today(),
                   firm=str(options.get("firm") or "BDS Chartered Accountants Ltd"), prepared_by=str(options.get("prepared_by") or ""),
                   extra={k: raw.get(k) for k in extra_keys if raw.get(k) not in (None, "")})


class Flags:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, code: str, severity: str, text: str, evidence: str = "", refs: list | None = None, amount_=None, side: str = ""):
        self.items.append({"id": _id("X", code, text), "code": code, "severity": severity, "text": text, "next_evidence": evidence,
                           "refs": [r for r in (refs or []) if r], "amount": amount_, "side": side})

    def blocking(self, side: str = "") -> list[dict]:
        return [x for x in self.items if x["severity"] == "blocking" and (not side or x["side"] in (side, ""))]


def uses_month_first(src: Source) -> bool:
    return month_first([v for _, _, values in table_rows(src) for v in values if isinstance(v, str)] + [t["text"] for t in src.text])


def category(text: str) -> str:
    """What an IRD transaction does to the account."""
    t = (text or "").lower()
    if re.search(r"use.of.money|\buomi\b|\binterest\b", t):
        return "interest"
    if re.search(r"penalt", t):
        return "penalty"
    if re.search(r"refund", t):
        return "refund"
    if re.search(r"reversal|reversed", t):
        return "reversal"
    if re.search(r"transfer", t):
        return "transfer"
    if re.search(r"payment|paid|receipt", t):
        return "payment"
    return "charge"


def read_myir(src: Source, ai=None) -> dict:
    """myIR's transaction summary (any tax account): every line, signed + owed / - paid."""
    us = uses_month_first(src)
    out = []
    t = R.find_table(src, "myir_transactions", ai) if src.sheets else None
    if t is not None:
        for row_no, values in t.rows:
            when = day(t.get(values, "date"), us=us)
            if when is None or R._is_total(values):
                continue
            if "amount" in t.cols:
                a = amount(t.get(values, "amount")) or ZERO
            else:
                a = abs(amount(t.get(values, "debit")) or ZERO) - abs(amount(t.get(values, "credit")) or ZERO)
            kind = t.text(values, "type")
            out.append({"id": f"{src.sid}:{row_no}", "date": when, "effective": day(t.get(values, "effective"), us=us) or when,
                        "period_end": day(t.get(values, "period"), us=us), "type": kind, "category": category(kind), "amount": a,
                        "account_type": t.text(values, "account_type"), "source": t.ref(row_no), "how": "code"})
        return {"lines": out, "problem": "" if out else "No transaction lines were found."}
    if ai is None:
        return {"lines": [], "problem": "The transaction summary could not be read."}
    got = ai.extract("myir_transactions", src)
    for n, r in enumerate(got.get("lines", []), start=1):
        when = day(r.get("date"))
        if when is None:
            continue
        a = amount(r.get("amount"))
        if a is None:
            continue
        out.append({"id": f"{src.sid}:ai:{n}", "date": when, "effective": day(r.get("effective_date")) or when, "period_end": day(r.get("period_end")),
                    "type": r.get("transaction", ""), "category": category(r.get("transaction", "")), "amount": a, "account_type": r.get("account_type", ""),
                    "source": f"{src.sid} {src.name}, {r.get('source', '')}", "how": "ai"})
    return {"lines": out, "problem": "" if out else "No transaction lines could be read from this document."}


def match_payment(payment: dict, gl: list[dict], used: set, prefer: set[str]) -> dict | None:
    """The ledger line for an IRD payment or refund: the same amount within 14 days, in an account other
    than the bank, preferring the expected accounts; never the same line twice."""
    amt = abs(payment["amount"])
    near = [ln for ln in gl if ln["id"] not in used and not BANK.search(ln["account"]) and abs(abs(ln["debit"] - ln["credit"]) - amt) < Decimal("0.01")
            and abs((ln["date"] - payment["date"]).days) <= 14]
    near.sort(key=lambda ln: (0 if ln["account"].lower() in prefer else 1, abs((ln["date"] - payment["date"]).days), ln["id"]))
    if not near:
        return None
    used.add(near[0]["id"])
    return near[0]


def tb_matching(tb: list[dict], wanted: list[str], pattern: re.Pattern | None, exclude: re.Pattern | None = None) -> list[dict]:
    """Trial balance rows chosen by the accountant (names or codes) or, without a choice, by their names."""
    if wanted:
        return [r for r in tb if r["account"].lower() in wanted or (r.get("code") or "").lower() in wanted]
    return [r for r in tb if pattern and pattern.search(r["account"]) and not (exclude and exclude.search(r["account"]))]


def opening_of(gl_opening: dict, accounts: list[dict]) -> Decimal | None:
    names = {r["account"] for r in accounts}
    found = [v for k, v in gl_opening.items() if k in names]
    return sum(found, ZERO) if found else None


def envelope(run_id: str, job_id: str, mode: str, result: dict, workbook: bytes, reader, started: float, sources: list,
             counts: dict, summary: str, status: str, rules_version: str) -> dict:
    s = get_settings()
    calls = reader.usage
    totals = empty_usage()
    cost = 0.0
    for u in calls:
        for k in totals:
            totals[k] += u[k]
        cost += cost_usd(u["model"], u, s) if not u["model"].startswith("fake-") else 0.0
    all_input = totals["input"] + totals["cache_read"] + totals["cache_write"]
    verdict = {"Reconciled": "ready", "Reconciled subject to corrections": "ready_with_exceptions"}.get(status, "not_ready")
    trail = {
        "read": {"label": f"{len(sources)} documents read from Drive", "documents": len(sources), "changed": 0, "removed": [], "images_read": 0, "detail": []},
        "checked": {"label": "Documents read into records", "detail": []},
        "compared": {"label": status, "detail": []},
        "judged": {"label": status, "how": "code", "detail": []},
        "verified": {"label": f"{counts.get('blocking', 0)} blocking and {counts.get('review', 0)} review exceptions", "evidence": 0, "detail": []},
    }
    return {
        "run_id": run_id, "job_id": job_id, "mode": mode, "status": "complete", "verdict": verdict, "readiness": status[:40], "summary": summary[:400],
        "coverage": {"addressed": 0, "total": counts.get("review", 0)},
        "counts": {"high": counts.get("blocking", 0), "medium": counts.get("review", 0), "low": counts.get("info", 0)},
        "direction_items": [], "findings": [], "evidence": [], "precheck_type": mode, "trail": trail, "skipped": [],
        "usage": {"calls": calls, "totals": totals, "model_calls": len(calls), "reader_calls": 0, "cost_usd": round(cost, 6),
                  "cache_share": round(totals["cache_read"] / all_input, 3) if all_input else 0.0, "reused_answers": 0,
                  "budget": {"reading_calls": s.gst_max_reading_calls}},
        "models": {"gst": model_id("gst", s)},
        "versions": {"prompt": rules_version[:40], "parser": s.parser_version, "skills": {n: sk.version for n, sk in all_skills().items()}},
        "knowledge_ids": [], "demo": s.llm_mode == "fake", "duration_s": round(time.time() - started, 1),
        # The WP Agent's result: kept by the PM application with the run (its "gst" field holds any WP Agent's).
        "gst": jsonable(result), "workbook_b64": base64.b64encode(workbook).decode(),
    }


def worst(*statuses: str) -> str:
    order = ["Incomplete evidence", "Unreconciled", "Reconciled subject to corrections", "Reconciled"]
    return min(statuses, key=order.index)


def conclude(blocking: bool, residual: Decimal | None, tolerance: Decimal, corrections: Decimal) -> str:
    if blocking or residual is None:
        return "Incomplete evidence"
    if abs(residual) > tolerance:
        return "Unreconciled"
    return "Reconciled subject to corrections" if corrections else "Reconciled"


__all__ = ["WpSetup", "WpStop", "Flags", "setup_from", "read_myir", "match_payment", "tb_matching", "opening_of", "envelope", "worst", "conclude",
           "category", "uses_month_first", "q", "_id", "BANK"]
