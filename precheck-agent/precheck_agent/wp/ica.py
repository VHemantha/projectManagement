"""The imputation (ICA) reconciliation agent (AFIT, specification working draft 1.0, 7 Nov 2026), in the
layout of AFIT's own workpaper (the two screens supplied on 10 Nov 2026):

A  Imputation Credits - the ICA movement statement: opening + credits (income tax paid, FDP paid
   (legacy), RWT on interest received, imputation & FDP credits attached to dividends received, other)
   - debits (income tax refunded, FDP refunds (legacy), imputation credits attached to dividends paid,
   other) = closing. The actual memorandum balance; adjustments in B never change it.
B  Reconcile Closing Imputation Cr Balance to RE - closing ICA + end-of-year terminal tax still to
   pay/refund + Prov 3 tax still to pay/refund + other adjustments = balance; grossed up at 72/28
   (exact; the ratio shows as 0.3889); against retained profit + permanent and timing tax differences
   + the 33% and 30% retained-earnings differentials = tax-paid retained profit; difference; missing
   credits = difference x 28/72.

Tax payments come from IRD's income tax transaction summary (principal only: use-of-money interest
and penalties never create ICA credits); RWT and credits on income received from IRD's company
income summary (else the ledger); terminal tax, permanent and timing differences from the tax
computation and last year's workpaper, or the accountant's settings. Nothing is forced to agree:
a difference stays visible with the evidence still needed.
"""
import io
import logging
import re
import time
from decimal import Decimal

from openpyxl import Workbook

from ..gst import ai as A
from ..gst import readers as R
from ..gst import workbook as W
from ..gst.ai import Reader
from ..gst.money import ZERO, amount, q
from ..gst.sources import SourceProblem, gather
from . import sheets as S
from .base import BANK, Flags, WpStop, _id, conclude, envelope, read_myir, setup_from, tb_matching

logger = logging.getLogger(__name__)
RULES = "ica-1.0"
SKILL = "nz-imputation-reconciliation"
RATIO = Decimal(28) / Decimal(72)  # shown as 0.3889; never rounded in a calculation
GROSS_UP = Decimal(72) / Decimal(28)
EXTRA = ("opening_ica", "terminal_tax", "prov3_tax", "retained_earnings", "permanent_differences", "timing_differences", "ic33", "ic30",
         "other_adjustments")

KINDS = {
    "prior_ica": "Prior-year ICA return / statement or ICA-to-retained-earnings workpaper",
    "ica_return": "This year's ICA return (IR4J) or statement, if prepared",
    "ird_income_tax": "IRD income tax transaction summary",
    "income_summary": "IRD company income summary (interest, dividends, RWT, imputation credits)",
    "tax_computation": "Tax computation / IR4 return (draft or filed)",
    "dividends": "Dividend statements, resolutions, distributions",
    "financial_statements": "Financial statements",
    "trial_balance": "Trial balance (year end)",
    "general_ledger": "General ledger (full year)",
    "other": "Other / not used",
}
_RULES = [
    ("prior_ica", r"((prior|previous|last)\s*(year|yr)|\bpy\b).*(imputation|\bica\b|ir4j|retained)|(imputation|\bica\b|ir4j).*((prior|previous|last)\s*(year|yr)|\bpy\b)"),
    ("ica_return", r"imputation|\bica\b|ir4j"),
    ("ird_income_tax", r"(income\s*tax|\binc\b|\bitn\b).*transaction|transaction\s*summary"),
    ("income_summary", r"income\s*summary|company\s*income|interest.*dividend.*summary|\brwt\b.*summary"),
    ("tax_computation", r"tax\s*comp|\bir4\b|tax\s*return|computation"),
    ("dividends", r"dividend|distribution|resolution"),
    ("financial_statements", r"financial\s*statements|annual\s*report|\bfs\b"),
    ("trial_balance", r"trial\s*balance|\btb\b"),
    ("general_ledger", r"general\s*ledger|ledger\s*detail|\bgl\b"),
]
S_ = A._STR
A.SCHEMAS["prior_ica"] = A._obj({"tax_year_end": S_, "opening_balance": S_, "closing_balance": S_, "retained_earnings": S_, "permanent_differences": S_,
                                  "timing_differences": S_, "ic33_remaining": S_, "ic30_remaining": S_, "source": S_})
A.ASK["prior_ica"] = ("Read last year's ICA return / imputation workpaper: its closing ICA balance (a debit balance as negative), and if shown the "
                      "cumulative permanent and timing tax differences, retained earnings, and the remaining 33% and 30% imputation credits.")
