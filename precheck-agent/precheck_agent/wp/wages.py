"""The wages (PAYE) reconciliation agent (AFIT, specification working draft 1.0, 7 Nov 2026).

Two separate conclusions:
- Payroll expense: IRD gross employee earnings (less schedular payments) + net employer KiwiSaver +
  ESCT is the employer-cost baseline; closing less opening wage accruals and the leave provision
  movement bridge it to the accrual P&L; the expected expense is compared with the mapped GL wages
  expense (reported, proposed corrections, adjusted).
- Payroll liabilities: the IRD payroll (EMP) account is rolled forward to the balance date - opening
  payable + current-year charges - payments and credits to the balance date - and compared with the
  GL controls (PAYE, KiwiSaver, ESCT, student loan, child support). Later payments are settlement
  evidence only; penalties and interest are kept apart.

IRD payments are matched to the GL; one charged to wages or income tax becomes a proposed journal
(effect on expense and on liabilities shown). Monthly rows show where an annual difference sits.
Code does every figure; the model reads documents (PDF summaries) and writes the summary.
"""
import logging
import re
import time
from collections import defaultdict
from datetime import date
from decimal import Decimal

from openpyxl import Workbook

from ..gst import ai as A
from ..gst import readers as R
from ..gst import workbook as W
from ..gst.ai import Reader
from ..gst.money import ZERO, amount, day, month_end, q
from ..gst.sources import SourceProblem, gather
from . import sheets as S
from .base import (BANK, Flags, WpStop, _id, conclude, envelope, match_payment, opening_of, read_myir, setup_from, tb_matching,
                   uses_month_first, worst)

logger = logging.getLogger(__name__)
RULES = "wages-1.0"
SKILL = "nz-wages-reconciliation"
EXTRA = ("wage_expense_accounts", "payroll_liability_accounts", "schedular_payments", "opening_ird_payable", "other_expense_adjustments")

KINDS = {
    "payroll_summary": "IRD payroll (employment information) summary for the year",
    "payroll_ird": "IRD payroll transaction summary (the EMP account)",
    "general_ledger": "General ledger (full year)",
    "trial_balance": "Trial balance (year end)",
    "journal_report": "Journal report / audit history",
    "prior_wages": "Prior-year wages reconciliation",
    "payroll_register": "Payroll register or payroll provider statement",
    "other": "Other / not used",
}
_RULES = [
    ("prior_wages", r"((prior|previous|last)\s*(year|yr)|\bpy\b).*(wage|payroll|paye)|(wage|payroll|paye).*((prior|previous|last)\s*(year|yr)|\bpy\b)"),
    ("payroll_ird", r"(paye|payroll|\bemp\b|employ).*transaction|transaction\s*summary"),
    ("payroll_summary", r"(paye|payroll|\bemp\b|employ).*summary|employment\s*information|payday\s*filing"),
    ("journal_report", r"journal\s*report|manual\s*journals?|audit\s*(history|trail)"),
    ("general_ledger", r"general\s*ledger|ledger\s*detail|\bgl\b"),
    ("trial_balance", r"trial\s*balance|\btb\b"),
    ("payroll_register", r"payroll\s*register|pay\s*run|payslip|smartly|ipayroll|employment\s*hero|provider\s*statement"),
]

R.FIELDS["payroll_summary"] = {
    "month": ["month ending", "month end", "period ending", "pay period", "payday", "month", "period"],
    "gross": ["gross earnings and/or schedular payments", "gross earnings", "gross"],
    "not_acc": ["not liable for acc earners levy", "not liable for acc"],
    "paye": ["paye incl tax on schedular payments", "paye", "paye deductions"],
    "child_support": ["child support deductions", "child support"],
    "student_loan": ["student loan deductions", "student loan"],
    "ks_employee": ["kiwisaver deductions", "kiwisaver employee deductions", "employee kiwisaver"],
    "ks_employer": ["net kiwisaver employer contributions", "kiwisaver employer contributions", "employer kiwisaver"],
    "esct": ["esct deductions", "esct"],
    "ess": ["ess benefits component included in gross earnings", "ess benefits"],
    "prior_gross": ["total prior period gross adjustments"],
    "prior_paye": ["total prior period paye adjustments"],
    "total_deductions": ["total deductions"],
}
R.REQUIRED["payroll_summary"] = ["month", "gross"]
MONTH_FIELDS = ("gross", "not_acc", "paye", "child_support", "student_loan", "ks_employee", "ks_employer", "esct", "ess", "prior_gross", "prior_paye",
                "total_deductions")
A.SCHEMAS["payroll_summary"] = A._obj({"employer_contribution_label": A._STR, "months": A._list({
    "month_end": A._STR, **{f: A._STR for f in MONTH_FIELDS}, "source": A._STR})})
A.ASK["payroll_summary"] = ("Read the IRD payroll (employment information) summary: one record per month ending, with each column as shown (gross earnings "
                            "and/or schedular payments, PAYE, child support, student loan, KiwiSaver deductions, net KiwiSaver employer contributions, ESCT, "
                            "ESS, prior-period adjustments, total deductions). The columns may continue on a later page in the same row order: join them "
                            "row by row. Leave out the totals row. Dates as YYYY-MM-DD; myIR writes them month first (4/30/2025). Give the employer "
                            "KiwiSaver column's heading exactly as printed.")
