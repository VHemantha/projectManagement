"""Reading the electronic workpapers' documents (AFIT, 16 Nov 2026): what each document is, whose it is,
and its figures - code reads the ledgers and trial balance; the reader model reads the PDFs (IRD
summaries, statements, minutes, invoices) into fixed records. Every figure keeps its source."""
from __future__ import annotations

import hashlib
import re
from datetime import date
from decimal import Decimal

from ..gst import ai as A
from ..gst import readers as R
from ..gst.money import ZERO, amount, day
from ..gst.sources import Source, full_text, table_rows
from ..wp.base import read_myir  # noqa: F401  (the myIR layout registered there)

# --- the kinds of document ---------------------------------------------------------------------------
KINDS = {
    "general_ledger": "General ledger detail (all accounts with transactions and balances)",
    "trial_balance": "Trial balance",
    "bank_statement": "Bank statement or bank transaction history",
    "bank_reconciliation": "Bank reconciliation report from the accounting software",
    "ird_income_summary": "IRD income summary (interest and dividends received, with tax deducted)",
    "ird_tax_transactions": "IRD (myIR) income tax account transactions for a tax year",
    "ica_statement": "IRD imputation credit account details / ICA statement or return",
    "dividend_received": "Dividend statement from a company the entity holds shares in",
    "interest_statement": "Interest or shareholder current account statement showing interest and RWT",
    "dividend_paid": "The entity's own dividend minutes or dividend statement (dividends it paid)",
    "fee_statement": "Accountant's fee statement or invoices to the entity",
    "creditors": "Creditors / accounts payable list or aged payables",
    "debtors": "Debtors / accounts receivable list or aged receivables",
    "tax_computation": "Income tax computation or tax return",
    "home_office": "Home office (use of home) records: floor areas, household costs",
    "gst": "GST return or GST report (the GST reconciliation is a separate agent)",
    "prior_workpapers": "Workpapers file (Excel workpapers of a year)",
    "other": "Anything else (correspondence, notes, rulings, personal documents)",
}
_RULES = [
    ("prior_workpapers", r"workpapers?.*\.(xlsm|xlsx)$|\.xlsm$"),
    ("gst", r"\bgst\b"),
    ("creditors", r"creditor|accounts payable|aged payables|\bap\b ageing"),
    ("debtors", r"debtor|receivable"),
    ("bank_reconciliation", r"bank(ing)? ?rec"),
    ("general_ledger", r"general ledger|gl detail|ledger report"),
    ("trial_balance", r"trial balance"),
    ("ird_income_summary", r"income summary|ird earnings|income from myir"),
    ("ica_statement", r"account details.*attributes|\bica\b|imputation credit account|ir4j"),
    ("ird_tax_transactions", r"transactions? ?- ?transaction details|income tax.*transaction|myir.*transaction"),
    ("dividend_paid", r"minutes|resolution|dividends? declared"),
    ("dividend_received", r"dividend statement|dividend advice"),
    ("interest_statement", r"shareholder (current account )?statement|interest certificate|rwt certificate"),
    ("fee_statement", r"accountan(cy|t)'?s? fee|fee statement|\bpa statements?\b"),
    ("tax_computation", r"tax (calculation|computation)|\bir4\b|tax return"),
    ("home_office", r"home office|use of home|uoho"),
    ("bank_statement", r"bank statement|transaction history|\d{2}-\d{4}-\d{7}-\d{2,3}"),
]
_TEXT_RULES = [
    ("bank_reconciliation", r"banking reconciliation report|bank reconciliation"),
    ("general_ledger", r"general ledger report"),
    ("ird_income_summary", r"income from myir|your income from"),
    ("ica_statement", r"ica closing balance"),
    ("ird_tax_transactions", r"transaction details.*income tax|income tax.*transactions"),
    ("dividend_paid", r"company minute|minutes of a resolution"),
    ("dividend_received", r"dividend statement"),
    ("interest_statement", r"shareholder current account statement|gross interest payment"),
]


def classify(sources: list[Source], reader=None) -> None:
    unknown = []
    for src in sources:
        if src.error:
            src.kind, src.kind_how = "other", "unreadable"
            continue
        name = re.sub(r"[_]+", " ", src.name.lower())
        kind = next((k for k, p in _RULES if re.search(p, name)), None)
        if kind is None:
            head = full_text(src, limit=2500).lower()
            kind = next((k for k, p in _TEXT_RULES if re.search(p, head)), None)
        if kind:
            src.kind, src.kind_how = kind, "name"
        else:
            unknown.append(src)
    if unknown and reader is not None:
        for src, kind in zip(unknown, reader.classify(unknown, KINDS)):
            src.kind, src.kind_how = (kind if kind in KINDS else "other"), "ai"
    for src in unknown:
        if not src.kind:
            src.kind = "other"