A.SCHEMAS["ica_return"] = A.SCHEMAS["prior_ica"]
A.ASK["ica_return"] = A.ASK["prior_ica"].replace("last year's", "this year's")
A.SCHEMAS["income_summary"] = A._obj({"items": A._list({"payer": S_, "kind": {"type": "string", "enum": ["interest", "dividend", "other"]}, "gross": S_,
                                                         "rwt": S_, "imputation_credits": S_, "source": S_})})
A.ASK["income_summary"] = ("Read IRD's company income summary: one record per payer and income type (interest or dividend), with the gross amount, "
                           "RWT deducted and imputation credits attached, as shown.")
A.SCHEMAS["tax_computation"] = A._obj({"tax_year_end": S_, "taxable_income": S_, "tax_payable": S_, "terminal_tax": S_, "provisional_paid": S_,
                                        "prov3_outstanding": S_, "non_deductible_expenses": S_, "non_taxable_income": S_, "timing_differences": S_,
                                        "source": S_})
A.ASK["tax_computation"] = ("Read the tax computation / IR4: taxable income, tax payable, terminal tax still to pay (a refund as negative), provisional "
                            "tax paid, any provisional instalment still outstanding, non-deductible expenses added back, non-taxable income deducted, "
                            "and timing differences.")
A.SCHEMAS["dividends"] = A._obj({"received": A._list({"payer": S_, "date": S_, "cash": S_, "rwt": S_, "imputation_credits": S_, "source": S_}),
                                  "paid": A._list({"date": S_, "amount": S_, "imputation_credits": S_, "source": S_})})
A.ASK["dividends"] = ("List dividends received (payer, date, cash amount before RWT, RWT, imputation credits) and dividends paid or credited by the "
                      "company (date, amount, imputation credits attached).")
A.SCHEMAS["financial_statements"] = A._obj({"retained_earnings_closing": S_, "profit_after_tax": S_, "dividends_paid": S_, "income_tax_payable": S_,
                                             "source": S_})
A.ASK["financial_statements"] = ("Read the financial statements: closing retained earnings, profit after tax for the year, dividends paid, and income "
                                 "tax payable (a refund due as negative).")

RE_ACCOUNT = re.compile(r"retained\s*(earnings|profits?)|accumulated\s*(profits?|losses?|earnings)", re.I)
TAX_ACCOUNT = re.compile(r"income\s*tax|tax\s*(payable|provision|refund|receivable)|provision\s*for\s*(income\s*)?tax|taxation|terminal\s*tax", re.I)
NOT_TAX = re.compile(r"\bgst\b|\bpaye\b|deferred|\brwt\b.*payable|withholding\s*tax\s*payable|fbt|expense", re.I)
RWT_ACCOUNT = re.compile(r"\brwt\b|resident\s*withholding|withholding\s*tax", re.I)
IMP_ACCOUNT = re.compile(r"imputation\s*credit", re.I)
PNL_TYPES = re.compile(r"revenue|income|sales|expense|direct\s*cost|overhead|depreciation|cost\s*of\s*sales", re.I)
FDP = re.compile(r"\bfdp\b|foreign\s*dividend\s*payment", re.I)


def classify(sources, reader) -> None:
    from ..gst.sources import full_text

    unknown = []
    for src in sources:
        if src.error:
            src.kind, src.kind_how = "other", "unreadable"
            continue
        name = re.sub(r"[_\-.]+", " ", src.name.lower())
        kind = next((k for k, p in _RULES if re.search(p, name)), None) or next((k for k, p in _RULES if re.search(p, full_text(src, 1500).lower())), None)
        if kind:
            src.kind, src.kind_how = kind, "name"
        else:
            unknown.append(src)
    if unknown and reader is not None:
        for src, kind in zip(unknown, reader.classify(unknown, KINDS)):
            src.kind, src.kind_how = (kind if kind in KINDS else "other"), "ai"


