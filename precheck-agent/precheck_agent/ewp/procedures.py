"""Each workpaper's procedure (AFIT electronic workpapers guidance, 16 Nov 2026): the figures it takes,
where they come from, the checks against the ledger and the exceptions. Code computes every figure;
nothing is entered without its source, and nothing is adjusted to make a workpaper balance."""
from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta
from decimal import Decimal

from ..gst.money import ZERO, q
from . import catalogue as C
from .readers import core_words

SEVERITY_ORDER = {"blocking": 0, "review": 1, "info": 2}
GST_FRACTION = Decimal(3) / Decimal(23)


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def _money(v) -> str:
    return f"{q(v):,.2f}" if v is not None else "-"


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def same_payer(a: str, b: str) -> bool:
    wa, wb = set(core_words(a)), set(core_words(b))
    return bool(wa and wb and (wa <= set(_norm(b).split()) or wb <= set(_norm(a).split())))


class Ewp:
    def __init__(self, su, data: dict, selected: list[str]):
        self.su, self.d = su, data
        self.selected = [k for k in C.KEYS if k in selected] or list(C.KEYS)
        self.fields: list[dict] = []
        self.checks: list[dict] = []
        self.flags: list[dict] = []
        self.journals: list[dict] = []
        self.bd, self.start = su.balance_date, su.fy_start
        self.gst = (su.extra.get("gst_status") or "We do GST") != "N/A"
        self.tolerance = su.tolerance if su.tolerance else Decimal("1")
        self.groups: dict[str, list[dict]] = {}
        self.unmapped: list[dict] = []
        for acc in data.get("accounts", []):
            g = acc.get("group", "")
            (self.groups.setdefault(g, []) if g else self.unmapped).append(acc)

    # --- helpers -------------------------------------------------------------------------------------
    def field(self, wp: str, sheet: str, cell: str, label: str, value, kind: str = "money", source: str = "", how: str = "ledger",
              status: str = "verified", note: str = "", editable: bool = True) -> dict:
        if isinstance(value, Decimal):
            value = q(value)
        f = {"id": _id(sheet, cell), "wp": wp, "sheet": sheet, "cell": cell, "label": label, "value": value, "agent_value": value, "kind": kind,
             "source": source, "how": how, "status": status, "note": note, "editable": editable}
        self.fields = [x for x in self.fields if x["id"] != f["id"]] + [f]
        return f

    def flag(self, wp: str, severity: str, text: str, evidence: str = "", amount_=None, code: str = "") -> None:
        self.flags.append({"id": _id(wp, code or text[:60]), "wp": wp, "code": code, "severity": severity, "text": text, "next_evidence": evidence,
                           "amount": q(amount_) if amount_ is not None else None})

    def check(self, wp: str, label: str, workpaper, ledger, note: str = "") -> dict:
        variance = None if workpaper is None or ledger is None else q(workpaper - ledger)
        status = "missing" if variance is None else ("agrees" if abs(variance) <= self.tolerance else "difference")
        c = {"wp": wp, "label": label, "workpaper": q(workpaper) if workpaper is not None else None, "ledger": q(ledger) if ledger is not None else None,
             "variance": variance, "status": status, "note": note}
        self.checks.append(c)
        return c

    def journal(self, wp: str, title: str, lines: list[tuple[str, str, Decimal, Decimal]], narration: str, why: str) -> None:
        self.journals.append({"id": _id("J", wp, title), "wp": wp, "title": title, "narration": narration, "why": why, "status": "proposed - not posted",
                              "lines": [{"account": a, "code": c, "debit": q(dr), "credit": q(cr)} for a, c, dr, cr in lines]})

    def accounts(self, *groups: str) -> list[dict]:
        return [a for g in groups for a in self.groups.get(g, [])]

    def total(self, *groups: str, key: str = "closing") -> Decimal | None:
        accs = self.accounts(*groups)
        if not accs:
            return None
        return sum(((a.get(key) or ZERO) for a in accs), ZERO)

    def gl_ref(self, accs: list[dict]) -> str:
        return "; ".join(f"GL {a['code']} {a['name']}".strip() for a in accs)

    def in_year(self, d: date | None) -> bool:
        return d is not None and self.start <= d <= self.bd

    def tax_account_name(self) -> tuple[str, str]:
        for acc in self.accounts("tax") + self.unmapped:
            if re.search(r"income tax|taxation|\brwt\b", acc["name"], re.I):
                return acc["name"], acc["code"]
        return "Income tax", ""

    # --- the workbench: who, when, what -----------------------------------------------------------------
    def workbench(self) -> None:
        su = self.su
        self.field("Workbench", "Workbench", "E8", "Client name", su.entity, "text", "Job settings", "setup")
        if su.extra.get("entity_type"):
            self.field("Workbench", "Workbench", "E10", "Entity type", su.extra["entity_type"], "text", "Job settings", "setup")
        if su.ird_number:
            self.field("Workbench", "Workbench", "Q10", "IRD number", su.ird_number, "text", "Job settings", "setup")
        if su.prepared_by:
            self.field("Workbench", "Workbench", "E18", "Prepared by", su.prepared_by, "text", "The person who ran the WP Agent", "setup")
        if su.extra.get("reviewed_by"):
            self.field("Workbench", "Workbench", "Q18", "Reviewed by", su.extra["reviewed_by"], "text", "Job settings", "setup")
        self.field("Workbench", "Workbench", "Q20", "Balance date", self.bd, "date", "Job settings", "setup")
        gl = self.d.get("gl_source")
        if gl and gl.get("entity") != "confirmed":
            self.flag("Workbench", "blocking", f"The general ledger ({gl['name']}) doesn't name {su.entity}.", "The ledger export of this entity.", code="gl_entity")

    # --- B1: review summary ------------------------------------------------------------------------------
    def b1(self) -> None:
        if not self.d.get("accounts"):
            self.flag("B1", "blocking", "No general ledger or trial balance of the entity was found, so no workpaper can be compared with the ledger.",
                      "The general ledger detail (or trial balance) for the year, exported from the accounting software.", code="no_gl")
            return
        src = (self.d.get("gl_source") or {}).get("name", "the ledger")
        banks = sorted(self.accounts("bank"), key=lambda a: a["code"])
        for row, acc in zip(C.B1_BANK_ROWS, banks):
            n = row - C.B1_BANK_ROWS[0] + 1
            self.field("B1", "B1", f"G{row}", f"Bank account # {n} - {acc['code']} {acc['name']}", acc["closing"], source=f"{src}: {self.gl_ref([acc])}")
            if acc.get("opening") is not None:
                self.field("B1", "B1", f"K{row}", f"Bank account # {n} - prior year", acc["opening"], source=f"{src}: opening balance")
        if len(banks) > len(C.B1_BANK_ROWS):
            self.flag("B1", "review", f"{len(banks)} bank accounts: B1 has rows for {len(C.B1_BANK_ROWS)}.", code="many_banks")
        sums: dict[str, list[dict]] = {}
        for g, accs in self.groups.items():
            if g == "bank":
                continue
            key = g
            if g in ("gst", "tax"):
                net = sum((a["closing"] or ZERO for a in accs), ZERO)
                key = f"{g}_asset" if net >= 0 else f"{g}_liability"
            sums.setdefault(key, []).extend(accs)
        for key, accs in sorted(sums.items(), key=lambda kv: C.B1.get(kv[0], 999)):
            row = C.B1.get(key)
            if row is None:
                continue
            closing = sum((a["closing"] or ZERO for a in accs), ZERO)
            self.field("B1", "B1", f"G{row}", C.B1_LABEL.get(key, key), closing, source=f"{src}: {self.gl_ref(accs)}")
            balance_sheet = any(a.get("type") in ("asset", "liability", "equity") for a in accs)
            if balance_sheet and all(a.get("opening") is not None for a in accs):
                opening = sum((a["opening"] or ZERO for a in accs), ZERO)
                self.field("B1", "B1", f"K{row}", f"{C.B1_LABEL.get(key, key)} - prior year", opening, source=f"{src}: opening balances")
            if key in ("gst_asset", "gst_liability"):
                self.flag("B1", "info", f"GST accounts net to {_money(closing)}; the GST reconciliation (L1) is the WP Agent's separate GST agent.",
                          code="gst_l1")
        for acc in self.unmapped:
            if acc["closing"]:
                self.flag("B1", "review", f"Account {acc['code']} {acc['name']} ({_money(acc['closing'])}) isn't taken to a workpaper: decide where "
                          "it belongs.", "The account's nature (and any journal clearing it).", acc["closing"], code=f"unmapped_{acc['code'] or acc['name']}")

    # --- F1.1: bank reconciliation -------------------------------------------------------------------------
    def f11(self) -> None:
        banks = sorted(self.accounts("bank"), key=lambda a: a["code"])
        if not banks:
            self.flag("F1.1", "blocking", "No bank account was found in the ledger.", "The general ledger with the bank account(s).", code="no_bank")
            return
        acc = banks[0]
        if len(banks) > 1:
            self.flag("F1.1", "review", f"{len(banks)} bank accounts: F1.1 is for {acc['code']} {acc['name']}; add F1.2 onwards in the workbook for "
                      + ", ".join(f"{b['code']} {b['name']}" for b in banks[1:]) + ".", code="more_banks")
        self.field("F1.1", "F1.1", "D10", "Bank account name", f"{acc['name']} ({acc['code']})", "text", self.gl_ref([acc]), "ledger")
        statement = next((s for s in self.d.get("bank_statements", []) if s.get("closing_date") == self.bd and s.get("closing_balance") is not None), None)
        rec = next((r for r in self.d.get("bank_recs", []) if r.get("date") == self.bd), None)
        closing, how, status, source = None, "", "", ""
        if statement:
            closing, how, status, source = statement["closing_balance"], "document", "extracted", statement["source"]
        elif rec and rec.get("statement_balance") is not None:
            closing, how, status, source = rec["statement_balance"], "document", "review", rec["source"]
            self.flag("F1.1", "review", f"The closing balance {_money(closing)} is the accounting software's expected bank statement balance (bank "
                      "reconciliation report), not the bank's own statement.", f"The bank statement at {self.bd:%d/%m/%Y}.", code="no_statement")
        else:
            self.flag("F1.1", "blocking", f"No bank statement (or bank reconciliation) at {self.bd:%d/%m/%Y} was found for {acc['name']}.",
                      f"The bank statement showing the balance at {self.bd:%d/%m/%Y}.", code="no_statement")
        self.field("F1.1", "F1.1", "H12", "Bank statement date", self.bd, "date", source or "Balance date", "setup" if not source else how,
                   status or "missing")
        if closing is not None:
            self.field("F1.1", "F1.1", "I12", "Closing balance per bank statement", closing, source=source, how=how, status=status)
        payments = (rec or {}).get("withdrawals", [])
        receipts = (rec or {}).get("deposits", [])
        for items, (first, last), what in ((payments, C.F11_PAYMENTS, "payment"), (receipts, C.F11_RECEIPTS, "receipt")):
            rows = list(range(first, last + 1))
            if len(items) > len(rows):
                self.flag("F1.1", "review", f"{len(items)} unprocessed {what}s: the workpaper has room for {len(rows)}; the rest are in one line.",
                          code=f"many_{what}s")
                rest = items[len(rows) - 1:]
                items = items[: len(rows) - 1] + [{"date": None, "reference": "", "description": f"{len(rest)} other {what}s",
                                                     "amount": sum((x["amount"] for x in rest), ZERO)}]
            for row, it in zip(rows, items):
                label = f"Unprocessed {what} {row - first + 1}"
                if it.get("date"):
                    self.field("F1.1", "F1.1", f"B{row}", f"{label} - date", it["date"], "date", rec["source"], "document", "extracted")
                self.field("F1.1", "F1.1", f"C{row}", f"{label} - reference", it.get("reference", ""), "text", rec["source"], "document", "extracted")
                self.field("F1.1", "F1.1", f"D{row}", f"{label} - description", it.get("description", ""), "text", rec["source"], "document", "extracted")
                self.field("F1.1", "F1.1", f"I{row}", f"{label} - amount", it["amount"], source=rec["source"], how="document", status="extracted")
        if closing is not None:
            wp = closing + sum((x["amount"] for x in receipts), ZERO) - sum((x["amount"] for x in payments), ZERO)
            c = self.check("F1.1", f"Bank {acc['code']}: statement +/- unprocessed items vs ledger", wp, acc["closing"])
            if c["status"] == "difference":
                self.flag("F1.1", "review", f"The bank reconciliation differs from the ledger by {_money(c['variance'])}.",
                          "The unprocessed items behind the difference.", c["variance"], code="bank_difference")

    # --- M1: accounts payable ------------------------------------------------------------------------------
    def m1(self) -> None:
        accs = self.accounts("payables")
        gl = self.total("payables")
        lists = self.d.get("creditors", [])
        if gl is None and not lists:
            self.flag("M1", "info", "No accounts payable account and no creditors list: M1 isn't needed.", code="na")
            return
        row = 26 if self.gst else 12
        if gl is not None:
            self.field("M1", "M1", f"I{row}", "Posted into the client's ledger (payable +)", -gl, source=self.gl_ref(accs))
            if gl > 0:
                self.flag("M1", "review", f"Accounts payable has a debit balance of {_money(gl)}: a payable can't be a debit - find what it is "
                          "(a prepayment, a duplicate payment or an old balance) and clear it.", "Supplier statements or the account's history.", gl,
                          code="ap_debit")
        listed = [r for lst in lists for r in lst.get("rows", [])]
        if any(lst.get("none_stated") for lst in lists) and not listed:
            lst = next(x for x in lists if x.get("none_stated"))
            self.field("M1", "M1", "B13", "Creditors note", f"No creditors at {self.bd:%d/%m/%Y} per {lst['name']}", "text", lst["source"], "document",
                       "extracted")
            if gl and abs(gl) > self.tolerance:
                self.flag("M1", "review", f"The creditors list shows none, but the ledger's accounts payable is {_money(gl)}.",
                          "What makes up the ledger balance.", gl, code="ap_vs_list")
        elif listed:
            total = sum((r["amount"] for r in listed), ZERO)
            if gl is not None:
                c = self.check("M1", "Creditors list vs ledger", -total, gl)
                if c["status"] == "difference":
                    self.flag("M1", "review", f"The creditors list totals {_money(total)}; the ledger shows {_money(-gl)} payable. Creditors not in the "
                              "ledger go in M1's lines below the posted amount (a journal follows).", "Supplier statements for the difference.",
                              c["variance"], code="ap_difference")
        elif gl:
            self.flag("M1", "review", f"No creditors list or supplier statements: the ledger's {_money(-gl)} payable isn't supported.",
                      f"The aged payables at {self.bd:%d/%m/%Y} (or supplier statements).", code="no_list")
        if gl is not None:
            self.check("M1", "Accounts payable per workpaper vs ledger", gl, gl, "posted amount as per ledger")

    # --- T2: investment income -----------------------------------------------------------------------------
    def t2(self) -> None:
        summary = self.d.get("income_summary", [])
        interest = [dict(x, status="extracted") for s in summary for x in s.get("interest", []) if self.in_year(x.get("date")) or x.get("date") is None]
        dividends = [dict(x, status="extracted") for s in summary for x in s.get("dividends", []) if self.in_year(x.get("date")) or x.get("date") is None]
        for st in self.d.get("interest_statements", []):
            hit = next((x for x in interest if same_payer(x["payer"], st["payer"]) and st.get("gross") is not None
                        and abs(x["gross"] - st["gross"]) <= Decimal("0.01")), None)
            if hit:
                hit["status"], hit["source"] = "verified", f"{hit['source']}; agrees with {st['source']}"
            elif st.get("gross") is not None:
                interest.append({**st, "status": "review"})
                self.flag("T2", "review", f"Interest from {st['payer']} ({_money(st['gross'])}) isn't in IRD's income summary.",
                          "IRD's income summary or the payer's RWT certificate.", st["gross"], code=f"int_{st['payer']}")
        for st in self.d.get("dividends_received", []):
            hit = next((x for x in dividends if same_payer(x["payer"], st["payer"]) and st.get("gross") is not None
                        and abs(x["gross"] - st["gross"]) <= Decimal("0.01")), None)
            if hit:
                hit["status"] = "verified"
                hit["source"] = f"{hit['source']}; agrees with {st['source']}"
            elif st.get("gross") is not None and not any(same_payer(x["payer"], st["payer"]) and x.get("statement_of") == st["source"] for x in dividends):
                if any(x.get("source") == st["source"] for x in dividends):
                    continue
                dividends.append({**st, "tax": st.get("rwt"), "status": "review", "statement_of": st["source"]})
                self.flag("T2", "review", f"A dividend from {st['payer']} ({_money(st['gross'])}) isn't in IRD's income summary.",
                          "IRD's income summary or the company's dividend statement.", st["gross"], code=f"div_{st['payer']}_{st['gross']}")
        if not summary:
            self.flag("T2", "review" if (interest or dividends) else "info", "IRD's income summary for the year wasn't found: interest and dividends "
                      "can't be checked against what IRD holds.", "The myIR income summary for the year.", code="no_summary")
        for items, (first, last), what in ((interest, C.T2_INTEREST, "interest"), (dividends, C.T2_DIVIDENDS, "dividend")):
            rows = list(range(first, last + 1))
            if len(items) > len(rows):
                self.flag("T2", "review", f"{len(items)} {what} lines: the workpaper has room for {len(rows)}.", code=f"many_{what}")
            for row, x in zip(rows, sorted(items, key=lambda x: (x.get("date") or self.bd, x["payer"]))):
                n = row - first + 1
                if x.get("date"):
                    self.field("T2", "T2", f"B{row}", f"{what.title()} {n} - date", x["date"], "date", x["source"], "document", x["status"])
                self.field("T2", "T2", f"C{row}", f"{what.title()} {n} - payer", x["payer"], "text", x["source"], "document", x["status"])
                self.field("T2", "T2", f"G{row}", f"{what.title()} {n} - gross", x["gross"], source=x["source"], how="document", status=x["status"])
                self.field("T2", "T2", f"H{row}", f"{what.title()} {n} - RWT", x.get("tax") or ZERO, source=x["source"], how="document", status=x["status"])
                if what == "dividend":
                    self.field("T2", "T2", f"I{row}", f"Dividend {n} - imputation credits", x.get("imputation") or ZERO, source=x["source"], how="document",
                               status=x["status"])
        if interest:
            self.field("T2", "T2", "G9", "NZ interest (tick)", "R", "text", "Interest found", "calculated", "verified", editable=False)
        if dividends:
            self.field("T2", "T2", "G10", "NZ dividends (tick)", "R", "text", "Dividends found", "calculated", "verified", editable=False)
        tax_name, tax_code = self.tax_account_name()
        for items, group, what in ((interest, "interest_income", "interest"), (dividends, "dividend_income", "dividends")):
            if not items:
                continue
            gross = sum((x["gross"] for x in items), ZERO)
            credits = sum(((x.get("tax") or ZERO) + (x.get("imputation") or ZERO) for x in items), ZERO)
            gl = self.total(group)
            c = self.check("T2", f"{what.title()} received (gross) vs ledger", -gross, gl)
            if c["status"] == "difference":
                diff = -(c["variance"])
                if abs(diff - credits) <= self.tolerance and credits:
                    accs = self.accounts(group)
                    income = accs[0] if accs else {"name": what.title() + " income", "code": ""}
                    self.journal("T2", f"Gross up {what} for tax deducted", [(tax_name, tax_code, credits, ZERO), (income["name"], income["code"], ZERO, credits)],
                                 f"Gross up {what} for RWT and imputation credits per IRD", f"The ledger has {what} net of {_money(credits)} tax credits.")
                    self.flag("T2", "review", f"The ledger records {what} net of tax credits ({_money(credits)}): a journal grossing it up is proposed (D1).",
                              code=f"gross_{what}")
                else:
                    self.flag("T2", "review", f"{what.title()} per the workpaper ({_money(gross)}) differs from the ledger ({_money(-(gl or ZERO))}) by "
                              f"{_money(c['variance'])}.", "The income not in the ledger, or not in IRD's records.", c["variance"], code=f"diff_{what}")

    # --- Q1: taxation due ----------------------------------------------------------------------------------
    def _ird(self, period: date) -> list[dict]:
        return [x for x in self.d.get("tax_transactions", []) if x.get("period_end") == period]

    def q1(self) -> None:
        comp = self.d.get("tax_computation")
        if comp and comp.get("tax_payable") is not None:
            self.field("Q1", "Q1", "I9", "Tax payable on current year taxable profit", comp["tax_payable"], source=comp["source"], how="document",
                       status="extracted")
        else:
            self.flag("Q1", "blocking", "The tax payable on this year's taxable profit isn't known: there's no tax computation.",
                      f"The income tax computation for the year ended {self.bd:%d/%m/%Y}.", code="no_tax_comp")
        periods = {x.get("period_end") for x in self.d.get("tax_transactions", [])}
        have_current = self.bd in periods or any(s.get("period_end") == self.bd for s in self.d.get("tax_docs", []))
        current = self._ird(self.bd)
        payments = sorted((x for x in current if x["category"] in ("payment", "transfer") and x["amount"] < 0 and x["effective"] <= self.bd + timedelta(days=60)),
                          key=lambda x: x["effective"])
        if not have_current:
            self.flag("Q1", "blocking", f"IRD's income tax transactions for the year ended {self.bd:%d/%m/%Y} weren't found: provisional tax paid can't "
                      "be confirmed.", f"myIR income tax transactions for the period ending {self.bd:%d/%m/%Y}.", code="no_ird_current")
        for row, x in zip((29, 30, 31), payments[:3]):
            self.field("Q1", "Q1", f"I{row}", f"Provisional tax instalment {row - 28} ({x['effective']:%d/%m/%Y})", -x["amount"], source=x["source"],
                       how="document", status="extracted")
        for row, x in zip(range(C.Q1_OTHER_PAYMENTS[0], C.Q1_OTHER_PAYMENTS[1] + 1), payments[3:]):
            self.field("Q1", "Q1", f"B{row}", "Other payment - date", x["effective"], "date", x["source"], "document", "extracted")
            self.field("Q1", "Q1", f"C{row}", "Other payment - description", x["type"] or "Payment", "text", x["source"], "document", "extracted")
            self.field("Q1", "Q1", f"I{row}", "Other payment - amount", -x["amount"], source=x["source"], how="document", status="extracted")
        # Payments the ledger shows for this year's income tax that IRD doesn't.
        tag = self.bd.strftime("%d%m%Y")
        gl_pay = [ln for a in self.d.get("accounts", []) if a.get("group") == "bank" for ln in a["lines"]
                  if re.search(rf"\bINC\s*{tag}\b", ln["description"], re.I) and ln["credit"] > 0]
        ird_total = sum((-x["amount"] for x in payments), ZERO)
        for ln in gl_pay:
            if not any(abs(-x["amount"] - ln["credit"]) <= Decimal("0.01") for x in payments):
                self.flag("Q1", "review", f"The ledger shows {_money(ln['credit'])} paid to IRD on {ln['date']:%d/%m/%Y} for income tax {self.bd:%Y} "
                          f"(\"{ln['description'][:60]}\"), but IRD's {self.bd:%Y} account doesn't show it" + (" (IRD shows no activity)" if not current else "")
                          + ": it may have been transferred to another account or year.", "IRD's record of where the payment went.", ln["credit"],
                          code=f"gl_pay_{ln['date']}")
        if gl_pay or ird_total:
            self.check("Q1", "Provisional tax paid: IRD vs ledger", ird_total, sum((ln["credit"] for ln in gl_pay), ZERO))
        # Prior years: what IRD shows as still owed (or due back) at the balance date.
        arrears_rows = iter(range(C.Q1_PRIOR_ARREARS[0], C.Q1_PRIOR_ARREARS[1] + 1))
        refund_rows = iter(range(C.Q1_REFUNDS[0], C.Q1_REFUNDS[1] + 1))
        for period in sorted(p for p in periods if p and p < self.bd):
            lines = [x for x in self._ird(period) if x["category"] not in ("interest", "penalty") and x["effective"] <= self.bd]
            if not lines:
                continue
            balance = sum((x["amount"] for x in lines), ZERO)
            src = lines[0]["source"].split(",")[0]
            if balance > self.tolerance:
                row = next(arrears_rows, None)
                if row:
                    self.field("Q1", "Q1", f"B{row}", "Prior year arrears - description", f"Income tax {period:%Y} unpaid at {self.bd:%d/%m/%Y}", "text", src,
                               "document", "extracted")
                    self.field("Q1", "Q1", f"I{row}", "Prior year arrears - amount", balance, source=src, how="document", status="extracted")
            elif balance < -self.tolerance:
                row = next(refund_rows, None)
                if row:
                    self.field("Q1", "Q1", f"B{row}", "Refund not received - description", f"Income tax {period:%Y} refund due at {self.bd:%d/%m/%Y}",
                               "text", src, "document", "extracted")
                    self.field("Q1", "Q1", f"I{row}", "Refund not received - amount", -balance, source=src, how="document", status="extracted")

    # --- Q3a: imputation credit account --------------------------------------------------------------------
    def q3a(self) -> None:
        prior_bd = date(self.bd.year - 1, self.bd.month, min(self.bd.day, 28 if self.bd.month == 2 else self.bd.day))
        ica = next((x for x in self.d.get("ica", []) if x.get("period_end") == prior_bd), None) or next(
            (x for x in self.d.get("ica", []) if x.get("period_end") and x["period_end"] < self.bd), None)
        opening = None
        if ica and ica.get("ica_closing") is not None:
            opening = -ica["ica_closing"]  # myIR shows a credit balance (credits in the company's favour) as negative
            self.field("Q3a", "Q3a", "I10", "Opening ICA balance (credit +)", opening, source=ica["source"], how="document", status="extracted",
                       note=f"IRD shows {_money(ica['ica_closing'])} at {ica['period_end']:%d/%m/%Y}")
            if opening < 0:
                self.flag("Q3a", "review", f"The ICA opened in debit ({_money(opening)}): further income tax and an imputation penalty may be due.",
                          code="debit_opening")
        else:
            self.flag("Q3a", "blocking", "The opening ICA balance wasn't found (last year's closing).",
                      f"myIR's ICA closing balance at {prior_bd:%d/%m/%Y} or last year's ICA return/workpaper.", code="no_opening")
        terminal, refunds = [], []
        for x in self.d.get("tax_transactions", []):
            if not x.get("period_end") or x["period_end"] >= self.bd or not self.in_year(x["effective"]):
                continue
            if x["category"] in ("payment", "transfer") and x["amount"] < 0:
                terminal.append(x)
            elif x["category"] == "refund":
                refunds.append(x)
        for row, x in zip(range(C.Q3A_TERMINAL[0], C.Q3A_TERMINAL[1] + 1), sorted(terminal, key=lambda x: x["effective"])):
            self.field("Q3a", "Q3a", f"C{row}", f"Terminal tax payment ({x['period_end']:%Y}) - date", x["effective"], "date", x["source"], "document",
                       "extracted")
            self.field("Q3a", "Q3a", f"H{row}", f"Terminal tax payment ({x['period_end']:%Y}) - amount", -x["amount"], source=x["source"], how="document",
                       status="extracted")
        for row, x in zip(range(C.Q3A_REFUNDS[0], C.Q3A_REFUNDS[1] + 1), refunds):
            self.field("Q3a", "Q3a", f"C{row}", "Income tax refund - date", x["effective"], "date", x["source"], "document", "extracted")
            self.field("Q3a", "Q3a", f"H{row}", "Income tax refund - amount", abs(x["amount"]), source=x["source"], how="document", status="extracted")
        paid = [x for x in self.d.get("dividends_paid", []) if self.in_year(x.get("date"))]
        for row, x in zip(range(C.Q3A_DIVIDENDS[0], C.Q3A_DIVIDENDS[1] + 1), paid):
            self.field("Q3a", "Q3a", f"C{row}", "Dividend paid - date", x["date"], "date", x["source"], "document", "extracted")
            self.field("Q3a", "Q3a", f"D{row}", "Dividend paid - description", f"Imputation credits attached to dividend paid {x['date']:%d/%m/%Y}", "text",
                       x["source"], "document", "extracted")
            self.field("Q3a", "Q3a", f"H{row}", "Imputation credits attached", x.get("imputation") or ZERO, source=x["source"], how="document",
                       status="extracted")
            net = x.get("net")
            if net and x.get("imputation") and x["imputation"] / net > Decimal(28) / Decimal(72) + Decimal("0.0001"):
                self.flag("Q3a", "review", f"The dividend of {x['date']:%d/%m/%Y} carries imputation credits above the 28/72 maximum ratio.",
                          code=f"ratio_{x['date']}")
            if x.get("rwt"):
                self.flag("Q3a", "info", f"RWT of {_money(x['rwt'])} was deducted from the dividend paid on {x['date']:%d/%m/%Y}: it is paid to IRD with "
                          "the RWT return and isn't an ICA credit.", code=f"div_rwt_{x['date']}")
        if len(paid) > 2:
            self.flag("Q3a", "review", f"{len(paid)} dividends paid: the workpaper has room for 2.", code="many_dividends")
        if opening is not None:
            t2_credits = sum(((x.get("tax") or ZERO) + (x.get("imputation") or ZERO) for s in self.d.get("income_summary", [])
                              for x in s.get("interest", []) + s.get("dividends", []) if self.in_year(x.get("date")) or x.get("date") is None), ZERO)
            prov = sum((-x["amount"] for x in self._ird(self.bd) if x["category"] in ("payment", "transfer") and x["amount"] < 0
                        and self.in_year(x["effective"])), ZERO)
            closing = (opening + prov + sum((-x["amount"] for x in terminal), ZERO) + t2_credits - sum((abs(x["amount"]) for x in refunds), ZERO)
                       - sum((x.get("imputation") or ZERO for x in paid), ZERO))
            self.checks.append({"wp": "Q3a", "label": "ICA closing balance (computed, credit +)", "workpaper": q(closing), "ledger": None, "variance": None,
                                "status": "computed", "note": "opening + tax paid + RWT and imputation credits received - refunds - credits attached"})
            if closing < 0:
                self.flag("Q3a", "review", f"The ICA closes in debit ({_money(closing)}) at {self.bd:%d/%m/%Y}.", code="debit_closing")

    # --- S2: income ----------------------------------------------------------------------------------------
    def s2(self) -> None:
        ar = self.accounts("receivables")
        if ar:
            self.field("S2", "S2", "G31", "Closing accounts receivable", self.total("receivables"), source=self.gl_ref(ar))
            if all(a.get("opening") is not None for a in ar):
                self.field("S2", "S2", "G32", "Opening accounts receivable", self.total("receivables", key="opening"), source=self.gl_ref(ar))
        sales = self.accounts("sales")
        if sales:
            self.field("S2", "S2", "H46", "Net income per ledger", -(self.total("sales") or ZERO), source=self.gl_ref(sales))
        else:
            self.flag("S2", "info", "No sales or fee income account in the ledger.", code="no_sales")
        self.flag("S2", "info", "S2 takes the GST returns' income from L1, which the GST agent prepares separately: until L1 is filled, S2's "
                  "discrepancy isn't meaningful.", code="needs_l1")

    # --- V1: expenses --------------------------------------------------------------------------------------
    def v1(self) -> None:
        used = []
        for group, (title, first, last, dcol, acol, basis) in C.V1_SECTIONS.items():
            accs = self.accounts(group)
            if not accs:
                continue
            used.append(group)
            rows = list(range(first, last + 1))
            entries = [(a, a["closing"] + (sum((ln["tax"] for ln in a["lines"]), ZERO) if basis == "gross" and self.gst else ZERO)) for a in accs]
            if len(entries) > len(rows):
                keep, rest = entries[: len(rows) - 1], entries[len(rows) - 1:]
                entries = keep + [({"code": "", "name": f"{len(rest)} other accounts", "lines": []}, sum((v for _, v in rest), ZERO))]
            for row, (a, value) in zip(rows, entries):
                self.field("V1", "V1", f"B{row}", f"{title} - code", a["code"], "text", self.gl_ref([a]) if a.get("code") else "", "ledger")
                self.field("V1", "V1", f"{dcol}{row}", f"{title} - description", a["name"], "text", self.gl_ref([a]) if a.get("code") else "", "ledger")
                self.field("V1", "V1", f"{acol}{row}", f"{title} - {'gross (incl GST)' if basis == 'gross' and self.gst else 'amount'}", value,
                           source=self.gl_ref([a]) if a.get("code") else "Ledger", how="ledger" if basis != "gross" else "calculated",
                           note="ledger amount plus the GST on its lines" if basis == "gross" and self.gst else "")
            gl = self.total(group)
            wp = sum((v for _, v in entries), ZERO)
            if basis == "gross" and self.gst:
                wp = sum(((a["closing"]) for a in accs), ZERO)  # the workpaper takes the GST back off
            self.check("V1", f"{title} vs ledger", wp, gl)
            self._expense_flags(group, title, accs)
        ent = self.accounts("entertainment")
        if ent:
            used.append("entertainment")
            gross = sum((a["closing"] + (sum((ln["tax"] for ln in a["lines"]), ZERO) if self.gst else ZERO) for a in ent), ZERO)
            self.field("V1", "V1", C.V1_ENTERTAINMENT[0], "Entertainment - total per GL requiring adjustment (incl GST)", gross, source=self.gl_ref(ent),
                       how="calculated", note="ledger amount plus the GST on its lines")
            self.field("V1", "V1", C.V1_ENTERTAINMENT[1], "Entertainment - GST inclusive?", "Yes" if self.gst else "No", "text", "GST status", "setup")
            self.flag("V1", "review", f"Entertainment of {_money(self.total('entertainment'))} (excl GST): 50% of food and drink is non-deductible; "
                      "check what is fully deductible (V1 line 'less fully deductible') and that none of it is private.",
                      "The entertainment transactions' nature.", self.total("entertainment"), code="entertainment")
        for group in used:
            tick = C.V1_TICKS.get("interest" if group.startswith("interest") else group)
            if tick:
                self.field("V1", "V1", tick, f"{group.replace('_', ' ').title()} (tick)", "R", "text", "Section used", "calculated", editable=False)
        if not used:
            self.flag("V1", "info", "No expense accounts were found in the ledger.", code="none")

    def _expense_flags(self, group: str, title: str, accs: list[dict]) -> None:
        for a in accs:
            for ln in a["lines"]:
                value = ln["debit"] - ln["credit"]
                if group == "repairs" and value >= Decimal("1000"):
                    self.flag("V1", "review", f"{title}: {_money(value)} on {ln['date']:%d/%m/%Y} (\"{ln['description'][:50]}\") may be capital "
                              "expenditure.", "The invoice.", value, code=f"capital_{ln['source']}")
                if re.search(r"fine|penalt|donation|gym|clothing|personal|private|grocer|supermarket|new world|countdown|woolworths", ln["description"],
                             re.I):
                    self.flag("V1", "review", f"{title}: {_money(value)} on {ln['date']:%d/%m/%Y} (\"{ln['description'][:50]}\") may be private or "
                              "non-deductible.", "The invoice and its business purpose.", value, code=f"private_{ln['source']}")
        if group == "vehicles":
            self.flag("V1", "review", f"Vehicle expenses of {_money(self.total(group))}: the business-use percentage needs a logbook (V1 vehicles).",
                      "The vehicle logbook.", code="logbook")

    # --- V2: use of home -----------------------------------------------------------------------------------
    def v2(self) -> None:
        gl = self.accounts("home_office")
        if not self.d.get("home_office_docs"):
            self.flag("V2", "review" if gl else "info", "No home-office evidence (house and office floor areas, household costs, the method chosen) was "
                      "found, so V2 isn't filled in." + (f" The ledger holds {_money(self.total('home_office'))}." if gl else ""),
                      "Floor areas (m²), the year's household costs and the method to use.", self.total("home_office"), code="no_evidence")
        else:
            self.flag("V2", "review", "Home-office documents were found: enter the floor areas and costs on V2 from them (they vary too much in form "
                      "to be read reliably).", code="enter_by_hand")

    # --- V5: accounting fees -------------------------------------------------------------------------------
    def v5(self) -> None:
        invoices = [x for st in self.d.get("fee_statements", []) for x in st["invoices"] if self.in_year(x.get("date"))]
        gl = self.total("accounting_fees")
        if not invoices:
            self.flag("V5", "review" if gl else "info", "No fee statement or invoices to the entity for the year were found.",
                      "The firm's debtor statement for the client for the year.", code="no_statement")
            return
        total = sum((x["amount"] for x in invoices), ZERO)
        src = "; ".join(sorted({x["source"] for x in invoices}))
        self.field("V5", "V5", "D12", "Annual accounting fees per our debtors system (incl GST)", total, source=src, how="document", status="extracted",
                   note=", ".join(f"{x.get('reference') or 'invoice'} {x['date']:%d/%m/%y} {_money(x['amount'])}" for x in invoices))
        net = total - (q(total * GST_FRACTION) if self.gst else ZERO)
        if gl is not None:
            c = self.check("V5", "Net fees charged vs accounting fees in the ledger", net, gl)
            if c["status"] == "difference":
                self.flag("V5", "review", f"Fees billed for the year ({_money(net)} excl GST) differ from the ledger's accounting fees ({_money(gl)}) by "
                          f"{_money(c['variance'])}: fees billed after balance date, accruals or other charges explain it.",
                          "Invoices around the balance date.", c["variance"], code="difference")

    # --- D1: proposed journals -----------------------------------------------------------------------------
    def d1(self) -> None:
        rows = list(range(C.D1_ROWS[0], C.D1_ROWS[1] + 1))
        i = 0
        for j in self.journals:
            need = len(j["lines"])
            if i + need > len(rows):
                self.flag("D1", "review", f"No room on D1 for the journal '{j['title']}'.", code=f"room_{j['id']}")
                continue
            for n, ln in enumerate(j["lines"]):
                row = rows[i + n]
                self.field("D1", "D1", f"B{row}", f"{j['title']} - date", self.bd, "date", f"Proposed by {j['wp']}", "calculated", "review")
                self.field("D1", "D1", f"C{row}", f"{j['title']} - account", ln["account"], "text", f"Proposed by {j['wp']}", "calculated", "review")
                if ln["code"]:
                    self.field("D1", "D1", f"H{row}", f"{j['title']} - code", ln["code"], "text", f"Proposed by {j['wp']}", "calculated", "review")
                if ln["debit"]:
                    self.field("D1", "D1", f"J{row}", f"{j['title']} - debit", ln["debit"], source=f"Proposed by {j['wp']}", how="calculated", status="review")
                if ln["credit"]:
                    self.field("D1", "D1", f"K{row}", f"{j['title']} - credit", ln["credit"], source=f"Proposed by {j['wp']}", how="calculated", status="review")
                if n == 0:
                    self.field("D1", "D1", f"L{row}", f"{j['title']} - narration", j["narration"], "text", f"Proposed by {j['wp']}", "calculated", "review")
            i += need + 1
        if self.journals:
            self.flag("D1", "info", f"{len(self.journals)} proposed journal(s) on D1: not posted - the accountant decides.", code="proposed")

    # --- the run -------------------------------------------------------------------------------------------
    def run(self) -> dict:
        self.workbench()
        order = ["B1", "F1.1", "M1", "T2", "Q1", "Q3a", "S2", "V1", "V2", "V5", "D1"]
        steps = {"B1": self.b1, "F1.1": self.f11, "M1": self.m1, "T2": self.t2, "Q1": self.q1, "Q3a": self.q3a, "S2": self.s2, "V1": self.v1,
                 "V2": self.v2, "V5": self.v5, "D1": self.d1}
        for key in order:
            if key in self.selected:
                steps[key]()
        flags = sorted({f["id"]: f for f in self.flags}.values(), key=lambda f: (SEVERITY_ORDER[f["severity"]], f["wp"]))
        workpapers = []
        for key, title, purpose in [("Workbench", "Workbench", "Client and job details")] + C.WORKPAPERS:
            if key != "Workbench" and key not in self.selected:
                continue
            mine = [f for f in flags if f["wp"] == key]
            checks = [c for c in self.checks if c["wp"] == key]
            fields = [f for f in self.fields if f["wp"] == key]
            if any(f["severity"] == "blocking" for f in mine):
                status = "Incomplete evidence"
            elif any(c["status"] == "difference" for c in checks) or any(f["severity"] == "review" for f in mine):
                status = "Prepared - review"
            elif not fields:
                status = "Nothing to enter"
            else:
                status = "Prepared"
            workpapers.append({"key": key, "title": title, "purpose": purpose, "status": status, "fields": len(fields), "checks": checks,
                               "exceptions": [f["id"] for f in mine]})
        counts = {s: sum(1 for f in flags if f["severity"] == s) for s in ("blocking", "review", "info")}
        order_status = ["Incomplete evidence", "Prepared - review", "Prepared", "Nothing to enter"]
        overall = min((w["status"] for w in workpapers if w["key"] != "Workbench"), key=order_status.index, default="Prepared")
        lines = [{"label": f"{f['wp']} {f['label']}", "value": f["value"], "note": f.get("source", "")} for f in self.fields if f["kind"] in ("money", "number")]
        lines += [{"label": f"{c['wp']} check: {c['label']}", "value": c["variance"] if c["variance"] is not None else c["workpaper"],
                   "note": f"workpaper {c['workpaper']}, ledger {c['ledger']}, {c['status']}"} for c in self.checks]
        conclusions = [{"label": f"{w['key']} {w['title']}", "status": w["status"],
                        "residual": next((c["variance"] for c in w["checks"] if c["variance"] is not None), None)} for w in workpapers]
        return {"agent": "ewp", "status": overall, "workpapers": workpapers, "fields": self.fields, "checks": self.checks, "exceptions": flags,
                "journals": self.journals, "counts": counts, "lines": lines, "conclusions": conclusions, "selected": self.selected,
                "corrections": [{"id": j["id"], "title": j["title"], "lines": j["lines"], "explanation": j["why"], "status": j["status"]} for j in self.journals]}