# --- whose document it is ----------------------------------------------------------------------------
_SUFFIX = {"ltd", "limited", "the", "company", "co", "trust", "trustee", "trustees", "partnership", "nz", "new", "zealand", "and", "&", "of",
           "holdings", "group"}


def core_words(entity: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (entity or "").lower())
    core = [w for w in words if w not in _SUFFIX]
    return core[:3] or words[:2]


# IRD's own documents name their taxpayer in the header (name and IRD number). The owners' personal
# myIR documents mention the company too - as employer or as the other side of a transfer - so for these
# the entity must be the header's taxpayer, not just named somewhere (AFIT's Yearend FY26 folder, 17 Nov 2026).
IRD_KINDS = {"ird_income_summary", "ird_tax_transactions", "ica_statement"}
_IRD_NO = re.compile(r"\b(\d{2,3})[- ](\d{3})[- ](\d{3})\b")


def _names(text: str, entity: str) -> bool:
    flat = re.sub(r"[^a-z0-9]+", " ", text.lower())
    words = core_words(entity)
    return bool(words) and all(re.search(rf"\b{re.escape(w)}\b", flat) for w in words)


def entity_check(src: Source, entity: str, ird_number: str = "", kind: str = "") -> str:
    """"confirmed" when the document is the entity's; otherwise "other". An IRD document must be about
    the entity (its header taxpayer); any other document must name the entity or its IRD number."""
    text = full_text(src, limit=30_000)
    digits = re.sub(r"\D", "", ird_number or "")
    if (kind or src.kind) in IRD_KINDS:
        first = _IRD_NO.search(text)
        if first and len(digits) in (8, 9):
            return "confirmed" if "".join(first.groups()).lstrip("0") == digits.lstrip("0") else "other"
        return "confirmed" if _names(text[:600], entity) else "other"
    if _names(src.name + "\n" + text, entity):
        return "confirmed"
    if len(digits) in (8, 9) and any("".join(m.groups()).lstrip("0") == digits.lstrip("0") for m in _IRD_NO.finditer(text)):
        return "confirmed"
    return "other"


def fingerprint(src: Source) -> str:
    return hashlib.sha1(full_text(src, limit=200_000).encode("utf-8", "replace")).hexdigest()


# --- ledgers ------------------------------------------------------------------------------------------
_MYOB_ACCOUNT = re.compile(r"^\s*(\d-\d{4})\s*$")
_PERIOD = re.compile(r"(\d{1,2} \w{3,9} \d{4})\s*-\s*(\d{1,2} \w{3,9} \d{4})")


def read_ledger_accounts(src: Source, ai=None) -> dict:
    """Accounts with opening and closing balances (debit +) and their lines: MYOB's "General ledger
    report" layout read by code; other layouts through the generic ledger reader."""
    rows = table_rows(src)
    head = " ".join(str(v) for _, _, values in rows[:8] for v in values if v)
    period = _PERIOD.search(head)
    span = (day(period.group(1)), day(period.group(2))) if period else (None, None)
    myob = any(str(values[0] or "").strip() == "Date" and "Net activity ($)" in [str(v or "").strip() for v in values] for _, _, values in rows[:15])
    accounts: dict[str, dict] = {}
    if myob:
        current = None
        for sheet, row_no, values in rows:
            v = list(values) + [None] * 10
            first = str(v[0] or "").strip()
            if _MYOB_ACCOUNT.match(first):
                current = {"code": first, "name": str(v[1] or "").strip(), "opening": amount(v[4]) or ZERO, "closing": amount(v[8]),
                           "lines": [], "source": src.ref(sheet, row_no)}
                accounts[first] = current
                if current["closing"] is None:
                    current["closing"] = current["opening"]
                continue
            if current is None:
                continue
            if first == "Total":
                current["opening"] = amount(v[4]) if amount(v[4]) is not None else current["opening"]
                current["closing"] = amount(v[8]) if amount(v[8]) is not None else current["closing"]
                current = None
                continue
            when = day(v[0])
            if when is None:
                continue
            debit, credit, tax = amount(v[5]) or ZERO, amount(v[6]) or ZERO, amount(v[9]) or ZERO
            current["lines"].append({"date": when, "ref": str(v[1] or ""), "type": str(v[2] or ""), "description": str(v[3] or ""), "debit": debit,
                                     "credit": credit, "tax": tax, "source": src.ref(sheet, row_no)})
        return {"accounts": list(accounts.values()), "period": span, "layout": "MYOB general ledger report",
                "problem": "" if accounts else "No accounts were found in the ledger."}
    got = R.read_ledger(src, ai)
    for ln in got["lines"]:
        key = ln.get("code") or ln["account"]
        acc = accounts.setdefault(key, {"code": ln.get("code") or "", "name": ln["account"], "opening": got["opening"].get(ln["account"], ZERO),
                                        "closing": None, "lines": [], "source": ln["source"]})
        acc["lines"].append({"date": ln["date"], "ref": ln.get("ref", ""), "type": ln.get("source_type", ""), "description": ln.get("description", ""),
                             "debit": ln["debit"], "credit": ln["credit"], "tax": ln.get("gst") or ZERO, "source": ln["source"]})
    for acc in accounts.values():
        acc["closing"] = acc["opening"] + sum((x["debit"] - x["credit"] for x in acc["lines"]), ZERO)
    return {"accounts": list(accounts.values()), "period": span, "layout": "general ledger", "problem": got["problem"]}