class Ica:
    def __init__(self, su, data: dict):
        self.su, self.d, self.f = su, data, Flags()
        self.bd, self.start = su.balance_date, su.fy_start

    def _given(self, key: str, found, how_found: str, label: str, needed: bool = True, evidence: str = ""):
        """A figure: the accountant's setting, else what the documents give, else an exception."""
        given = self.su.money(key)
        if given is not None:
            return given, "job settings"
        if found is not None:
            return found, how_found
        if needed:
            self.f.add(f"no_{key}", "review", f"{label}: not found in the documents; nil used.", evidence or f"{label} (or enter it in the job settings).",
                       side="B")
        return ZERO, "not found (nil)"

    def movements(self) -> dict:
        """A: the ICA movement statement."""
        prior = self.d.get("prior") or {}
        opening = self.su.money("opening_ica")
        how_open = "job settings"
        if opening is None and prior.get("closing_balance") is not None:
            opening, how_open = prior["closing_balance"], "last year's ICA return / workpaper"
        if opening is None and self.su.first_year:
            opening, how_open = ZERO, "first-year company"
        if opening is None:
            self.f.add("no_opening", "blocking", "The opening ICA balance couldn't be established (missing history isn't a nil balance).",
                       "Last year's ICA return or workpaper, or the opening ICA in the job settings.", side="A")
            opening, how_open = ZERO, "not established"
        tax = [x for x in self.d["ird"] if not x["account_type"] or re.search(r"income|\binc\b|\bitn\b|\btax\b", x["account_type"], re.I)
               and not re.search(r"gst|payroll|emp|paye", x["account_type"], re.I)]
        in_year = [x for x in tax if self.start <= x["effective"] <= self.bd]
        paid = [x for x in in_year if x["category"] in ("payment", "transfer") and x["amount"] < 0]
        refunded = [x for x in in_year if x["category"] in ("refund", "transfer") and x["amount"] > 0]
        excluded = [x for x in in_year if x["category"] in ("interest", "penalty")]
        rows = []
        for x in paid:
            rows.append({"id": _id("M", x["id"]), "date": x["effective"], "category": "Income Tax Paid", "description": x["type"], "credit": -x["amount"],
                         "debit": ZERO, "source": x["source"], "note": "transfer in: confirm the account it came from" if x["category"] == "transfer" else ""})
        for x in refunded:
            rows.append({"id": _id("M", x["id"]), "date": x["effective"], "category": "Income Tax Refunded", "description": x["type"], "credit": ZERO,
                         "debit": x["amount"], "source": x["source"], "note": "transfer out" if x["category"] == "transfer" else ""})
        if excluded:
            self.f.add("uomi", "info", f"{len(excluded)} use-of-money interest or penalty line(s) kept out of the ICA ({q(sum((x['amount'] for x in excluded), ZERO)):,}).",
                       refs=[x["source"] for x in excluded[:5]], side="A")
        if not self.d["ird"]:
            self.f.add("no_ird", "blocking", "No IRD income tax transaction summary was found: tax payments and refunds can't be evidenced.",
                       "The myIR income tax transaction summary for the year (and after it for later settlement).", side="A")
        # RWT and imputation credits on income received: IRD's income summary first, else dividend statements, else the ledger.
        rwt = imp = ZERO
        if self.d["income"]:
            for it in self.d["income"]:
                rwt += it["rwt"] or ZERO
                imp += it["imputation_credits"] or ZERO
                if (it["rwt"] or ZERO) or (it["imputation_credits"] or ZERO):
                    rows.append({"id": _id("M", it["source"], it["payer"]), "date": None, "category": f"{it['kind'].capitalize()} received — {it['payer']}",
                                 "description": f"gross {q(it['gross'] or ZERO):,}", "credit": (it["rwt"] or ZERO) + (it["imputation_credits"] or ZERO),
                                 "debit": ZERO, "source": it["source"], "note": "IRD company income summary"})
            how_income = "IRD company income summary"
        elif self.d["div_received"]:
            for it in self.d["div_received"]:
                rwt += it["rwt"] or ZERO
                imp += it["imputation_credits"] or ZERO
            how_income = "dividend statements"
        else:
            rwt = sum((ln["debit"] - ln["credit"] for ln in self.d["gl"] if RWT_ACCOUNT.search(ln["account"]) and not re.search(r"payable", ln["account"], re.I)
                       and self.start <= ln["date"] <= self.bd), ZERO)
            imp = sum((ln["debit"] - ln["credit"] for ln in self.d["gl"] if IMP_ACCOUNT.search(ln["account"]) and "attached" not in ln["account"].lower()
                       and self.start <= ln["date"] <= self.bd), ZERO)
            how_income = "general ledger (no IRD income summary)"
            self.f.add("no_income_summary", "review", "No IRD company income summary: RWT and imputation credits received are taken from the ledger.",
                       "IRD's company income summary for the year.", side="A")
        div_paid_credits = sum((it["imputation_credits"] or ZERO for it in self.d["div_paid"]), ZERO)
        if not self.d["div_paid"] and any(re.search(r"dividends?\s*(paid|declared)", r["account"], re.I) and r["balance"] for r in self.d["tb"]):
            self.f.add("dividends_paid", "review", "Dividends were paid in the year but the imputation credits attached aren't evidenced.",
                       "The dividend statements or resolutions showing the credits attached.", side="A")
        if any(FDP.search(f"{x['type']}") for x in self.d["ird"]):
            self.f.add("fdp", "review", "FDP lines found: foreign dividend payment rules were repealed — treat as legacy items for specialist review.",
                       side="A")
        tax_paid = sum((r["credit"] for r in rows if r["category"] == "Income Tax Paid"), ZERO)
        tax_refunded = sum((r["debit"] for r in rows if r["category"] == "Income Tax Refunded"), ZERO)
        credits = {"Income Tax Paid": tax_paid, "FDP Paid": ZERO, "RWT on Interest Received": rwt, "IMP & FDP Credits attached to div rec": imp,
                   "Other Credits": ZERO}
        debits = {"Income Tax Refunded": tax_refunded, "FDP Refunds": ZERO, "IMP Credits attached to div paid": div_paid_credits, "Other Debits": ZERO}
        closing = opening + sum(credits.values(), ZERO) - sum(debits.values(), ZERO)
        if closing < 0:
            self.f.add("debit_balance", "review", f"The ICA closes in debit ({q(closing):,}): further income tax and an imputation penalty may follow.",
                       "Review the debit and its timing before 31 March.", side="A")
        current = self.d.get("current_return") or {}
        if current.get("closing_balance") is not None and abs(current["closing_balance"] - closing) > Decimal("0.01"):
            self.f.add("return_differs", "review", f"This year's ICA return shows a closing balance of {q(current['closing_balance']):,}; the movements give "
                       f"{q(closing):,}.", "The return's detailed statement.", side="A", amount_=current["closing_balance"] - closing)
        return {"opening": opening, "opening_how": how_open, "credits": credits, "debits": debits, "closing": closing, "rows": rows,
                "income_how": how_income}

    def retained(self, a: dict) -> dict:
        """B: the closing ICA reconciled to retained earnings."""
        tc, fs, prior = self.d.get("taxcomp") or {}, self.d.get("fs") or {}, self.d.get("prior") or {}
        tax_rows = tb_matching(self.d["tb"], [], TAX_ACCOUNT, NOT_TAX)
        tb_tax = sum((-r["balance"] for r in tax_rows), ZERO) if tax_rows else None
        terminal, how_t = self._given("terminal_tax", tc.get("terminal_tax") if tc.get("terminal_tax") is not None else tb_tax,
                                      "tax computation" if tc.get("terminal_tax") is not None else "trial balance (income tax accounts)",
                                      "EOY terminal tax still to pay/refund")
        prov3, how_p3 = self._given("prov3_tax", tc.get("prov3_outstanding"), "tax computation", "Prov 3 tax still to pay/refund", needed=False)
        other, _ = self._given("other_adjustments", None, "", "Other adjustments", needed=False)
        if prov3 and how_t != "job settings":
            self.f.add("prov3_overlap", "review", "Prov 3 tax is added separately: confirm it isn't already in the terminal tax / net tax payable.",
                       side="B")
        balance = a["closing"] + terminal + prov3 + other
        grossed = balance * GROSS_UP
        re_rows = tb_matching(self.d["tb"], [], RE_ACCOUNT)
        tb_re = None
        if re_rows:
            tb_re = sum((-r["balance"] for r in re_rows), ZERO)
            pnl = [r for r in self.d["tb"] if PNL_TYPES.search(r.get("type", ""))]
            if pnl:
                tb_re += sum((-r["balance"] for r in pnl), ZERO)  # this year's profit, not yet closed to retained earnings
            elif self.d["tb"]:
                self.f.add("profit_unknown", "review", "The trial balance has no account types, so this year's profit couldn't be added to retained earnings.",
                           "The financial statements' closing retained earnings (or enter it in the job settings).", side="B")
        retained_found = fs.get("retained_earnings_closing") if fs.get("retained_earnings_closing") is not None else tb_re
        retained, how_re = self._given("retained_earnings", retained_found,
                                       "financial statements" if fs.get("retained_earnings_closing") is not None else "trial balance (retained earnings + profit)",
                                       "Retained profit")
        perm_found = None
        if prior.get("permanent_differences") is not None or tc.get("non_deductible_expenses") is not None or tc.get("non_taxable_income") is not None:
            perm_found = (prior.get("permanent_differences") or ZERO) + (tc.get("non_deductible_expenses") or ZERO) - (tc.get("non_taxable_income") or ZERO)
        permanent, how_perm = self._given("permanent_differences", perm_found, "last year's workpaper + this year's tax computation",
                                          "Permanent tax differences (cumulative)")
        timing_found = (prior.get("timing_differences") or ZERO) + (tc.get("timing_differences") or ZERO) \
            if prior.get("timing_differences") is not None or tc.get("timing_differences") is not None else None
        timing, how_tim = self._given("timing_differences", timing_found, "last year's workpaper + this year's tax computation",
                                      "Timing tax differences (cumulative)", needed=False)
        ic33, _ = self._given("ic33", prior.get("ic33_remaining"), "last year's workpaper", "Remaining 33% IC", needed=False)
        ic30, _ = self._given("ic30", prior.get("ic30_remaining"), "last year's workpaper", "Remaining 30% IC", needed=False)
        diff33 = ic33 * (GROSS_UP - Decimal(67) / Decimal(33))
        diff30 = ic30 * (GROSS_UP - Decimal(70) / Decimal(30))
        tax_paid_rp = retained + permanent + timing + diff33 + diff30
        difference = grossed - tax_paid_rp
        missing = difference * RATIO
        return {"terminal": terminal, "terminal_how": how_t, "prov3": prov3, "other": other, "balance": balance, "grossed": grossed, "retained": retained,
                "retained_how": how_re, "permanent": permanent, "permanent_how": how_perm, "timing": timing, "timing_how": how_tim, "ic33": ic33,
                "diff33": diff33, "ic30": ic30, "diff30": diff30, "tax_paid_rp": tax_paid_rp, "difference": difference, "missing": missing}

    def run(self) -> dict:
        if not self.d["tb"] and not (self.d.get("fs") or {}).get("retained_earnings_closing"):
            self.f.add("no_tb", "blocking", "Neither a trial balance nor the financial statements were found: retained earnings can't be established.",
                       "The year-end trial balance or financial statements.", side="B")
        if not self.d.get("taxcomp"):
            self.f.add("no_taxcomp", "review", "No tax computation: terminal tax and this year's permanent and timing differences come from the trial balance "
                       "and settings only.", "This year's tax computation or IR4 draft.", side="B")
        for p in self.d["problems"]:
            self.f.add("reading", "review", p["text"], p.get("evidence", ""), [p.get("source", "")])
        a = self.movements()
        b = self.retained(a)
        status = conclude(bool(self.f.blocking()), b["difference"], self.su.tolerance, ZERO)
        if status == "Unreconciled":
            self.f.add("difference", "review", f"Difference of {q(b['difference']):,} (missing credits {q(b['missing']):,}) remains: not forced to agree.",
                       "Permanent and timing differences, dividends, historical-rate credits and tax balances.", amount_=b["difference"], side="B")
        ica_lines = ([{"label": "Opening Balance", "value": a["opening"], "input": True, "note": a["opening_how"], "key": "op"},
                      {"heading": True, "label": "Credits"}]
                     + [{"label": k, "value": v, "indent": 1, "key": f"c{n}", "ref": "ICA movements"} for n, (k, v) in enumerate(a["credits"].items())]
                     + [{"label": "Total Credits", "formula": "=" + "+".join(f"{{c{n}}}" for n in range(len(a["credits"]))), "value": sum(a["credits"].values(), ZERO),
                         "strong": True, "key": "tc"},
                        {"heading": True, "label": "Debits"}]
                     + [{"label": k, "value": v, "indent": 1, "key": f"d{n}", "ref": "ICA movements"} for n, (k, v) in enumerate(a["debits"].items())]
                     + [{"label": "Total Debits", "formula": "=" + "+".join(f"{{d{n}}}" for n in range(len(a["debits"]))), "value": sum(a["debits"].values(), ZERO),
                         "strong": True, "key": "td"},
                        {"label": "Closing Balance", "formula": "={op}+{tc}-{td}", "value": a["closing"], "strong": True}])
        re_lines = [
            {"label": "End of Year Balance of IC Reconciliation", "value": a["closing"], "ref": "Imputation Credits", "key": "eoy"},
            {"label": "Plus EOY Terminal Tax still to pay/refund", "value": b["terminal"], "input": True, "note": b["terminal_how"], "key": "tt"},
            {"label": "Plus Prov 3 Tax still to pay/refund", "value": b["prov3"], "input": True, "key": "p3"},
            {"label": "Other Adjustments", "value": b["other"], "input": True, "key": "oa"},
            {"label": "Balance", "formula": "={eoy}+{tt}+{p3}+{oa}", "value": b["balance"], "strong": True, "key": "bal"},
            {"label": "Imputation Ratio", "value": Decimal("0.3889"), "ratio": True, "note": "28/72, applied exactly"},
            {"label": "Balance Grossed Up", "formula": "={bal}*72/28", "value": b["grossed"], "strong": True, "key": "gu"},
            {"label": "Retained Profit", "value": b["retained"], "input": True, "note": b["retained_how"], "key": "rp"},
            {"label": "Permanent Tax Differences (enter credits as -ve)", "value": b["permanent"], "input": True, "note": b["permanent_how"], "key": "pd"},
            {"label": "Timing Tax Differences", "value": b["timing"], "input": True, "note": b["timing_how"], "key": "td"},
            {"label": "Remaining 33% IC as at 31 Mar 2011", "value": b["ic33"], "input": True, "key": "c33"},
            {"label": "33% RE differential", "formula": "={c33}*(72/28-67/33)", "value": b["diff33"], "key": "d33"},
            {"label": "Remaining 30% IC as at 31 Mar 2013 (excluding those originally earned at 33%)", "value": b["ic30"], "input": True, "key": "c30"},
            {"label": "30% RE differential", "formula": "={c30}*(72/28-70/30)", "value": b["diff30"], "key": "d30"},
            {"label": "Tax Paid Retained Profit", "formula": "={rp}+{pd}+{td}+{d33}+{d30}", "value": b["tax_paid_rp"], "strong": True, "key": "tp"},
            {"label": "Difference", "formula": "={gu}-{tp}", "value": b["difference"], "strong": True, "key": "df"},
            {"label": "Missing Credits", "formula": "={df}*28/72", "value": b["missing"], "strong": True},
        ]
        counts = {s_: sum(1 for x in self.f.items if x["severity"] == s_) for s_ in ("blocking", "review", "info")}
        return {"agent": "ica", "status": status, "ica_lines": ica_lines, "re_lines": re_lines, "lines": ica_lines + re_lines,
                "movements": a, "retained": b, "exceptions": self.f.items, "counts": counts, "corrections": [],
                "conclusions": [{"label": "ICA closing balance", "status": "Incomplete evidence" if self.f.blocking("A") else "Prepared", "residual": a["closing"]},
                                {"label": "Difference to retained earnings", "status": status, "residual": b["difference"]}]}