A.SCHEMAS["prior_wages"] = A._obj({"balance_date": A._STR, "ird_payable_closing": A._STR, "gl_liabilities_closing": A._STR, "wage_accrual_closing": A._STR,
                                    "leave_provision_closing": A._STR, "unresolved": A._list({"item": A._STR, "amount": A._STR, "source": A._STR})})
A.ASK["prior_wages"] = ("Read last year's wages reconciliation: the IRD payroll principal payable at its balance date, the GL payroll liabilities, the "
                        "closing wage accrual and leave provision, and unresolved items. Payable balances as positive amounts.")

WAGE_EXP = re.compile(r"wages|salar|kiwi\s*saver|\besct\b|employer\s*(super|contrib)|staff\s*costs?|payroll|holiday\s*pay|\bacc\s*levy|bonus", re.I)
NOT_EXPENSE = re.compile(r"payable|accru|provision|clearing|deduction|liabilit|control|suspense|advance|owing", re.I)
CONTRACTOR = re.compile(r"contract|schedular|subcontract", re.I)
LIAB = re.compile(r"\bpaye\b|kiwi\s*saver|\besct\b|student\s*loan|child\s*support|employee\s*deduction|payroll\s*(liabilit|clearing|deduction|payable)|"
                  r"\bird\b.*(emp|payroll)|employer\s*deductions|withholding\s*tax\s*payable", re.I)
LIAB_WORDS = re.compile(r"payable|liabilit|deduction|clearing|control|owing|due", re.I)
WAGE_ACCRUAL = re.compile(r"(accru\w*\s*(wages|salar|bonus|payroll))|((wages|salar|bonus|payroll)\s*accru)", re.I)
LEAVE = re.compile(r"holiday\s*pay\s*(accru|provision|payable|liabilit)|annual\s*leave|leave\s*(provision|accru|liabilit)", re.I)
NET_WAGES = re.compile(r"(net\s*)?wages\s*payable|salar(y|ies)\s*payable|net\s*pay\b", re.I)
INCOME_TAX = re.compile(r"income\s*tax|provisional\s*tax|terminal\s*tax|tax\s*payable", re.I)
CHARGE_PARTS = [("PAYE", r"paye"), ("KiwiSaver employee", r"kiwi\s*saver\s*employee"), ("KiwiSaver employer", r"kiwi\s*saver\s*employer|voluntary\s*kiwi"),
                ("ESCT", r"superannuation\s*contribution\s*tax|\besct\b"), ("Student loan", r"student\s*loan"), ("Child support", r"child\s*support")]


def classify(sources, reader) -> None:
    unknown = []
    for src in sources:
        if src.error:
            src.kind, src.kind_how = "other", "unreadable"
            continue
        name = re.sub(r"[_\-.]+", " ", src.name.lower())
        kind = next((k for k, p in _RULES if re.search(p, name)), None)
        if kind is None:
            from ..gst.sources import full_text

            head = full_text(src, limit=1500).lower()
            kind = next((k for k, p in _RULES if re.search(p, head)), None)
        if kind:
            src.kind, src.kind_how = kind, "name"
        else:
            unknown.append(src)
    if unknown and reader is not None:
        for src, kind in zip(unknown, reader.classify(unknown, KINDS)):
            src.kind, src.kind_how = (kind if kind in KINDS else "other"), "ai"


def read_summary(src, ai) -> dict:
    us = uses_month_first(src)
    months, label = [], ""
    if src.sheets and (t := R.find_table(src, "payroll_summary", ai)):
        sheet = next(sh for sh in src.sheets if sh["name"] == t.sheet)
        heads = next((values for r, values in sheet["rows"] if r == t.header_row), [])
        col = t.cols.get("ks_employer")
        label = str(heads[col]) if col is not None and col < len(heads) else ""
        for row_no, values in t.rows:
            end = day(t.get(values, "month"), us=us)
            if end is None:
                continue
            months.append({"id": f"{src.sid}:{row_no}", "month_end": month_end(end), **{f: amount(t.get(values, f)) for f in MONTH_FIELDS},
                           "source": t.ref(row_no)})
        return {"months": months, "employer_label": label, "problem": "" if months else "No months were found in the payroll summary."}
    got = ai.extract("payroll_summary", src) if ai else {}
    for n, r in enumerate(got.get("months", []), start=1):
        end = day(r.get("month_end"))
        if end is None:
            continue
        months.append({"id": f"{src.sid}:ai:{n}", "month_end": month_end(end), **{f: amount(r.get(f)) for f in MONTH_FIELDS},
                       "source": f"{src.sid} {src.name}, {r.get('source', '')}"})
    return {"months": months, "employer_label": got.get("employer_contribution_label", ""),
            "problem": "" if months else "The payroll summary could not be read: export it from myIR as Excel, or check the PDF."}


def read_prior(src, ai) -> dict:
    got = ai.extract("prior_wages", src) if ai else {}
    if not got or all(got.get(k) in ("", None) for k in ("ird_payable_closing", "gl_liabilities_closing", "wage_accrual_closing")):
        return {"problem": "Last year's wages reconciliation could not be read: check its closing balances by hand."}
    return {**{k: amount(got.get(k)) for k in ("ird_payable_closing", "gl_liabilities_closing", "wage_accrual_closing", "leave_provision_closing")},
            "unresolved": got.get("unresolved") or [], "source": f"{src.sid} {src.name}", "problem": ""}