def read_tb(src: Source, ai=None) -> dict:
    got = R.read_trial_balance(src, ai)
    return {"accounts": [{"code": r.get("code", ""), "name": r["account"], "type": r.get("type", ""), "opening": None, "closing": r["balance"],
                          "lines": [], "source": r["source"]} for r in got["rows"]], "problem": got["problem"]}


# --- the reader model's records -----------------------------------------------------------------------
_S, _B = A._STR, A._BOOL
A.SCHEMAS.update({
    "ewp_income_summary": A._obj({"interest": A._list({"payer": _S, "date": _S, "gross": _S, "tax": _S, "source": _S}),
                                  "dividends": A._list({"payer": _S, "date": _S, "gross": _S, "tax": _S, "imputation": _S, "source": _S}),
                                  "period_from": _S, "period_to": _S}),
    "ewp_dividend_received": A._obj({"payer": _S, "date": _S, "gross": _S, "imputation": _S, "rwt": _S, "net": _S, "source": _S}),
    "ewp_interest_statement": A._obj({"payer": _S, "period_end": _S, "gross": _S, "rwt": _S, "net": _S, "source": _S}),
    "ewp_dividend_paid": A._obj({"date": _S, "gross": _S, "imputation": _S, "rwt": _S, "net": _S, "source": _S}),
    "ewp_ica": A._obj({"period_end": _S, "ica_closing": _S, "source": _S}),
    "ewp_bank_statement": A._obj({"account_name": _S, "account_number": _S, "closing_date": _S, "closing_balance": _S, "source": _S}),
    "ewp_bank_rec": A._obj({"account": _S, "account_number": _S, "date": _S, "ledger_balance": _S, "statement_balance": _S,
                            "outstanding_withdrawals": A._list({"date": _S, "reference": _S, "description": _S, "amount": _S}),
                            "outstanding_deposits": A._list({"date": _S, "reference": _S, "description": _S, "amount": _S}), "source": _S}),
    "ewp_fee_statement": A._obj({"client": _S, "lines": A._list({"date": _S, "description": _S, "reference": _S, "debit": _S, "credit": _S})}),
    "ewp_creditors": A._obj({"as_at": _S, "none_stated": _B, "rows": A._list({"supplier": _S, "reference": _S, "amount": _S, "gst_included": _B})}),
    "ewp_tax_computation": A._obj({"tax_year": _S, "taxable_income": _S, "tax_payable": _S, "source": _S}),
})
A.ASK.update({
    "ewp_income_summary": "Read IRD's income summary: every interest payment (payer, date, gross, tax deducted) and every dividend (payer, date, gross, "
                          "tax deducted, imputation credits), and the period it covers. Dates as YYYY-MM-DD; amounts as shown.",
    "ewp_dividend_received": "Read this dividend statement received by the shareholder: the paying company, the date, the gross dividend for tax "
                             "purposes, imputation credits, RWT deducted and the net dividend.",
    "ewp_interest_statement": "Read this statement for interest paid to the account holder: the payer, the period end, gross interest, RWT withheld and "
                              "the net interest.",
    "ewp_dividend_paid": "Read these dividend minutes / the company's own dividend statement (a dividend the company paid): the payment date, the gross "
                         "dividend, the imputation credits attached, RWT deducted and the net dividend paid.",
    "ewp_ica": "Read the imputation credit account details: the period (balance date) and the ICA closing balance exactly as shown, with its sign.",
    "ewp_bank_statement": "Read this bank statement: the account name and number, the last date it covers and the closing balance on that date.",
    "ewp_bank_rec": "Read this bank reconciliation report: the account name and its bank account number (if shown), the date, the balance per the ledger, the expected balance on the bank statement, "
                    "and every outstanding (unpresented) withdrawal and deposit with its date, reference, description and amount.",
    "ewp_fee_statement": "Read this accountant's statement or invoice: the client it is addressed to and every line (date, description, invoice or "
                         "reference number, debit, credit). Dates as YYYY-MM-DD.",
    "ewp_creditors": "Read this creditors list / accounts payable report: the date it is as at, whether it states there are no creditors, and each "
                     "creditor (supplier, reference, amount owing, whether GST is included).",
    "ewp_tax_computation": "Read this income tax computation or return: the tax year, the taxable income and the income tax payable (residual income "
                           "tax before credits if shown separately, otherwise the tax payable).",
})


def money(record: dict, key: str) -> Decimal | None:
    return amount(record.get(key))


def when(record: dict, key: str = "date") -> date | None:
    return day(record.get(key))