# --- the workpaper ---------------------------------------------------------------------------------------------

def workbook(result: dict, su, meta: dict) -> bytes:
    r = result
    wb = Workbook()
    ws = wb.active
    ws.title = "Imputation Credits"
    ws.sheet_properties.tabColor = W.MAROON
    for col, w in {"A": 62, "B": 18, "C": 46}.items():
        ws.column_dimensions[col].width = w
    row = W.header(ws, su, meta, "Imputation Credits", "I1", 3, note="If the opening balance is in debit, enter it as a negative.")
    row = S.banner(ws, row, r["status"], last="C")
    end = S.statement(ws, row, r["ica_lines"], value_head="Imputation Credit Account")
    W.signoff(ws, end + 3, su, meta)
    W._print_setup(ws, landscape=False)

    ws = wb.create_sheet("Reconcile ICA to RE")
    ws.sheet_properties.tabColor = W.MAROON
    for col, w in {"A": 62, "B": 18, "C": 46}.items():
        ws.column_dimensions[col].width = w
    row = W.header(ws, su, meta, "Reconcile Closing Imputation Cr Balance to RE", "I2", 3,
                   note="The reconciliation is effective at the balance date, not 31 March. Enter all credits as +ves, unless stated.")
    end = S.statement(ws, row, r["re_lines"])
    W._put(ws, f"A{end + 2}", "Commentary", font=W.F_SECTION)
    ws.merge_cells(f"A{end + 3}:C{end + 7}")
    W._put(ws, f"A{end + 3}", result.get("summary") or "", align=W.WRAP, border=W.BOX)
    W._print_setup(ws, landscape=False)

    ws, row = W.sheet(wb, "ICA movements", "I3", su, meta, {1: 12, 2: 34, 3: 40, 4: 14, 5: 14, 6: 30, 7: 44},
                      note="Every movement in the account, once, with its evidence. Use-of-money interest and penalties are never ICA movements.")
    head = row
    W.table(ws, row, ["Date", "Category", "Description", "Credit", "Debit", "Note", "Source"],
            [[m["date"], m["category"], m["description"], m["credit"], m["debit"], m["note"], m["source"]] for m in r["movements"]["rows"]],
            money=(4, 5), wrap=(2, 3, 6, 7), totals=(4, 5))
    W._finish(ws, head)

    ws, row = W.sheet(wb, "Tax payments & balances", "I4", su, meta, {1: 12, 2: 12, 3: 36, 4: 14, 5: 14, 6: 44},
                      note="IRD's income tax account line by line: principal, interest and penalties apart.")
    head = row
    W.table(ws, row, ["Date", "Period", "Transaction", "Category", "Amount (owed +)", "Source"],
            [[x["date"], x["period_end"], x["type"], x["category"], x["amount"], x["source"]] for x in r["ird_lines"]], money=(5,), wrap=(3, 6))
    W._finish(ws, head)

    ws, row = W.sheet(wb, "Dividends & income", "I5", su, meta, {1: 30, 2: 12, 3: 14, 4: 14, 5: 14, 6: 44},
                      note="Interest and dividends received (RWT and credits) and dividends paid (credits attached).")
    head = row
    end = W.table(ws, row, ["Payer", "Kind", "Gross / cash", "RWT", "Imputation credits", "Source"],
                  [[x["payer"], x["kind"], x["gross"], x["rwt"], x["imputation_credits"], x["source"]] for x in r["income"]],
                  money=(3, 4, 5), totals=(3, 4, 5), wrap=(6,), title="Received")
    W.table(ws, end + 3, ["Date", "Amount", "Imputation credits attached", "Source"],
            [[x["date"], x["amount"], x["imputation_credits"], x["source"]] for x in r["div_paid"]], money=(2, 3), totals=(2, 3), wrap=(4,),
            title="Paid or credited")
    W._finish(ws, head)

    ws, row = W.sheet(wb, "Historical rates", "I6", su, meta, {1: 40, 2: 16, 3: 22, 4: 18},
                      note="Credits at 33% and 30% convert at their own ratios; the baseline above is converted at 72/28. 28% applies from 2011-12.")
    b = r["retained"]
    W.table(ws, row, ["Credits", "Remaining IC", "Conversion", "RE differential"],
            [["33% credits (to 31 Mar 2011)", b["ic33"], "67/33 vs 72/28", b["diff33"]],
             ["30% credits (to 31 Mar 2013)", b["ic30"], "70/30 vs 72/28", b["diff30"]]], money=(2, 4))
    W._print_setup(ws)

    S.exceptions_sheet(wb, su, meta, r["exceptions"], "I7")
    S.sources_sheet(wb, su, meta, result["sources"], "I8")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# --- the run ---------------------------------------------------------------------------------------------------