class Wages:
    def __init__(self, su, data: dict):
        self.su, self.d, self.f = su, data, Flags()
        self.bd, self.start = su.balance_date, su.fy_start
        self.corrections: list[dict] = []

    # --- the accounts -------------------------------------------------------------------------------------
    def mapping(self) -> dict:
        tb = self.d["tb"]
        expense = [r for r in tb_matching(tb, self.su.accounts("wage_expense_accounts"), WAGE_EXP, NOT_EXPENSE)
                   if (self.su.accounts("wage_expense_accounts") or (r["balance"] > 0 and not CONTRACTOR.search(r["account"])
                                                                    and not re.search(r"liabilit|asset|equity", r.get("type", ""), re.I)))]
        used = {r["account"] for r in expense}
        liab = [r for r in tb_matching(tb, self.su.accounts("payroll_liability_accounts"), LIAB) if r["account"] not in used
                and (self.su.accounts("payroll_liability_accounts") or LIAB_WORDS.search(r["account"]) or r["balance"] < 0
                     or re.search(r"liabilit", r.get("type", ""), re.I))]
        used |= {r["account"] for r in liab}
        accrual = [r for r in tb if WAGE_ACCRUAL.search(r["account"]) and r["account"] not in used]
        leave = [r for r in tb if LEAVE.search(r["account"]) and r["account"] not in used and r not in accrual]
        net = [r for r in tb if NET_WAGES.search(r["account"]) and r["account"] not in used and r not in accrual and r not in leave]
        contractors = [r for r in tb if CONTRACTOR.search(r["account"]) and WAGE_EXP.search(r["account"] + " wages")]
        rows = ([{**r, "role": "Wages expense"} for r in expense] + [{**r, "role": "Payroll liability"} for r in liab]
                + [{**r, "role": "Wage accrual"} for r in accrual] + [{**r, "role": "Leave provision"} for r in leave]
                + [{**r, "role": "Net wages payable"} for r in net] + [{**r, "role": "Contractors (separate schedule)"} for r in contractors])
        if not expense:
            self.f.add("no_expense_accounts", "blocking", "No wages expense accounts were found in the trial balance.",
                       "Name the wages expense accounts in the job settings.", side="expense")
        if not liab:
            self.f.add("no_liability_accounts", "blocking", "No payroll liability accounts (PAYE, KiwiSaver, ESCT) were found in the trial balance.",
                       "Name the payroll liability accounts in the job settings.", side="liabilities")
        if contractors:
            self.f.add("contractors", "review", f"Contractor / schedular accounts found ({', '.join(r['account'] for r in contractors)}): kept out of wages; "
                       "match them to schedular payments in a separate schedule.", "The contractor payments schedule.", side="expense")
        return {"expense": expense, "liabilities": liab, "accrual": accrual, "leave": leave, "net_wages": net, "contractors": contractors, "rows": rows}

    # --- payroll expense ----------------------------------------------------------------------------------
    def months(self) -> list[dict]:
        by_end: dict[date, dict] = {}
        for m in self.d["months"]:
            if self.start <= m["month_end"] <= self.bd:
                if m["month_end"] in by_end:
                    self.f.add("duplicate_month", "info", f"Two filings for the month ending {m['month_end']:%d/%m/%Y}: the later one is used (an amendment "
                               "replaces, it isn't added).", refs=[m["source"]], side="expense")
                by_end[m["month_end"]] = m
        ends, d = [], month_end(self.start)
        while d <= self.bd:
            ends.append(d)
            d = month_end(date(d.year + (d.month // 12), d.month % 12 + 1, 1))
        if self.d["months"]:
            for end in ends:
                if end not in by_end:
                    self.f.add("missing_month", "blocking", f"The payroll summary has no month ending {end:%d/%m/%Y} (a month with no payroll is still "
                               "shown as nil).", "The IRD payroll summary for the whole year.", side="expense")
        return [by_end[e] for e in sorted(by_end)]

    def expense(self, months: list[dict], m: dict) -> dict:
        tot = {f: sum((x[f] or ZERO for x in months), ZERO) for f in MONTH_FIELDS}
        gross_employer = bool(self.d.get("employer_label")) and "net" not in self.d["employer_label"].lower()
        esct = ZERO if gross_employer else tot["esct"]
        if gross_employer:
            self.f.add("employer_gross", "review", f"The employer KiwiSaver column is headed “{self.d['employer_label']}” (not net): ESCT is not added again.",
                       "Confirm the field definition for this report layout.", side="expense")
        schedular = self.su.money("schedular_payments") or ZERO
        if tot["gross"] and not self.su.extra.get("schedular_payments"):
            self.f.add("schedular_unknown", "info", "IRD's gross earnings combine employee earnings and schedular payments: none were given, so all of it is "
                       "treated as employee earnings.", "The schedular payments in the year, if any.", side="expense")
        baseline = tot["gross"] - schedular + tot["ks_employer"] + esct
        accruals = []
        for role, rows in (("Wage accrual", m["accrual"]), ("Leave provision", m["leave"])):
            if not rows:
                continue
            closing = sum((-r["balance"] for r in rows), ZERO)
            opening = opening_of(self.d["gl_opening"], rows)
            how = "GL opening balance"
            if opening is not None:
                opening = -opening
            elif role == "Wage accrual" and (self.d.get("prior") or {}).get("wage_accrual_closing") is not None:
                opening, how = self.d["prior"]["wage_accrual_closing"], "last year's wages reconciliation"
            elif role == "Leave provision" and (self.d.get("prior") or {}).get("leave_provision_closing") is not None:
                opening, how = self.d["prior"]["leave_provision_closing"], "last year's wages reconciliation"
            elif self.su.first_year:
                opening, how = ZERO, "first-year entity"
            included = opening is not None
            if not included:
                self.f.add("accrual_opening", "review", f"{role}: the opening balance couldn't be established, so its movement isn't in the bridge "
                           f"(closing {q(closing):,}).", "The opening balance (GL opening or last year's workpaper).", [r["source"] for r in rows], closing,
                           side="expense")
            if role == "Leave provision":
                self.f.add("leave_movement", "review", "The leave provision movement is included only as far as it is charged to the wages expense "
                           "selected: confirm it isn't already counted.", "The leave provision schedule.", side="expense")
            accruals.append({"role": role, "accounts": [r["account"] for r in rows], "opening": opening, "closing": closing, "how": how,
                             "movement": (closing - opening) if included else None, "included": included})
        other = self.su.money("other_expense_adjustments") or ZERO
        movement = sum((a["movement"] for a in accruals if a["included"]), ZERO)
        expected = baseline + movement + other
        reported = sum((r["balance"] for r in m["expense"]), ZERO)
        return {"totals": tot, "schedular": schedular, "esct_used": esct, "baseline": baseline, "accruals": accruals, "other": other,
                "expected": expected, "reported": reported}

    # --- payroll liabilities -------------------------------------------------------------------------------
    def liabilities(self, m: dict) -> dict:
        lines = [x for x in self.d["ird"] if not x["account_type"] or re.search(r"payroll|emp|paye|employ", x["account_type"], re.I)]
        principal = [x for x in lines if x["category"] not in ("penalty", "interest")]
        charges = [x for x in lines if x["category"] in ("penalty", "interest")]
        fy_charges = [x for x in principal if x["category"] == "charge" and x["period_end"] and self.start <= x["period_end"] <= self.bd]
        credits = [x for x in principal if x["category"] != "charge" and self.start <= x["date"] <= self.bd]
        later = [x for x in principal if x["category"] != "charge" and x["date"] > self.bd and (x["period_end"] or self.bd) <= self.bd]
        prior_lines = [x for x in principal if x["period_end"] and x["period_end"] < self.start]
        opening, how = self.su.money("opening_ird_payable"), "job settings"
        if opening is None and (self.d.get("prior") or {}).get("ird_payable_closing") is not None:
            opening, how = self.d["prior"]["ird_payable_closing"], "last year's wages reconciliation"
        if opening is None and prior_lines:
            opening, how = -sum((x["amount"] for x in prior_lines if x["category"] != "charge"), ZERO), "IRD's settlement after the year start"
            self.f.add("opening_derived", "review", f"Opening IRD payroll payable taken from its settlement in the year ({q(opening):,}).",
                       "Last year's wages reconciliation.", side="liabilities")
        if opening is None and self.su.first_year:
            opening, how = ZERO, "first-year entity"
        if opening is None and lines:
            self.f.add("no_opening", "blocking", "The opening IRD payroll payable couldn't be established (absence isn't a nil balance).",
                       "Last year's wages reconciliation, or the opening IRD payable in the job settings.", side="liabilities")
        # Prior periods' charges are in the opening balance; payments in the year for them are among the credits.
        charge_total = sum((x["amount"] for x in fy_charges), ZERO)
        credit_total = sum((x["amount"] for x in credits), ZERO)
        closing = (opening + charge_total + credit_total) if opening is not None else None
        parts = defaultdict(lambda: ZERO)
        for x in fy_charges:
            part = next((label for label, p in CHARGE_PARTS if re.search(p, x["type"], re.I)), "Other")
            parts[part] += x["amount"]
        gl = sum((-r["balance"] for r in m["liabilities"]), ZERO)
        return {"opening": opening, "opening_how": how, "charges": charge_total, "credits": credit_total, "closing": closing,
                "later": sum((x["amount"] for x in later), ZERO), "penalties": sum((x["amount"] for x in charges), ZERO), "parts": dict(parts),
                "gl": gl, "net_wages": sum((-r["balance"] for r in m["net_wages"]), ZERO), "lines": lines, "credit_lines": credits}

    def check_parts(self, exp: dict, liab: dict):
        t = exp["totals"]
        pairs = [("PAYE", t["paye"]), ("KiwiSaver employee", t["ks_employee"]), ("Student loan", t["student_loan"]), ("Child support", t["child_support"])]
        for label, summary in pairs:
            charged = liab["parts"].get(label, ZERO)
            if (summary or charged) and abs(summary - charged) > Decimal("0.01"):
                self.f.add("summary_vs_charges", "review", f"{label}: the payroll summary shows {q(summary):,} for the year but IRD charged {q(charged):,}.",
                           "Amended filings or periods outside the report.", side="liabilities", amount_=summary - charged)

    def payments(self, m: dict, liab: dict) -> list[dict]:
        expense = {r["account"].lower() for r in m["expense"]}
        liability = {r["account"].lower() for r in m["liabilities"]}
        target = m["liabilities"][0]["account"] if m["liabilities"] else "PAYE payable"
        used, rows = set(), []
        for p in [x for x in liab["credit_lines"] if x["category"] == "payment"]:
            ln = match_payment(p, self.d["gl"], used, liability)
            row = {"id": _id("PM", p["id"]), "date": p["date"], "period": p["period_end"], "amount": p["amount"], "ird_source": p["source"],
                   "gl": ({"account": ln["account"], "date": ln["date"], "ref": ln["ref"], "source": ln["source"]} if ln else None), "result": ""}
            amt = abs(p["amount"])
            if ln is None:
                row["result"] = "Not found in the books"
                self.f.add("payment_missing", "review", f"IRD payroll payment of {q(amt):,} on {p['date']:%d/%m/%Y} wasn't found in the GL.",
                           "Bank or payroll provider evidence (no entry is proposed before it's seen).", [p["source"]], amt, side="liabilities")
            elif ln["account"].lower() in liability:
                row["result"] = "Matched to the payroll liability"
            elif ln["account"].lower() in expense:
                row["result"] = f"Charged to {ln['account']}"
                self._fix("IRD payment debited to salary expense despite an existing liability", target, ln["account"], amt, p, ln,
                          expense=-amt, liabilities=-amt)
            elif INCOME_TAX.search(ln["account"]) or re.search(r"suspense", ln["account"], re.I):
                row["result"] = f"Coded to {ln['account']}"
                self._fix("Payroll payment coded to income tax or suspense", target, ln["account"], amt, p, ln, liabilities=-amt)
            else:
                row["result"] = f"Found in {ln['account']}: review"
                self.f.add("payment_other", "review", f"IRD payroll payment of {q(amt):,} was recorded in {ln['account']}.", "The entry and what it was for.",
                           [p["source"], ln["source"]], amt, side="liabilities")
            rows.append(row)
        return rows

    def _fix(self, title, debit, credit, amt, p, ln, expense=ZERO, liabilities=ZERO):
        self.corrections.append({"id": _id("P", p["id"], ln["id"]), "title": title,
                                 "lines": [{"account": debit, "debit": amt, "credit": ZERO}, {"account": credit, "debit": ZERO, "credit": amt}],
                                 "expense_effect": expense, "liability_effect": liabilities, "effective": ln["date"],
                                 "explanation": f"IRD shows a payroll payment of {q(amt):,} on {p['date']:%d/%m/%Y}; the books recorded it in {credit}. "
                                                "Allocate by verified deduction components before posting.",
                                 "evidence": [p["source"], ln["source"]], "status": "proposed — not posted"})

    def monthly(self, months: list[dict], m: dict) -> list[dict]:
        accounts = {r["account"] for r in m["expense"]}
        gl_by_month = defaultdict(lambda: ZERO)
        for ln in self.d["gl"]:
            if ln["account"] in accounts and self.start <= ln["date"] <= self.bd:
                gl_by_month[month_end(ln["date"])] += ln["debit"] - ln["credit"]
        rows = []
        for x in months:
            ird = (x["gross"] or ZERO) + (x["ks_employer"] or ZERO) + (x["esct"] or ZERO)
            gl = gl_by_month.get(x["month_end"], ZERO)
            rows.append({"month_end": x["month_end"], "gross": x["gross"], "ks_employer": x["ks_employer"], "esct": x["esct"], "ird": ird, "gl": gl,
                         "residual": gl - ird if self.d["gl"] else None})
        pairs = [f"{a['month_end']:%b %Y} and {b['month_end']:%b %Y}" for i, a in enumerate(rows) for b in rows[i + 1:]
                 if a["residual"] and b["residual"] and abs(a["residual"] + b["residual"]) < Decimal("0.01")]
        if pairs:
            self.f.add("equal_opposite", "info", "Equal and opposite monthly differences (" + "; ".join(pairs) + "): timing candidates, not proof.",
                       "The payroll run or event reference on both sides.", side="expense")
        return rows

    def run(self) -> dict:
        if not self.d["months"]:
            self.f.add("no_summary", "blocking", "No IRD payroll summary was found.", "The IRD payroll (employment information) summary for the year.",
                       side="expense")
        if not self.d["ird"]:
            self.f.add("no_ird", "blocking", "No IRD payroll transaction summary was found.", "The myIR transaction summary for the EMP account.",
                       side="liabilities")
        if not self.d["tb"]:
            self.f.add("no_tb", "blocking", "No trial balance was found.", "The year-end trial balance.")
        if not self.d["gl"]:
            self.f.add("no_gl", "review", "No general ledger: payments can't be matched and monthly GL totals can't be shown.", "The full general ledger.")
        if self.d.get("prior") is None and not self.su.first_year:
            self.f.add("no_prior", "review", "No prior-year wages reconciliation: openings come from the ledger and IRD only.",
                       "Last year's wages reconciliation.")
        for p in self.d["problems"]:
            self.f.add("reading", "review", p["text"], p.get("evidence", ""), [p.get("source", "")])
        m = self.mapping()
        months = self.months()
        exp = self.expense(months, m)
        liab = self.liabilities(m)
        if months and liab["lines"]:
            self.check_parts(exp, liab)
        pay = self.payments(m, liab) if self.d["gl"] else []
        monthly = self.monthly(months, m)
        exp_fix = sum((c["expense_effect"] for c in self.corrections), ZERO)
        liab_fix = sum((c["liability_effect"] for c in self.corrections), ZERO)
        adjusted_exp = exp["reported"] + exp_fix
        exp_residual = (adjusted_exp - exp["expected"]) if months and m["expense"] else None
        adjusted_liab = liab["gl"] + liab_fix
        liab_residual = (adjusted_liab - liab["closing"]) if liab["closing"] is not None and m["liabilities"] else None
        exp_status = conclude(bool(self.f.blocking("expense")), exp_residual, self.su.tolerance, exp_fix)
        liab_status = conclude(bool(self.f.blocking("liabilities")), liab_residual, self.su.tolerance, liab_fix)
        for side, res, status in (("expense", exp_residual, exp_status), ("liabilities", liab_residual, liab_status)):
            if status == "Unreconciled":
                self.f.add(f"{side}_residual", "review", f"Payroll {side}: unexplained residual of {q(res):,} (not forced to agree).",
                           "Monthly analysis; accrual schedules; the payroll register.", amount_=res, side=side)
        if liab["net_wages"]:
            self.f.add("net_wages", "info", f"Net wages payable in the GL: {q(liab['net_wages']):,}. IRD's account doesn't show whether employees were paid.",
                       "The payroll register or bank detail.", side="liabilities")
        if liab["penalties"]:
            self.f.add("penalties", "review", f"IRD penalties and interest of {q(liab['penalties']):,}: kept out of payroll principal and wages.",
                       "The penalty/interest expense and liability accounts.", side="liabilities")
        t = exp["totals"]
        exp_lines = [
            {"heading": True, "label": "Payroll expense"},
            {"label": "Employee gross earnings and/or schedular payments (IRD)", "value": t["gross"], "ref": "IRD monthly totals", "key": "g"},
            {"label": "Less schedular payments included in gross", "value": -exp["schedular"], "input": True, "key": "s"},
            {"label": "Net employer KiwiSaver contributions", "value": t["ks_employer"], "ref": "IRD monthly totals", "key": "k"},
            {"label": "Related ESCT", "value": exp["esct_used"], "ref": "IRD monthly totals", "key": "e"},
            {"label": "IRD-based employer-cost baseline", "formula": "={g}+{s}+{k}+{e}", "value": exp["baseline"], "strong": True, "key": "base"},
        ]
        keys = []
        for n, a in enumerate(exp["accruals"]):
            exp_lines.append({"label": f"{a['role']} movement (closing {q(a['closing']):,} less opening {q(a['opening']) if a['opening'] is not None else '—'})",
                              "value": a["movement"] if a["included"] else 0, "ref": "Accruals & prior-year", "note": "" if a["included"] else "opening not established",
                              "key": f"a{n}"})
            keys.append(f"a{n}")
        exp_lines += [
            {"label": "Other supported items", "value": exp["other"], "input": True, "key": "o"},
            {"label": "Expected P&L wages expense", "formula": "={base}" + "".join(f"+{{{k}}}" for k in keys) + "+{o}", "value": exp["expected"],
             "strong": True, "key": "x"},
            {"label": "Reported GL wages expense (mapped accounts)", "value": exp["reported"], "ref": "GL mapping", "key": "r"},
            {"label": "Proposed corrections (not posted)", "value": exp_fix, "ref": "Proposed journals", "key": "c"},
            {"label": "Adjusted GL wages expense", "formula": "={r}+{c}", "value": adjusted_exp, "strong": True, "key": "ag"},
            {"label": "Residual (adjusted GL less expected)", "formula": "={ag}-{x}", "value": exp_residual, "strong": True},
        ]
        liab_lines = [
            {"heading": True, "label": "Payroll liabilities (IRD EMP account)"},
            {"label": f"Opening IRD payroll payable ({liab['opening_how']})", "value": liab["opening"], "key": "op"},
            {"label": "Current-year charges (deductions and contributions)", "value": liab["charges"], "ref": "IRD settlements", "key": "ch"},
            {"label": "Payments and credits to the balance date", "value": liab["credits"], "ref": "IRD settlements", "key": "cr"},
            {"label": "IRD payroll principal payable at the balance date", "formula": "={op}+{ch}+{cr}", "value": liab["closing"], "strong": True, "key": "cl"},
            {"label": "GL payroll liabilities (PAYE, KiwiSaver, ESCT, deductions)", "value": liab["gl"], "ref": "GL mapping", "key": "gl"},
            {"label": "Proposed corrections (not posted)", "value": liab_fix, "ref": "Proposed journals", "key": "lc"},
            {"label": "Adjusted GL payroll liabilities", "formula": "={gl}+{lc}", "value": adjusted_liab, "strong": True, "key": "al"},
            {"label": "Residual (adjusted GL less IRD)", "formula": "={al}-{cl}", "value": liab_residual, "strong": True},
            {"label": "Paid after the balance date (settlement evidence only)", "value": liab["later"], "note": "doesn't remove the year-end liability"},
            {"label": "Penalties and interest (kept apart)", "value": liab["penalties"]},
            {"label": "Net wages payable in the GL (tested separately)", "value": liab["net_wages"]},
        ]
        status = worst(exp_status, liab_status)
        counts = {s_: sum(1 for x in self.f.items if x["severity"] == s_) for s_ in ("blocking", "review", "info")}
        return {"agent": "wages", "status": status, "expense_status": exp_status, "liability_status": liab_status,
                "conclusions": [{"label": "Payroll expense", "status": exp_status, "residual": exp_residual},
                                {"label": "Payroll liabilities", "status": liab_status, "residual": liab_residual}],
                "lines": exp_lines + liab_lines, "expense_lines": exp_lines, "liability_lines": liab_lines, "expense": {k: v for k, v in exp.items() if k != "totals"} | {"totals": exp["totals"]},
                "liabilities": {k: v for k, v in liab.items() if k not in ("lines", "credit_lines")}, "months": monthly, "month_rows": months,
                "mapping": m["rows"], "ird_lines": liab["lines"], "payments": pay, "corrections": self.corrections, "exceptions": self.f.items,
                "counts": counts, "residuals": {"expense": exp_residual, "liabilities": liab_residual}}


# --- the workpaper ---------------------------------------------------------------------------------------------

def workbook(result: dict, su, meta: dict) -> bytes:
    import io

    r = result
    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.sheet_properties.tabColor = W.MAROON
    for i, w in {1: 64, 2: 18, 3: 44, 4: 4}.items():
        ws.column_dimensions[chr(64 + i)].width = w
    row = W.header(ws, su, meta, "Wages reconciliation", "W1", 4, note=f"Year {su.fy_start:%d/%m/%Y} to {su.balance_date:%d/%m/%Y} · expense and liabilities "
                                                                          "concluded separately")
    row = S.banner(ws, row, r["status"])
    for c in r["conclusions"]:
        W._put(ws, f"A{row}", f"{c['label']}: {c['status']}", font=W.F_BOLD)
        W._money(ws, f"B{row}", c["residual"], font=W.F_BOLD)
        W._put(ws, f"C{row}", "residual", font=W.F_SMALL)
        row += 1
    row = S.statement(ws, row + 1, r["lines"], title="Expense and liability bridges") + 2
    W._put(ws, f"A{row}", "Commentary", font=W.F_SECTION)
    ws.merge_cells(f"A{row + 1}:C{row + 5}")
    W._put(ws, f"A{row + 1}", result.get("summary") or "", align=W.WRAP, border=W.BOX)
    W.signoff(ws, row + 7, su, meta)
    W._print_setup(ws, landscape=False)

    ws, row = W.sheet(wb, "IRD monthly totals", "W2", su, meta, {1: 13, 2: 15, 3: 13, 4: 13, 5: 13, 6: 13, 7: 13, 8: 13, 9: 13, 10: 13, 11: 40},
                      note="The IRD payroll summary month by month (payday basis), as filed.")
    head = row
    W.table(ws, row, ["Month ending", "Gross earnings", "PAYE", "KiwiSaver employee", "Net KiwiSaver employer", "ESCT", "Student loan", "Child support",
                      "Prior-period adj.", "Total deductions", "Source"],
            [[x["month_end"], x["gross"], x["paye"], x["ks_employee"], x["ks_employer"], x["esct"], x["student_loan"], x["child_support"],
              (x["prior_gross"] or ZERO) + (x["prior_paye"] or ZERO), x["total_deductions"], x["source"]] for x in r["month_rows"]],
            money=tuple(range(2, 11)), wrap=(11,), totals=tuple(range(2, 11)))
    W._finish(ws, head)

    ws, row = W.sheet(wb, "GL mapping", "W3", su, meta, {1: 12, 2: 40, 3: 18, 4: 16, 5: 30, 6: 44},
                      note="Each trial balance account the reconciliation uses and its role. Correct a mapping in the job settings and run again.")
    head = row
    W.table(ws, row, ["Code", "Account", "Type", "Balance (debit +)", "Role", "Source"],
            [[x.get("code"), x["account"], x.get("type", ""), x["balance"], x["role"], x["source"]] for x in r["mapping"]], money=(4,), wrap=(2, 6))
    W._finish(ws, head)

    ws, row = W.sheet(wb, "IRD settlements", "W4", su, meta, {1: 12, 2: 12, 3: 34, 4: 14, 5: 14, 6: 26, 7: 12, 8: 30, 9: 40},
                      note="The IRD payroll (EMP) account line by line, and each IRD payment matched to the ledger.")
    head = row
    end = W.table(ws, row, ["Date", "Period ending", "Transaction", "Category", "Amount (owed +)", "Account type", "", "", "Source"],
                  [[x["date"], x["period_end"], x["type"], x["category"], x["amount"], x["account_type"], "", "", x["source"]] for x in r["ird_lines"]],
                  money=(5,), wrap=(3, 9))
    W.table(ws, end + 3, ["IRD date", "Period", "Amount", "GL account", "GL date", "GL reference", "Result", "IRD source", "GL source"],
            [[p["date"], p["period"], p["amount"], (p["gl"] or {}).get("account"), (p["gl"] or {}).get("date"), (p["gl"] or {}).get("ref"), p["result"],
              p["ird_source"], (p["gl"] or {}).get("source")] for p in r["payments"]], money=(3,), wrap=(7, 8, 9), title="Payment matching")
    W._finish(ws, head)

    ws, row = W.sheet(wb, "Liability roll-forward", "W5", su, meta, {1: 64, 2: 18, 3: 44},
                      note="IRD principal rolled forward to the balance date and compared with the GL controls. Later payments are settlement evidence only.")
    S.statement(ws, row, r["liability_lines"])
    parts = r["liabilities"]["parts"]
    if parts:
        W.table(ws, ws.max_row + 3, ["Component charged in the year", "NZD"], [[k, v] for k, v in parts.items()], money=(2,), totals=(2,),
                title="Charges by component")
    W._print_setup(ws, landscape=False)

    ws, row = W.sheet(wb, "Accruals & prior-year", "W6", su, meta, {1: 22, 2: 40, 3: 15, 4: 15, 5: 15, 6: 30, 7: 12},
                      note="Wage accruals and the leave provision bridge the payday-based baseline to the accrual P&L.")
    head = row
    W.table(ws, row, ["Item", "Accounts", "Opening", "Closing", "Movement", "Opening from", "In bridge"],
            [[a["role"], ", ".join(a["accounts"]), a["opening"], a["closing"], a["movement"], a["how"], "Yes" if a["included"] else "No"]
             for a in r["expense"]["accruals"]], money=(3, 4, 5), wrap=(2,))
    W._finish(ws, head)

    ws, row = W.sheet(wb, "Monthly differences", "W7", su, meta, {1: 13, 2: 15, 3: 15, 4: 13, 5: 16, 6: 16, 7: 15},
                      note="IRD employer cost (gross + net employer KiwiSaver + ESCT) against the GL wages expense posted in the month.")
    head = row
    W.table(ws, row, ["Month ending", "Gross earnings", "Net employer KiwiSaver", "ESCT", "IRD employer cost", "GL wages expense", "Difference"],
            [[x["month_end"], x["gross"], x["ks_employer"], x["esct"], x["ird"], x["gl"], x["residual"]] for x in r["months"]],
            money=(2, 3, 4, 5, 6, 7), totals=(2, 3, 4, 5, 6, 7))
    W._finish(ws, head)

    S.corrections_sheet(wb, su, meta, r["corrections"], "W8", (("expense_effect", "Effect on expense"), ("liability_effect", "Effect on liabilities")))
    S.exceptions_sheet(wb, su, meta, r["exceptions"], "W9")
    S.sources_sheet(wb, su, meta, result["sources"], "W10")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# --- the run ---------------------------------------------------------------------------------------------------

def read_all(sources, reader) -> dict:
    d = {"months": [], "employer_label": "", "ird": [], "gl": [], "gl_opening": {}, "tb": [], "journals": [], "prior": None, "problems": []}
    for src in sources:
        if src.error:
            d["problems"].append({"text": f"{src.name}: {src.error}", "source": src.sid})
            continue
        problem = ""
        if src.kind == "payroll_summary":
            got = read_summary(src, reader)
            d["months"] += got["months"]
            d["employer_label"] = d["employer_label"] or got.get("employer_label", "")
            problem = got["problem"]
        elif src.kind == "payroll_ird":
            got = read_myir(src, reader)
            d["ird"] += got["lines"]
            problem = got["problem"]
        elif src.kind == "general_ledger":
            got = R.read_ledger(src, reader)
            d["gl"] += got["lines"]
            for k, v in got["opening"].items():
                d["gl_opening"][k] = d["gl_opening"].get(k, ZERO) + v
            problem = got["problem"]
        elif src.kind == "trial_balance":
            got = R.read_trial_balance(src, reader)
            d["tb"] += got["rows"]
            problem = got["problem"]
        elif src.kind == "journal_report":
            d["journals"] += R.read_journals(src, reader)["lines"]
        elif src.kind == "prior_wages":
            got = read_prior(src, reader)
            if not got.get("problem"):
                d["prior"] = got
            problem = got.get("problem", "")
        if problem:
            d["problems"].append({"text": f"{src.name} ({KINDS.get(src.kind, src.kind)}): {problem}", "source": src.sid,
                                  "evidence": "A structured export (Excel or CSV) of the same report."})
    return d


def execute(run_id: str, job_id: str, options: dict, pm, check=lambda: None) -> dict:
    started = time.time()

    def emit(stage, label, state="running", **counts):
        pm.send_event(run_id, {"type": "ai_precheck.progress", "job_id": job_id, "stage": stage, "state": state, "label": label, "counts": counts})

    job = pm.get_job(job_id)
    su = setup_from(options, job, EXTRA)
    reader = Reader(run_id, purpose="a New Zealand wages (PAYE) reconciliation", method=SKILL)
    emit("read", "Reading the payroll documents from Google Drive")
    try:
        sources = gather(options.get("drive_link", ""))
    except SourceProblem as exc:
        raise WpStop(str(exc)) from exc
    check()
    classify(sources, reader)
    emit("read", f"{len(sources)} documents found", "done", documents=len(sources))
    emit("checked", "Reading the IRD payroll summary, the EMP account, the ledger and the trial balance")
    data = read_all(sources, reader)
    check()
    emit("compared", "Reconciling payroll expense and payroll liabilities")
    result = Wages(su, data).run()
    emit("compared", result["status"], "done")
    check()
    facts = (f"Payroll expense: {result['expense_status']}, residual {result['residuals']['expense']}. Payroll liabilities: {result['liability_status']}, "
             f"residual {result['residuals']['liabilities']}.\n"
             + "\n".join(f"{ln['label']}: {ln.get('value')}" for ln in result["lines"] if not ln.get("heading"))
             + "\nExceptions: " + "; ".join(f"[{x['severity']}] {x['text']}" for x in result["exceptions"][:20]))
    summary = reader.summary(facts) or (f"{result['status']}. Payroll expense {result['expense_status'].lower()}; payroll liabilities "
                                        f"{result['liability_status'].lower()}.")
    result.update(summary=summary, sources=[x.brief() for x in sources],
                  settings={"Entity": su.entity, "IRD number": su.ird_number, "Financial year start": su.fy_start, "Balance date": su.balance_date,
                            "Software": su.software, "Currency": su.currency, "GL version": su.gl_version,
                            "First-year entity": "Yes" if su.first_year else "No", "Tolerance": su.tolerance,
                            **{k.replace("_", " ").capitalize(): v for k, v in su.extra.items()}})
    meta = {"run_id": run_id, "prep_date": su.prep_date, "versions": {"rules": RULES}}
    emit("verified", "Writing the workpaper")
    book = workbook(result, su, meta)
    from .. import memory
    from ..knowledge import Scope

    final = envelope(run_id, job_id, "wages", result, book, reader, started, sources, result["counts"], summary, result["status"], RULES)
    memory.safely(memory.remember_wp, Scope.of(job), "wp_wages", final["gst"])
    emit("verified", "Workpaper written", "done")
    return final
