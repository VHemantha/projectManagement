"""The reconciliation itself: deterministic code over the records the readers produced. Decimal
arithmetic, one sign convention (GST payable positive, receivable negative), every item with an
amount, a reason, its sources and one treatment. Item ids come from their sources, so an unchanged
rerun gives the same totals and ids. Nothing here calls a model except `Reader.classify_imports`,
which only says what a ledger line is.

E = A + B - C + D (expected GST control balance); F = reported GL + correction effects;
unexplained = F - E. See WP_AGENT.md for each rule and its source in AFIT's specification.
"""
import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from .money import ZERO, add_months, gst_due_date, month_end, q

FREQ_MONTHS = {"monthly": 1, "two_monthly": 2, "six_monthly": 6}
BASES = ("payments", "invoice", "hybrid")
GST_COLUMN_MESSAGE = ("Please re-upload the ageing report with the GST column\n\n"
                      "The uploaded {report} ageing report does not include the GST attributable to outstanding balances.\n\n"
                      "In Xero, enable the GST column in the report's column settings, then export and upload the report again. "
                      "Ensure the report is prepared as at the financial year-end date.\n\n"
                      "This allows the reconciliation agent to use the reported GST amounts instead of estimating GST from the total balances.")
REPORT_NAME = {"ar": "Accounts Receivable", "ap": "Accounts Payable"}
NON_GST = re.compile(r"\b(wages?|salar(y|ies)|paye|kiwisaver|esct|income\s*tax|provisional\s*tax|inland\s*revenue|\bird\b|gst|payroll|"
                     r"student\s*loan|child\s*support|acc\s*levy)\b", re.I)
GST_ACCOUNT = re.compile(r"\bgst\b", re.I)
NOT_GST_ACCOUNT = re.compile(r"expense|imports?\s*expense|clearing\s*fee", re.I)
AR_ACCOUNT = re.compile(r"(accounts?\s*receivable|trade\s*debtors|\bdebtors\b|receivables)", re.I)
AP_ACCOUNT = re.compile(r"(accounts?\s*payable|trade\s*creditors|\bcreditors\b|payables)", re.I)
INCOME_TAX = re.compile(r"income\s*tax|provisional\s*tax|terminal\s*tax|tax\s*payable|tax\s*paid|\brwt\b|taxation", re.I)
BANK = re.compile(r"\bbank\b|cheque|savings|current\s*account|credit\s*card|cash", re.I)
PENALTY = re.compile(r"penalt|interest|uomi|use\s*of\s*money|late\s*(payment|filing)", re.I)
IMPORT_HINT = re.compile(r"import\s*gst|gst\s*on\s*imports?|customs|\bnzcs\b|import\s*entry|\bduty\b|clearance|broker", re.I)
STANDARD_CODE = re.compile(r"15\s*%|gst\s*on\s*(income|expenses|sales|purchases)|standard", re.I)
ZERO_CODE = re.compile(r"zero|exempt|no\s*gst|not\s*reportable|bas\s*excluded|0\s*%|gst\s*free", re.I)


def _id(prefix: str, *parts) -> str:
    return f"{prefix}-" + hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:8]