def _income(src, reader) -> list[dict]:
    got = reader.extract("income_summary", src) if reader else {}
    return [{"payer": it.get("payer", ""), "kind": it.get("kind") or "other", "gross": amount(it.get("gross")), "rwt": amount(it.get("rwt")),
             "imputation_credits": amount(it.get("imputation_credits")), "source": f"{src.sid} {src.name}, {it.get('source', '')}"}
            for it in got.get("items", [])]


def read_all(sources, reader) -> dict:
    d = {"ird": [], "gl": [], "gl_opening": {}, "tb": [], "income": [], "div_received": [], "div_paid": [], "prior": None, "current_return": None,
         "taxcomp": None, "fs": None, "problems": []}
    for src in sources:
        if src.error:
            d["problems"].append({"text": f"{src.name}: {src.error}", "source": src.sid})
            continue
        k, problem = src.kind, ""
        if k == "ird_income_tax":
            got = read_myir(src, reader)
            d["ird"] += got["lines"]
            problem = got["problem"]
        elif k == "trial_balance":
            got = R.read_trial_balance(src, reader)
            d["tb"] += got["rows"]
            problem = got["problem"]
        elif k == "general_ledger":
            got = R.read_ledger(src, reader)
            d["gl"] += got["lines"]
            problem = got["problem"]
        elif k == "income_summary":
            d["income"] += _income(src, reader)
            problem = "" if d["income"] else "The income summary could not be read."
        elif k in ("prior_ica", "ica_return", "tax_computation", "financial_statements"):
            got = reader.extract(k, src) if reader else {}
            vals = {key: (amount(v) if key not in ("source", "tax_year_end") else v) for key, v in got.items()}
            if not any(v is not None and v != "" for key, v in vals.items() if key not in ("source", "tax_year_end")):
                problem = "Its figures could not be read: enter them in the job settings."
            else:
                vals["source"] = f"{src.sid} {src.name}"
                d[{"prior_ica": "prior", "ica_return": "current_return", "tax_computation": "taxcomp", "financial_statements": "fs"}[k]] = vals
        elif k == "dividends":
            got = reader.extract("dividends", src) if reader else {}
            d["div_received"] += [{"payer": x.get("payer", ""), "rwt": amount(x.get("rwt")), "imputation_credits": amount(x.get("imputation_credits")),
                                   "source": f"{src.sid} {src.name}, {x.get('source', '')}"} for x in got.get("received", [])]
            d["div_paid"] += [{"date": x.get("date", ""), "amount": amount(x.get("amount")), "imputation_credits": amount(x.get("imputation_credits")),
                               "source": f"{src.sid} {src.name}, {x.get('source', '')}"} for x in got.get("paid", [])]
        if problem:
            d["problems"].append({"text": f"{src.name} ({KINDS.get(k, k)}): {problem}", "source": src.sid,
                                  "evidence": "A structured export (Excel or CSV), or the figure in the job settings."})
    return d