def _norm_ref(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{3,}", (text or "").lower()) if not t.isdigit() or len(t) >= 4}


@dataclass
class Setup:
    entity: str
    balance_date: date
    fy_start: date
    basis: str = "payments"
    frequency: str = "two_monthly"
    ird_number: str = ""
    software: str = "Xero"
    currency: str = "NZD"
    gl_version: str = ""
    gst_accounts: list[str] = field(default_factory=list)
    first_year: bool = False
    tolerance: Decimal = ZERO
    ar_gl_fallback: bool = False
    ap_gl_fallback: bool = False
    prep_date: date | None = None
    firm: str = "BDS Chartered Accountants Ltd"
    prepared_by: str = ""


@dataclass
class Data:
    returns: list[dict] = field(default_factory=list)
    ird: list[dict] = field(default_factory=list)
    gl: list[dict] = field(default_factory=list)
    gl_opening: dict = field(default_factory=dict)
    tb: list[dict] = field(default_factory=list)
    journals: list[dict] = field(default_factory=list)
    ar: dict | None = None
    ap: dict | None = None
    late_claims: list[dict] = field(default_factory=list)
    has_return_detail: bool = False
    prior_year: dict | None = None
    customs_sources: list[str] = field(default_factory=list)
    present: set = field(default_factory=set)  # the kinds of document found
    reading_problems: list[dict] = field(default_factory=list)


class Recon:
    def __init__(self, setup: Setup, data: Data, reader=None):
        self.su, self.d, self.reader = setup, data, reader
        self.bd = setup.balance_date
        self.exceptions: list[dict] = []
        self.corrections: list[dict] = []

    # --- helpers ------------------------------------------------------------------------------------
    def flag(self, code: str, severity: str, text: str, evidence: str = "", refs: list | None = None, amount_=None):
        self.exceptions.append({"id": _id("X", code, text), "code": code, "severity": severity, "text": text, "next_evidence": evidence,
                                "refs": refs or [], "amount": amount_})

    def _gst_accounts(self) -> set[str]:
        wanted = [w.strip().lower() for w in self.su.gst_accounts if w.strip()]
        names = {r["account"] for r in self.d.tb} | {ln["account"] for ln in self.d.gl}
        codes = {(r.get("code") or ""): r["account"] for r in self.d.tb} | {(ln.get("code") or ""): ln["account"] for ln in self.d.gl}
        if wanted:
            found = {n for n in names if n.lower() in wanted} | {codes[c] for c in codes if c and c.lower() in wanted}
            return found
        return {n for n in names if GST_ACCOUNT.search(n) and not NOT_GST_ACCOUNT.search(n)}

    # --- 1. uploads -------------------------------------------------------------------------------------
    def expected_periods(self) -> list[date]:
        step = FREQ_MONTHS.get(self.su.frequency, 2)
        ends, end = [], self.bd
        while end >= self.su.fy_start:
            ends.append(end)
            end = month_end(add_months(date(end.year, end.month, 1), -step))
        return sorted(ends)

    def check_uploads(self):
        p = self.d.present
        if "gst_returns" not in p:
            self.flag("no_returns", "blocking", "No GST return summary was found.", "Upload the IRD GST return summary for the year and any older unpaid periods.")
        if "ird_statement" not in p:
            self.flag("no_ird", "blocking", "No IRD GST account statement was found, so settlements can't be evidenced.",
                      "Upload the IRD GST transaction statements for the current and prior year, through the preparation date.")
        if not ({"trial_balance", "general_ledger"} & p):
            self.flag("no_gl", "blocking", "Neither a trial balance nor a general ledger was found.", "Upload the year-end trial balance and the full general ledger.")
        if "prior_year_recon" not in p and not self.su.first_year:
            self.flag("no_prior_year", "blocking", "No prior-year GST reconciliation was found (the entity isn't set as a first-year entity).",
                      "Upload last year's GST reconciliation, or tick First-year entity if it truly is one.")
        if "journal_report" not in p:
            self.flag("no_journals", "review", "No journal report with audit history: journals entered after a return was finalised can't be dated.",
                      "Upload the journal report showing created/modified dates.")
        if not self.d.has_return_detail:
            self.flag("no_return_detail", "review", "No transaction detail of later GST returns: late claims after year-end can't be checked.",
                      "Upload the GST return transaction detail (or late claims) from year-end through the latest return.")
        for problem in self.d.reading_problems:
            self.flag("reading", "review" if problem.get("minor") else "blocking", problem["text"], problem.get("evidence", ""), [problem.get("source", "")])

    # --- 2. returns and settlements (A) --------------------------------------------------------------------
    def returns_schedule(self) -> list[dict]:
        by_period: dict[date, list[dict]] = {}
        for r in self.d.returns:
            by_period.setdefault(r["period_end"], []).append(r)
        periods = {}
        for end, versions in by_period.items():
            versions.sort(key=lambda r: (1 if "amend" in str(r.get("version", "")).lower() else 0, r.get("filed") or date.min))
            r = versions[-1]
            totals_only = r.get("box8") is None and r.get("box10") is not None
            output = (r.get("box10") if totals_only else r.get("box8")) or ZERO
            box9 = ZERO if totals_only else (r.get("box9") or ZERO)
            inp = (r.get("box14") if (r.get("box12") is None and r.get("box14") is not None) else r.get("box12")) or ZERO
            box13 = ZERO if (r.get("box12") is None and r.get("box14") is not None) else (r.get("box13") or ZERO)
            calc = output + box9 - inp - box13
            given = r.get("box15")
            if given is not None and abs(given - calc) > Decimal("0.01"):
                self.flag("net_mismatch", "review", f"Return {end:%d/%m/%Y}: Box 15 shows {q(given)} but output + Box 9 - input - Box 13 is {q(calc)}.",
                          "Check the return's boxes against IRD's copy.", [r["source"]])
            if totals_only:
                self.flag("totals_only", "info", f"Return {end:%d/%m/%Y} gives only Box 10 and Box 14 (adjustments already included; not added again).",
                          refs=[r["source"]])
            net = given if given is not None else calc
            periods[end] = {"id": _id("R", end), "period_end": end, "period_start": r.get("period_start"), "version": r.get("version") or "original",
                            "versions": [{"version": v.get("version"), "filed": v.get("filed"), "net": v.get("box15"), "source": v["source"]} for v in versions],
                            "filed": r.get("filed"), "total_sales": r.get("box5"), "output": output, "box9": box9, "total_purchases": r.get("box11"),
                            "input": inp, "box13": box13, "net": net, "source": r["source"], "origin": "return",
                            "prior_year": end < self.su.fy_start, "settled_to_bd": ZERO, "settled_after": ZERO, "allocations": []}
        # Older unpaid periods known only from last year's reconciliation.
        for u in (self.d.prior_year or {}).get("unpaid_returns", []):
            end = u.get("period_end")
            if end and end not in periods:
                periods[end] = {"id": _id("R", end), "period_end": end, "period_start": None, "version": "per prior-year reconciliation", "versions": [],
                                "filed": None, "total_sales": None, "output": None, "box9": None, "total_purchases": None, "input": None, "box13": None,
                                "net": u["amount"], "source": u["source"], "origin": "prior_year", "prior_year": True,
                                "settled_to_bd": ZERO, "settled_after": ZERO, "allocations": []}
        for end in self.expected_periods():
            if end not in periods:
                self.flag("missing_return", "blocking", f"No return was found for the period ending {end:%d/%m/%Y} (a nil return is still a return).",
                          f"Upload the GST return for the period ending {end:%d/%m/%Y}.")
        for end, row in periods.items():
            if end > self.bd and (row["period_start"] or date.max) <= self.bd:
                self.flag("straddle", "review", f"The balance date falls inside the period ending {end:%d/%m/%Y}: its pre-year-end part must be worked out from "
                          "transactions (never by dividing the return by days). It isn't included in A.", "Transaction detail of that period.")
        return sorted(periods.values(), key=lambda r: r["period_end"])

    @staticmethod
    def ird_category(text: str) -> str:
        t = (text or "").lower()
        if PENALTY.search(t):
            return "interest" if re.search(r"interest|uomi|use\s*of\s*money", t) else "penalty"
        if re.search(r"refund", t):
            return "refund"
        if re.search(r"reversal|reversed|cancel", t):
            return "reversal"
        if re.search(r"transfer|offset|credit\s*from|credit\s*to", t):
            return "transfer"
        if re.search(r"payment|paid|receipt", t):
            return "payment"
        if re.search(r"return|assess|gst\s*(due|payable)|amend", t):
            return "assessment"
        return "other"

    def allocate(self, periods: list[dict]) -> dict:
        by_end = {p["period_end"]: p for p in periods}
        charges, unallocated, rows = [], [], []
        for line in self.d.ird:
            cat = self.ird_category(line["type"])
            movement = line["debit"] - line["credit"]  # + increases what is owed to IRD
            row = {**line, "category": cat, "movement": movement, "allocated_to": None}
            rows.append(row)
            if cat in ("penalty", "interest"):
                charges.append(row)
                continue
            if cat == "assessment":
                p = by_end.get(line.get("period_end"))
                if p and p["origin"] == "return" and abs(movement - p["net"]) > Decimal("0.01"):
                    self.flag("assessed_differs", "review", f"IRD assessed {q(movement)} for {p['period_end']:%d/%m/%Y} but the return shows {q(p['net'])}.",
                              "IRD's copy of the return or an amendment.", [line["source"], p["source"]])
                if p:
                    row["allocated_to"] = p["period_end"]
                continue
            end = line.get("period_end")
            p = by_end.get(end)
            if p is None:
                unallocated.append(row)
                continue
            row["allocated_to"] = end
            alloc = {"date": line["effective"], "amount": movement, "type": cat, "reference": line.get("reference", ""), "source": line["source"],
                     "after_bd": line["effective"] > self.bd}
            if line["effective"] <= self.bd < line["date"]:
                self.flag("backdated", "review", f"IRD line processed {line['date']:%d/%m/%Y} is effective {line['effective']:%d/%m/%Y}, before the balance date: "
                          "check its year-end effect.", "IRD's allocation history.", [line["source"]], movement)
            p["allocations"].append(alloc)
            if alloc["after_bd"]:
                p["settled_after"] += movement
            else:
                p["settled_to_bd"] += movement
        for row in unallocated:
            self.flag("unallocated", "review", f"IRD line {row['date']:%d/%m/%Y} {row['type']} {q(row['movement'])} isn't allocated to a GST period by IRD.",
                      "IRD's allocation of this amount (a statement showing the period).", [row["source"]], row["movement"])
        for p in periods:
            p["outstanding_bd"] = (p["net"] or ZERO) + p["settled_to_bd"] if p["net"] is not None else None
            p["outstanding_now"] = (p["outstanding_bd"] or ZERO) + p["settled_after"] if p["net"] is not None else None
            due = gst_due_date(p["period_end"])
            p["due"] = due
            ob = p["outstanding_bd"] or ZERO
            p["paid_at_bd"] = "Yes" if ob == 0 else "No"
            p["standing"] = "settled" if ob == 0 else ("overdue at balance date" if due <= self.bd else "not yet due at balance date")
            if p["filed"] and p["period_end"] <= self.bd < p["filed"]:
                p["note"] = "filed after balance date: included once"
        return {"lines": rows, "charges": charges, "unallocated": unallocated}

    # --- 3. the general ledger ---------------------------------------------------------------------------
    def ledger(self) -> dict:
        gst = self._gst_accounts()
        tb_gst = [r for r in self.d.tb if r["account"] in gst]
        if tb_gst:
            reported = sum((-r["balance"] for r in tb_gst), ZERO)
            how = "trial balance"
        elif self.d.gl:
            opening = sum((-v for k, v in self.d.gl_opening.items() if k in gst), ZERO)
            reported = opening + sum((ln["credit"] - ln["debit"] for ln in self.d.gl if ln["account"] in gst and ln["date"] <= self.bd), ZERO)
            how = "general ledger"
        else:
            reported, how = None, ""
        if not gst and (self.d.tb or self.d.gl):
            self.flag("no_gst_account", "blocking", "No GST control account could be identified.", "Name the GST control account(s) in the job settings.")
        if len(gst) > 1:
            self.flag("several_gst_accounts", "info", f"{len(gst)} GST accounts consolidated: {', '.join(sorted(gst))}.")
        ar = [r for r in self.d.tb if AR_ACCOUNT.search(r["account"]) and not GST_ACCOUNT.search(r["account"])]
        ap = [r for r in self.d.tb if AP_ACCOUNT.search(r["account"]) and not GST_ACCOUNT.search(r["account"])]
        return {"gst_accounts": sorted(gst), "reported": reported, "how": how, "accounts": tb_gst,
                "ar_control": sum((r["balance"] for r in ar), ZERO) if ar else None, "ap_control": sum((-r["balance"] for r in ap), ZERO) if ap else None,
                "ar_accounts": [r["account"] for r in ar], "ap_accounts": [r["account"] for r in ap]}

    def opening_check(self, ledger: dict):
        py = self.d.prior_year
        if not py or py.get("gl_gst_balance") is None:
            return None
        gst = set(ledger["gst_accounts"])
        if not self.d.gl_opening:
            return {"prior_year": py["gl_gst_balance"], "opening": None}
        opening = sum((-v for k, v in self.d.gl_opening.items() if k in gst), ZERO)
        if abs(opening - py["gl_gst_balance"]) > Decimal("0.01"):
            self.flag("opening_mismatch", "review", f"Opening GST per the GL ({q(opening)}) differs from last year's reconciled balance ({q(py['gl_gst_balance'])}).",
                      "Last year's closing journals, or a prior-period adjustment.", [py.get("source", "")], opening - py["gl_gst_balance"])
        return {"prior_year": py["gl_gst_balance"], "opening": opening}

    # --- 4. receivables and payables GST (B, C) ---------------------------------------------------------------
    def _returned_refs(self) -> dict[str, date]:
        """References of transactions shown in returns for periods ending on or before the balance date."""
        return {_norm_ref(x["ref"]): x["return_period_end"] for x in self.d.late_claims
                if x.get("ref") and x.get("return_period_end") and x["return_period_end"] <= self.bd}

    def timing_side(self, side: str, ledger: dict) -> dict:
        """B (side "ar") or C (side "ap"): the GST to adjust and every item behind it."""
        applies = self.su.basis == "payments" or (self.su.basis == "hybrid" and side == "ap")
        report = self.d.ar if side == "ar" else self.d.ap
        fallback = self.su.ar_gl_fallback if side == "ar" else self.su.ap_gl_fallback
        name = REPORT_NAME[side]
        out = {"side": side, "applies": applies, "source": "", "items": [], "total": ZERO, "paused": None, "excluded": [], "categories": {},
               "agreement": None, "basis_note": self._basis_note(side)}
        if report is None or not report.get("rows") and report.get("has_gst_column") is None:
            if fallback:
                return self._gl_fallback(side, ledger, out)
            out["paused"] = {"kind": "missing_report", "report": name,
                             "message": f"No {name} ageing report was found. Upload the year-end {name.lower()} ageing report with the GST column, "
                                        "or continue with GL analysis if it is unavailable."}
            if applies:
                self.flag(f"{side}_no_report", "blocking", f"No {name} ageing report was found; that side is paused.",
                          f"Upload the {name} ageing report with the GST column, or choose GL analysis.")
            return out
        if report.get("has_gst_column") is False:
            if fallback:
                out["fallback_reason"] = "GST-inclusive report unavailable — continue with GL analysis (preparer's choice)"
                return self._gl_fallback(side, ledger, out)
            out["paused"] = {"kind": "no_gst_column", "report": name, "message": GST_COLUMN_MESSAGE.format(report=name)}
            if applies:
                self.flag(f"{side}_no_gst_column", "blocking", f"The {name} ageing report has no GST column; that side is paused.",
                          "Re-upload the report with the GST column, or choose GL analysis.")
            return out
        out["source"] = "ageing report"
        returned = self._returned_refs()
        total_bal = ZERO
        for r in report["rows"]:
            total_bal += r["total"]
            item = {"id": _id(side.upper(), r["id"]), "contact": r["contact"], "ref": r["ref"], "date": r["date"], "balance": r["total"],
                    "gst": r["gst"] if r["gst"] is not None else ZERO, "category": "contains GST" if (r["gst"] or ZERO) != 0 else "no GST",
                    "how": "reported GST (ageing report)", "source": r["source"], "included": True, "reason": ""}
            if side == "ap" and NON_GST.search(f"{r['contact']} {r['ref']}"):
                item.update(included=False, category="non-GST liability", reason="Wages, PAYE, KiwiSaver, ESCT, income tax or GST: no GST to claim")
            elif _norm_ref(r["ref"]) in returned:
                item.update(included=False, reason=f"Already in the return for {returned[_norm_ref(r['ref'])]:%d/%m/%Y}")
            out["items"].append(item)
        self._agree(side, total_bal, report.get("report_total"), ledger, out)
        return self._finish(side, out)

    def _basis_note(self, side: str) -> str:
        b = self.su.basis
        if b == "payments":
            return "Payments basis: " + ("add GST recorded in the GL but not yet returned." if side == "ar" else "deduct GST recorded in the GL but not yet claimed.")
        if b == "invoice":
            return "Invoice basis: no automatic unpaid-balance adjustment (items shown as evidence only)."
        return "Hybrid basis: " + ("sales on invoice basis: no automatic adjustment." if side == "ar" else "purchases on payments basis: deduct GST not yet claimed.")

    def _agree(self, side, total_bal, report_total, ledger, out):
        control = ledger["ar_control"] if side == "ar" else ledger["ap_control"]
        out["agreement"] = {"ageing_total": total_bal, "report_total": report_total, "gl_control": control,
                            "difference": (total_bal - control) if control is not None else None}
        if report_total is not None and abs(report_total - total_bal) > Decimal("0.01"):
            self.flag(f"{side}_report_total", "review", f"The {REPORT_NAME[side]} ageing rows add to {q(total_bal)} but the report's total is {q(report_total)}.",
                      "Check the export is complete (all contacts, all pages).")
        if control is None:
            self.flag(f"{side}_no_control", "review", f"No {REPORT_NAME[side].lower()} control account was found in the trial balance to agree the ageing to.",
                      "The trial balance with the control account.")
        elif abs(total_bal - control) > Decimal("0.01"):
            self.flag(f"{side}_ageing_vs_gl", "review", f"The {REPORT_NAME[side]} ageing ({q(total_bal)}) doesn't agree to the GL control account ({q(control)}): "
                      f"difference {q(total_bal - control)}.", "Unmatched balances, overpayments, deposits, credit notes or a report-date difference.",
                      amount_=total_bal - control)

    def _finish(self, side, out):
        cats: dict[str, Decimal] = {}
        for it in out["items"]:
            cats[it["category"]] = cats.get(it["category"], ZERO) + (it["gst"] if it["included"] else ZERO)
        out["categories"] = cats
        included = sum((it["gst"] for it in out["items"] if it["included"] and it["category"] in ("contains GST", "estimate (15/115)")), ZERO)
        out["identified"] = included
        out["total"] = included if out["applies"] else ZERO
        for it in out["items"]:
            if it["category"] in ("mixed", "unresolved"):
                self.flag(f"{side}_{it['category']}", "review", f"{REPORT_NAME[side]} {it['ref'] or it['contact']}: balance {q(it['balance'])} is "
                          f"{it['category']} — its GST needs the accountant's analysis (not included).", "The invoice and its tax lines.", [it["source"]], it["balance"])
            if it["category"] == "estimate (15/115)":
                self.flag(f"{side}_estimate", "review", f"{REPORT_NAME[side]} {it['ref'] or it['contact']}: GST estimated at 3/23 of {q(it['balance'])} "
                          "(standard-rated, GST-inclusive, no GST amount recorded).", "The invoice's GST amount.", [it["source"]], it["gst"])
        return out

    def _gl_fallback(self, side: str, ledger: dict, out: dict) -> dict:
        """Receivables or payables traced in the full GL, invoice by invoice (the ageing report unavailable)."""
        out["source"] = "general ledger analysis (fallback)"
        accounts = set(ledger["ar_accounts"] if side == "ar" else ledger["ap_accounts"])
        if not accounts:
            pattern = AR_ACCOUNT if side == "ar" else AP_ACCOUNT
            accounts = {ln["account"] for ln in self.d.gl if pattern.search(ln["account"]) and not GST_ACCOUNT.search(ln["account"])}
        control_lines = [ln for ln in self.d.gl if ln["account"] in accounts and ln["date"] <= self.bd]
        if not control_lines:
            self.flag(f"{side}_gl_fallback_empty", "blocking", f"GL analysis chosen for {REPORT_NAME[side].lower()}, but no control account lines were found in the GL.",
                      "The full general ledger including the control account.")
            return self._finish(side, out)
        by_ref: dict[str, list[dict]] = {}
        for ln in control_lines:
            by_ref.setdefault(_norm_ref(ln["ref"]) or _norm_ref(f"{ln['contact']}{ln['date']}"), []).append(ln)
        others: dict[str, list[dict]] = {}
        for ln in self.d.gl:
            if ln["account"] not in accounts and ln.get("ref"):
                others.setdefault(_norm_ref(ln["ref"]), []).append(ln)
        returned = self._returned_refs()
        gst_accounts = set(ledger["gst_accounts"])
        for ref, lines in sorted(by_ref.items()):
            sign = 1 if side == "ar" else -1
            invoiced = sum(((ln["debit"] - ln["credit"]) * sign for ln in lines if (ln["debit"] if side == "ar" else ln["credit"])), ZERO)
            balance = sum(((ln["debit"] - ln["credit"]) * sign for ln in lines), ZERO)
            if abs(balance) < Decimal("0.01"):
                continue
            first = lines[0]
            related = [x for x in others.get(ref, []) if not BANK.search(x["account"])]
            codes = {x["tax_code"] for x in related if x.get("tax_code")}
            gst_lines = [x for x in related if x.get("gst") is not None and x["account"] not in gst_accounts]
            gst_posted = [x for x in related if x["account"] in gst_accounts]
            gst_total = (sum((abs(x["gst"]) for x in gst_lines), ZERO) if gst_lines
                         else sum((abs(x["credit"] - x["debit"]) for x in gst_posted), ZERO) if gst_posted else None)
            item = {"id": _id(side.upper(), first["id"]), "contact": first["contact"], "ref": first["ref"], "date": first["date"], "balance": balance,
                    "gst": ZERO, "category": "unresolved", "how": "", "source": first["source"], "included": True, "reason": ""}
            text = f"{first['contact']} {first['description']} {' '.join(x['account'] for x in related)}"
            standard = any(STANDARD_CODE.search(c) for c in codes)
            zero = any(ZERO_CODE.search(c) for c in codes)
            if side == "ap" and NON_GST.search(text):
                item.update(category="non-GST liability", included=False, reason="Wages, PAYE, KiwiSaver, ESCT, income tax or GST", how="excluded")
            elif standard and zero:
                item.update(category="mixed", how="tax codes differ across the invoice's lines")
            elif gst_total is not None and gst_total > 0 and invoiced:
                share = balance / invoiced if invoiced else Decimal(1)
                item.update(category="contains GST", gst=q(gst_total * min(share, Decimal(1))),
                            how=f"GST posted with the invoice ({q(gst_total)}) x unpaid share ({q(share * 100)}%)")
            elif zero or (gst_total is not None and gst_total == 0 and codes):
                item.update(category="zero-rated / exempt / no GST", how=f"tax code {', '.join(sorted(codes)) or 'no GST'}")
            elif standard and gst_total is None:
                item.update(category="estimate (15/115)", gst=q(balance * 3 / 23), how="estimate: 3/23 of a standard-rated GST-inclusive balance")
            else:
                item.update(category="unresolved", how="no GST amount or tax code found")
            if item["included"] and _norm_ref(first["ref"]) in returned:
                item.update(included=False, reason=f"Already in the return for {returned[_norm_ref(first['ref'])]:%d/%m/%Y}")
            out["items"].append(item)
        total_bal = sum((it["balance"] for it in out["items"]), ZERO)
        self._agree(side, total_bal, None, ledger, out)
        return self._finish(side, out)

    # --- 5. journals, late claims, import GST (D) -------------------------------------------------------------
    def _start(self, p: dict) -> date:
        """A period's first day: as the return gives it, else from the filing frequency."""
        if p["period_start"]:
            return p["period_start"]
        months = FREQ_MONTHS.get(self.su.frequency, 2)
        return month_end(add_months(date(p["period_end"].year, p["period_end"].month, 1), -months)) + timedelta(days=1)

    def _finalised(self, periods: list[dict], when: date) -> tuple[date | None, bool, dict | None]:
        """The finalisation date of the return covering a date: (date, is an actual date, period)."""
        for p in periods:
            start = self._start(p)
            if start <= when <= p["period_end"]:
                return (p["filed"], True, p) if p["filed"] else (gst_due_date(p["period_end"]), False, p)
        return None, False, None

    def journal_candidates(self, periods: list[dict], ledger: dict) -> list[dict]:
        gst = set(ledger["gst_accounts"])
        lines = self.d.journals or [dict(ln, journal=ln["ref"] or ln["id"], created=None, modified=None) for ln in self.d.gl
                                    if "journal" in (ln.get("source_type") or "").lower()]
        by_journal: dict[str, list[dict]] = {}
        for ln in lines:
            if ln["account"] in gst and ln.get("date") and ln["date"] <= self.bd:
                by_journal.setdefault(str(ln.get("journal") or ln["id"]), []).append(ln)
        out, undated = [], 0
        for jid, jl in sorted(by_journal.items()):
            first = jl[0]
            created = max((x.get("modified") or x.get("created") for x in jl if x.get("modified") or x.get("created")), default=None)
            if created is None:
                undated += 1
                continue
            final, actual, period = self._finalised(periods, first["date"])
            if final is None or created <= final:
                continue
            effect = sum((x["credit"] - x["debit"] for x in jl), ZERO)
            if effect == 0:
                continue
            out.append({"id": _id("J", jid, first["source"]), "kind": "journal", "journal": jid, "date": first["date"], "created": created,
                        "finalised": final, "finalised_actual": actual, "period_end": period["period_end"] if period else None,
                        "description": first.get("description", ""), "ref": first.get("ref", ""), "contact": first.get("contact", ""),
                        "effect": effect, "direction": "output" if effect > 0 else "input", "source": first["source"]})
        screened = [j for j in out if not j["finalised_actual"]]
        if screened:
            self.flag("deadline_fallback", "info", f"{len(screened)} journal(s) were screened against the returns' due dates: the returns' actual "
                      "finalisation dates aren't in the documents.", "The returns' filing/finalisation dates (IRD's return history).",
                      [j["source"] for j in screened[:10]])
        if undated:
            self.flag("journals_undated", "review", f"{undated} GST journal(s) dated at or before year-end have no created/modified date, so it can't be told "
                      "whether they were entered after the return was finalised.", "The journal report with audit history.")
        return out

    def late_claim_items(self, timing_refs: set[str]) -> tuple[list[dict], list[dict]]:
        """(late claims relevant to the year-end, evidence-only items)."""
        relevant, evidence = [], []
        for x in self.d.late_claims:
            rp, when = x.get("return_period_end"), x.get("date")
            item = {"id": _id("LC", x["id"]), "kind": "late_claim", "date": when, "ref": x.get("ref", ""), "contact": x.get("contact", ""),
                    "description": x.get("description", ""), "gst": x["gst"], "direction": x.get("side") or "", "return_period_end": rp,
                    "source": x["source"]}
            if rp is None or rp <= self.bd:
                item["reason"] = "In a return for a period ending at or before the balance date: already in A."
                evidence.append(item)
            elif when and when < self.su.fy_start:
                item["reason"] = "A prior-year transaction: evidence only (no current-year effect)."
                evidence.append(item)
            elif when and when > self.bd:
                continue  # a later year's own transaction
            elif _norm_ref(item["ref"]) and _norm_ref(item["ref"]) in timing_refs:
                item["reason"] = "Ordinary later settlement of an unpaid invoice already in G1/M1: not a correction."
                evidence.append(item)
            elif not item["direction"]:
                item["reason"] = "Not known whether it is sales or purchases: needs review."
                evidence.append(item)
                self.flag("late_claim_side", "review", f"Late claim {item['ref'] or item['description']} ({q(item['gst'])}): sales or purchases isn't shown.",
                          "The later return's detail.", [item["source"]], item["gst"])
            else:
                relevant.append(item)
        return relevant, evidence

    @staticmethod
    def _same_adjustment(j: dict, lc: dict) -> str:
        """"strong" when a journal and a late claim are the same underlying transaction, "amount" when
        only the amount and direction agree (not enough), "" otherwise."""
        if j["direction"] != lc["direction"]:
            return ""
        ref = _norm_ref(lc["ref"])
        jtext = f"{j.get('ref', '')} {j.get('description', '')} {j.get('contact', '')}"
        ref_hit = bool(ref) and (ref == _norm_ref(j.get("ref", "")) or ref in _norm_ref(jtext))
        words = _tokens(f"{lc['contact']} {lc['description']}") & _tokens(jtext)
        if ref_hit or (len(words) >= 2 and abs(abs(j["effect"]) - abs(lc["gst"])) < Decimal("0.01")):
            return "strong"
        if abs(abs(j["effect"]) - abs(lc["gst"])) < Decimal("0.01"):
            return "amount"
        return ""

    def adjustments(self, journals: list[dict], late: list[dict]) -> list[dict]:
        """The later returns' late claims for the year, set off (AFIT, 10 Nov 2026): every later return is
        gone through, each late claim taken with the sign the return shows (a credit note or reversal is
        a minus), the pluses and minuses set off, and the remainder taken to the reconciliation — one
        adjustment for sales and one for purchases. The remainder goes to the reconciliation with the
        opposite sign to the later returns' own (AFIT, 10 Nov 2026): a purchases remainder as a plus
        (Expenses not claimed; a negative remainder, Expenses claimed in error, as a minus), a sales
        remainder as a minus (Income not declared; a negative one, declared in error, as a plus).
        A journal for the same transaction is linked as evidence, never counted again; a journal no
        late claim confirms stays a candidate, out of the bridge. The order of the evidence doesn't
        change the result."""
        out, linked, maybe = [], {}, []
        for j in journals:
            for lc in late:
                how = self._same_adjustment(j, lc)
                if how == "strong":
                    linked.setdefault(j["id"], set()).add(lc["id"])
                elif how == "amount":
                    maybe.append((j, lc))
        for side in ("output", "input"):
            items = sorted((lc for lc in late if lc["direction"] == side), key=lambda x: x["id"])
            if not items:
                continue
            ids = {lc["id"] for lc in items}
            js = sorted((j for j in journals if linked.get(j["id"], set()) & ids), key=lambda j: j["id"])
            plus = sum((lc["gst"] for lc in items if lc["gst"] > 0), ZERO)
            minus = sum((lc["gst"] for lc in items if lc["gst"] < 0), ZERO)
            net = plus + minus
            # AFIT, 10 Nov 2026: a later return's remainder goes to the reconciliation with the opposite
            # sign to its own - a purchases remainder as a plus, a sales remainder as a minus.
            effect = -net if side == "output" else net
            if side == "output":
                category = "Income not declared" if net >= 0 else "Income declared in error"
            else:
                category = "Expenses not claimed" if net >= 0 else "Expenses claimed in error"
            returns = sorted({lc["return_period_end"] for lc in items if lc.get("return_period_end")})
            j_total = sum((abs(j["effect"]) for j in js), ZERO)
            unmatched = q(abs(j_total - abs(net))) if js else None
            status = (f"{len(items)} late claim(s) in {len(returns)} later return(s): {q(plus):,} plus and {q(minus):,} minus set off; "
                      f"remainder {q(net):,}" + (f"; {len(js)} journal(s) linked as evidence" if js else ""))
            if js and unmatched:
                status += f" (journals and late claims differ by {unmatched:,})"
            out.append({"id": _id("ADJ", side, *sorted(ids)), "category": category, "direction": side, "effect": q(effect), "status": status,
                        "review": bool(js and unmatched), "included": net != 0, "journals": [j["id"] for j in js],
                        "late_claims": [lc["id"] for lc in items], "evidence": js + items, "year_end_amount": q(effect),
                        "subsequent_return": returns[0] if returns else None, "returns": returns, "plus": q(plus), "minus": q(minus), "net": q(net),
                        "unmatched": unmatched,
                        "description": f"{'Sales' if side == 'output' else 'Purchases'} late claims in later returns "
                                       f"({', '.join(f'{d:%d/%m/%Y}' for d in returns)}), plus and minus set off"})
        confirmed = {j for j in linked}
        for j in journals:
            if j["id"] in confirmed:
                continue
            out.append({"id": _id("ADJ", j["id"]), "category": "Income not declared" if j["direction"] == "output" else "Expenses not claimed",
                        "direction": j["direction"], "effect": q(j["effect"]),
                        "status": "journal entered after the return was finalised: candidate, not in the bridge until confirmed",
                        "review": True, "included": False, "journals": [j["id"]], "late_claims": [], "evidence": [j], "year_end_amount": q(j["effect"]),
                        "subsequent_return": None, "returns": [], "unmatched": None, "description": j.get("description", "")})
        for j, lc in maybe:
            if j["id"] not in confirmed:
                self.flag("possible_duplicate", "review", f"Journal {j['journal']} and late claim {lc['ref'] or lc['description']} have the same amount "
                          f"({q(abs(lc['gst']))}) but nothing else ties them: the late claim is counted, the journal stays a candidate. Confirm whether "
                          "they are one adjustment.", "The underlying invoice or transaction of each.", [j["source"], lc["source"]], abs(lc["gst"]))
        return sorted(out, key=lambda a: a["id"])

    def import_gst(self, ledger: dict, timing_refs: set[str], late_refs: set[str]) -> dict:
        gst = set(ledger["gst_accounts"])
        candidates = [ln for ln in self.d.gl if ln["date"] <= self.bd and ln["date"] >= self.su.fy_start
                      and IMPORT_HINT.search(f"{ln['account']} {ln['description']} {ln['contact']} {ln.get('tax_code', '')}")]
        if not candidates:
            return {"items": [], "note": "No import GST, GST on imports or Customs GST transactions were identified: no adjustment is made."}
        lines = [{"id": ln["id"], "account": ln["account"], "date": ln["date"].isoformat(), "description": ln["description"], "ref": ln["ref"],
                  "amount": str(ln["debit"] - ln["credit"])} for ln in candidates]
        told = self.reader.classify_imports(lines) if self.reader else {}
        detail_refs = {_norm_ref(x["ref"]): x for x in self.d.late_claims if x.get("ref")}
        items = []
        for ln in candidates:
            text = f"{ln['description']} {ln['account']}".lower()
            kind = (told.get(ln["id"]) or {}).get("component") or (
                "import_gst" if re.search(r"import\s*gst|gst\s*on\s*imports?|customs\s*gst", text) else
                "customs_duty" if "duty" in text else "freight" if "freight" in text else "unclear")
            if kind not in ("import_gst", "unclear"):
                continue
            amount_ = ln["debit"] - ln["credit"]
            in_gl = ln["account"] in gst or any(x["account"] in gst and _norm_ref(x["ref"]) == _norm_ref(ln["ref"]) and ln["ref"]
                                                 for x in self.d.gl)
            in_return = detail_refs.get(_norm_ref(ln["ref"])) if ln["ref"] else None
            documented = bool(self.d.customs_sources)
            ref = _norm_ref(ln["ref"])
            counted = "M1" if ref and ref in timing_refs else ("late claims" if ref and ref in late_refs else "")
            if kind == "unclear":
                finding, treatment = "Evidence insufficient", "Request the Customs entry, broker invoice or payment to confirm it is import GST."
            elif in_gl and in_return:
                finding, treatment = "Correctly recorded in both GL and return", "Matched: no reconciliation adjustment."
            elif in_gl and not self.d.has_return_detail:
                finding, treatment = "Evidence insufficient", "The return's transaction detail is needed to confirm it was claimed."
            elif in_gl:
                finding, treatment = "Recorded in GL but not in the return", "Investigate timing and eligibility; a supported reconciling item or a return correction."
            elif in_return:
                finding, treatment = "Included in the return but missing or miscoded in GL", "Proposed accounting correction to the GST control account."
            elif documented:
                finding, treatment = "Supported by documentation but absent from both", "Review both its accounting and its GST return treatment."
            else:
                finding, treatment = "Evidence insufficient", "Request the Customs, broker, invoice or payment documentation."
            items.append({"id": _id("IMP", ln["id"]), "date": ln["date"], "account": ln["account"], "description": ln["description"], "ref": ln["ref"],
                          "amount": amount_, "component": kind, "why": (told.get(ln["id"]) or {}).get("why", ""), "in_gl_gst": in_gl,
                          "in_return": bool(in_return), "return_period": in_return.get("return_period_end") if in_return else None,
                          "finding": finding, "treatment": treatment, "counted_in": counted, "source": ln["source"]})
        return {"items": items, "note": ""}

    # --- 6. payments and corrections (F) ----------------------------------------------------------------------
    def payments(self, alloc: dict, ledger: dict) -> dict:
        gst = set(ledger["gst_accounts"])
        ird_payments = [x for x in alloc["lines"] if x["category"] in ("payment", "refund") and self.su.fy_start <= x["effective"]]
        books = [ln for ln in self.d.gl if not BANK.search(ln["account"])]
        used, rows = set(), []
        for p in ird_payments:
            amt = abs(p["movement"])
            near = [ln for ln in books if ln["id"] not in used and abs(abs(ln["debit"] - ln["credit"]) - amt) < Decimal("0.01")
                    and abs((ln["date"] - p["effective"]).days) <= 14]
            near.sort(key=lambda ln: (0 if ln["account"] in gst else 1, abs((ln["date"] - p["effective"]).days)))
            match = near[0] if near else None
            row = {"id": _id("PM", p["id"]), "ird_date": p["effective"], "ird_type": p["category"], "amount": p["movement"], "period": p["allocated_to"],
                   "ird_ref": p.get("reference", ""), "ird_source": p["source"], "gl": None, "result": "", "confidence": ""}
            if match is None:
                row["result"] = "Not found in the books" if p["effective"] <= (self.su.prep_date or self.bd) else ""
                if p["effective"] <= self.bd:
                    self.flag("payment_missing", "review", f"IRD {p['category']} of {q(amt)} on {p['effective']:%d/%m/%Y} wasn't found in the GL.",
                              "Bank evidence of the payment (do not post an entry before it is seen).", [p["source"]], amt)
            else:
                used.add(match["id"])
                ref_hit = p.get("reference") and _norm_ref(p["reference"]) in _norm_ref(f"{match['ref']} {match['description']}")
                row.update(gl={"id": match["id"], "account": match["account"], "date": match["date"], "ref": match["ref"],
                               "description": match["description"], "source": match["source"]}, confidence="high" if ref_hit else "medium (amount and date)")
                if match["account"] in gst:
                    row["result"] = "Matched to the GST account"
                elif INCOME_TAX.search(match["account"]):
                    row["result"] = f"Coded to {match['account']}"
                    if match["date"] <= self.bd:
                        self._correction("GST payment debited to income tax" if p["category"] == "payment" else "GST refund credited to income tax",
                                         p, match, amt, ledger)
                else:
                    row["result"] = f"Found in {match['account']}: review"
                    self.flag("payment_other_account", "review", f"IRD GST {p['category']} of {q(amt)} was recorded in {match['account']}.",
                              "The entry and what it was for.", [p["source"], match["source"]], amt)
            rows.append(row)
        # Book entries in the GST account that look like tax payments but match no IRD GST payment.
        for ln in self.d.gl:
            if ln["account"] in gst and ln["id"] not in used and ln["date"] <= self.bd and ln["date"] >= self.su.fy_start and \
                    re.search(r"\bird\b|inland\s*revenue|payment|paid|refund", f"{ln['description']} {ln['contact']}", re.I):
                text = f"{ln['description']} {ln['contact']}"
                amt = abs(ln["debit"] - ln["credit"])
                if INCOME_TAX.search(text):
                    self._reverse_correction("Income tax payment debited to GST", ln, amt, "the appropriate income tax account")
                elif PENALTY.search(text):
                    self._reverse_correction("Penalty or interest debited to GST", ln, amt, "the appropriate penalty/interest expense account")
                else:
                    rows.append({"id": _id("PM", ln["id"]), "ird_date": None, "ird_type": "", "amount": None, "period": None, "ird_ref": "", "ird_source": "",
                                 "gl": {"id": ln["id"], "account": ln["account"], "date": ln["date"], "ref": ln["ref"], "description": ln["description"],
                                        "source": ln["source"]},
                                 "result": "In the GST account, not matched to an IRD GST payment", "confidence": ""})
        return {"rows": rows}

    def _correction(self, title, p, match, amt, ledger):
        control = ledger["gst_accounts"][0] if ledger["gst_accounts"] else "GST control"
        payment = p["category"] == "payment"
        lines = ([{"account": control, "debit": amt, "credit": ZERO}, {"account": match["account"], "debit": ZERO, "credit": amt}] if payment else
                 [{"account": match["account"], "debit": amt, "credit": ZERO}, {"account": control, "debit": ZERO, "credit": amt}])
        self.corrections.append({"id": _id("P", p["id"], match["id"]), "title": title, "lines": lines, "gst_effect": -amt if payment else amt,
                                 "explanation": f"IRD shows a GST {p['category']} of {q(amt)} on {p['effective']:%d/%m/%Y}"
                                                f"{' for ' + p['allocated_to'].strftime('%d/%m/%Y') if p['allocated_to'] else ''}; the books recorded it in {match['account']}.",
                                 "evidence": [p["source"], match["source"]], "status": "proposed — not posted", "no_gst": True})

    def _reverse_correction(self, title, ln, amt, other):
        self.corrections.append({"id": _id("P", ln["id"]), "title": title,
                                 "lines": [{"account": other, "debit": amt, "credit": ZERO}, {"account": ln["account"], "debit": ZERO, "credit": amt}],
                                 "gst_effect": amt, "explanation": f"{ln['description'] or 'An entry'} of {q(amt)} on {ln['date']:%d/%m/%Y} is in the GST account. "
                                 "Verify the original entry and chart of accounts before posting.", "evidence": [ln["source"]],
                                 "status": "proposed — not posted", "no_gst": True})

    def import_corrections(self, imports: dict, ledger: dict) -> list[dict]:
        """Import GST in the return but not in the GL GST account: an accounting correction. Import GST in
        the GL but not the return: a reconciling item (deducted) for review."""
        d_items = []
        control = ledger["gst_accounts"][0] if ledger["gst_accounts"] else "GST control"
        for it in imports["items"]:
            if it["counted_in"]:
                it["treatment"] += f" Already counted in {it['counted_in']}: not added again."
                continue
            if it["finding"] == "Included in the return but missing or miscoded in GL":
                amt = abs(it["amount"])
                self.corrections.append({"id": _id("P", it["id"]), "title": "Import GST recorded outside the GST account",
                                         "lines": [{"account": control, "debit": amt, "credit": ZERO}, {"account": it["account"], "debit": ZERO, "credit": amt}],
                                         "gst_effect": -amt, "explanation": f"Import GST {q(amt)} ({it['description']}) was claimed in the return but posted to {it['account']}.",
                                         "evidence": [it["source"]], "status": "proposed — not posted", "no_gst": True})
            elif it["finding"] == "Recorded in GL but not in the return":
                d_items.append({"id": _id("ADJ", it["id"]), "category": "Expenses not claimed", "direction": "input", "effect": -q(abs(it["amount"])),
                                "status": "import GST in the GL, not yet claimed (review timing and eligibility)", "review": True, "journals": [],
                                "late_claims": [], "evidence": [], "year_end_amount": -q(abs(it["amount"])), "subsequent_return": None, "unmatched": None,
                                "description": it["description"], "import": it["id"], "included": True})
        return d_items

    # --- 7. period analysis -----------------------------------------------------------------------------------
    def period_analysis(self, periods: list[dict], ledger: dict, matched_ids: set[str]) -> dict:
        gst = set(ledger["gst_accounts"])
        rows, year = [], {"return_output": ZERO, "gl_output": ZERO, "return_input": ZERO, "gl_input": ZERO}
        settlement = re.compile(r"\bird\b|inland\s*revenue|gst\s*payment|refund|payment to|paid to", re.I)
        for p in periods:
            if p["prior_year"] or p["origin"] != "return" or p["period_end"] > self.bd:
                continue
            start = self._start(p)
            lines = [ln for ln in self.d.gl if ln["account"] in gst and start <= ln["date"] <= p["period_end"]
                     and ln["id"] not in matched_ids and not settlement.search(f"{ln['description']} {ln['contact']}")]
            gl_out = sum((ln["credit"] for ln in lines), ZERO)
            gl_in = sum((ln["debit"] for ln in lines), ZERO)
            r_out, r_in = (p["output"] or ZERO) + (p["box9"] or ZERO), (p["input"] or ZERO) + (p["box13"] or ZERO)
            rows.append({"period_end": p["period_end"], "return_output": r_out, "gl_output": gl_out, "output_residual": gl_out - r_out,
                         "return_input": r_in, "gl_input": gl_in, "input_residual": gl_in - r_in})
            for k, v in (("return_output", r_out), ("gl_output", gl_out), ("return_input", r_in), ("gl_input", gl_in)):
                year[k] += v
        pairs = []
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                for side in ("output_residual", "input_residual"):
                    if a[side] != 0 and abs(a[side] + b[side]) < Decimal("0.01"):
                        pairs.append(f"{side.split('_')[0]}: {a['period_end']:%d/%m/%Y} {q(a[side])} and {b['period_end']:%d/%m/%Y} {q(b[side])}")
        if pairs:
            self.flag("equal_opposite", "info", "Equal and opposite period differences (" + "; ".join(pairs) + "): not resolved without transaction-level matching.",
                      "Transaction ids, references and dates on both sides.")
        note = ("Payments basis: the GL records GST when invoiced, returns when paid, so period residuals include expected timing differences "
                "(bridged at year end by G1/M1)." if self.su.basis == "payments" else
                "Hybrid basis: purchases residuals include expected timing differences." if self.su.basis == "hybrid" else "")
        return {"rows": rows, "year": year, "note": note}

    # --- 8. the bridge --------------------------------------------------------------------------------------------
    def run(self) -> dict:
        self.check_uploads()
        periods = self.returns_schedule()
        alloc = self.allocate(periods)
        ledger = self.ledger()
        opening = self.opening_check(ledger)
        ar = self.timing_side("ar", ledger)
        ap = self.timing_side("ap", ledger)
        timing_refs = {_norm_ref(i["ref"]) for side in (ar, ap) for i in side["items"] if i.get("ref")}
        journals = self.journal_candidates(periods, ledger)
        late, evidence_only = self.late_claim_items(timing_refs)
        adjustments = self.adjustments(journals, late)
        late_refs = {_norm_ref(x["ref"]) for x in late if x.get("ref")}
        imports = self.import_gst(ledger, timing_refs, late_refs)
        adjustments += self.import_corrections(imports, ledger)
        pay = self.payments(alloc, ledger)
        matched_ids = {r["gl"]["id"] for r in pay["rows"] if r.get("gl")}
        analysis = self.period_analysis(periods, ledger, matched_ids)

        in_a = [p for p in periods if p["period_end"] <= self.bd and p["outstanding_bd"] is not None]
        a_current = sum((p["outstanding_bd"] for p in in_a if not p["prior_year"]), ZERO)
        a_prior = sum((p["outstanding_bd"] for p in in_a if p["prior_year"]), ZERO)
        A = a_current + a_prior
        B, C = ar["total"], ap["total"]
        D = sum((a["effect"] for a in adjustments if a.get("included", True)), ZERO)
        E = A + B - C + D
        reported = ledger["reported"]
        correction_effect = sum((c["gst_effect"] for c in self.corrections), ZERO)
        F = (reported + correction_effect) if reported is not None else None
        unexplained = (F - E) if F is not None else None
        blocking = [x for x in self.exceptions if x["severity"] == "blocking"]
        if blocking or F is None:
            status = "Incomplete evidence"
        elif abs(unexplained) > self.su.tolerance:
            status = "Unreconciled"
            self.flag("residual", "review", f"Unexplained difference of {q(unexplained)} remains (stop rule: not offset or adjusted).",
                      "Period analysis by output and input; the next evidence for the largest period residual.", amount_=unexplained)
        elif correction_effect != 0:
            status = "Reconciled subject to corrections"
        else:
            status = "Reconciled"
        return {
            "status": status, "periods": periods, "ird": alloc, "ledger": ledger, "opening": opening, "ar": ar, "ap": ap,
            "journals": journals, "late_claims": late, "late_claims_evidence": evidence_only, "adjustments": adjustments, "imports": imports,
            "payments": pay, "analysis": analysis, "corrections": sorted(self.corrections, key=lambda c: c["id"]),
            "bridge": {"A": A, "A_current": a_current, "A_prior": a_prior, "B": B, "C": C, "D": D, "E": E, "reported": reported,
                       "corrections": correction_effect, "F": F, "unexplained": unexplained, "tolerance": self.su.tolerance},
            "exceptions": self.exceptions,
            "counts": {"blocking": len(blocking), "review": sum(1 for x in self.exceptions if x["severity"] == "review"),
                       "outstanding_returns": sum(1 for p in in_a if (p["outstanding_bd"] or ZERO) != 0)},
        }