def execute(run_id: str, job_id: str, options: dict, pm, check=lambda: None) -> dict:
    started = time.time()

    def emit(stage, label, state="running", **counts):
        pm.send_event(run_id, {"type": "ai_precheck.progress", "job_id": job_id, "stage": stage, "state": state, "label": label, "counts": counts})

    job = pm.get_job(job_id)
    su = setup_from(options, job, EXTRA)
    reader = Reader(run_id, purpose="a New Zealand imputation credit account (ICA) reconciliation", method=SKILL)
    emit("read", "Reading the imputation documents from Google Drive")
    try:
        sources = gather(options.get("drive_link", ""))
    except SourceProblem as exc:
        raise WpStop(str(exc)) from exc
    check()
    classify(sources, reader)
    emit("read", f"{len(sources)} documents found", "done", documents=len(sources))
    emit("checked", "Reading the ICA returns, IRD statements, income summary, tax computation and the accounts")
    data = read_all(sources, reader)
    check()
    emit("compared", "Preparing the ICA statement and reconciling it to retained earnings")
    result = Ica(su, data).run()
    result.update(ird_lines=data["ird"], income=data["income"] + [{"payer": x["payer"], "kind": "dividend", "gross": None, "rwt": x["rwt"],
                                                                     "imputation_credits": x["imputation_credits"], "source": x["source"]}
                                                                    for x in data["div_received"]], div_paid=data["div_paid"])
    emit("compared", result["status"], "done")
    check()
    facts = ("\n".join(f"{ln['label']}: {ln.get('value')}" for ln in result["lines"] if not ln.get("heading"))
             + "\nExceptions: " + "; ".join(f"[{x['severity']}] {x['text']}" for x in result["exceptions"][:20]))
    summary = reader.summary(facts) or (f"{result['status']}. Closing ICA {q(result['movements']['closing']):,}; difference to retained earnings "
                                        f"{q(result['retained']['difference']):,} (missing credits {q(result['retained']['missing']):,}).")
    result.update(summary=summary, sources=[x.brief() for x in sources],
                  settings={"Entity": su.entity, "IRD number": su.ird_number, "Financial year start": su.fy_start, "Balance date": su.balance_date,
                            "Currency": su.currency, "First-year company": "Yes" if su.first_year else "No", "Tolerance": su.tolerance,
                            **{k.replace("_", " ").capitalize(): v for k, v in su.extra.items()}})
    meta = {"run_id": run_id, "prep_date": su.prep_date, "versions": {"rules": RULES}}
    emit("verified", "Writing the workpaper")
    book = workbook(result, su, meta)
    from .. import memory
    from ..knowledge import Scope

    final = envelope(run_id, job_id, "ica", result, book, reader, started, sources, result["counts"], summary, result["status"], RULES)
    memory.safely(memory.remember_wp, Scope.of(job), "wp_ica", final["gst"])
    emit("verified", "Workpaper written", "done")
    return final
