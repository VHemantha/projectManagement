"""Running the electronic workpapers (AFIT, 16 Nov 2026): read every document in the Drive folder and its
subfolders (all of them are the job's, 18 Nov 2026), read their figures, run each chosen workpaper's
procedure and write the template.
Also applies an accountant's corrections to a finished workbook (the same cell writer)."""
from __future__ import annotations

import base64
import re
import time
from decimal import Decimal

from ..gst.ai import Reader
from ..gst.money import ZERO, amount, day, q
from ..gst.sources import SourceProblem, full_text, gather
from ..wp.base import WpStop, envelope, read_myir, setup_from
from . import catalogue as C
from . import readers as X
from . import xlsm
from .procedures import Ewp

RULES = "ewp-1.0"
SKILL = "nz-electronic-workpapers"
EXTRA = ("entity_type", "gst_status", "reviewed_by")
# Which workpaper each kind of document supports (Supporting Docs sheet, and the inventory).
KIND_WP = {"general_ledger": "B1", "trial_balance": "B1", "bank_statement": "F1.1", "bank_reconciliation": "F1.1", "creditors": "M1",
           "ird_tax_transactions": "Q1", "tax_computation": "Q1", "ica_statement": "Q3a", "dividend_paid": "Q3a", "ird_income_summary": "T2",
           "dividend_received": "T2", "interest_statement": "T2", "fee_statement": "V5", "home_office": "V2", "debtors": "S2", "gst": "L1"}
NOT_READ = {"other", "gst", "prior_workpapers"}


def amt(value) -> Decimal | None:
    if value is None:
        return None
    text = str(value).replace("$", "").replace("NZD", "").strip()
    if re.fullmatch(r"(?i)nil|none|-", text):
        return ZERO
    return amount(text)


def _period_of(src) -> object:
    m = re.search(r"(\d{1,2}-[A-Za-z]{3}-\d{4})", src.name + " " + full_text(src, limit=1500))
    return day(m.group(1)) if m else None


def read_all(sources, reader, su) -> dict:
    d = {"accounts": [], "gl_source": None, "income_summary": [], "interest_statements": [], "dividends_received": [], "dividends_paid": [], "ica": [],
         "bank_statements": [], "bank_recs": [], "fee_statements": [], "creditors": [], "tax_transactions": [], "tax_docs": [], "tax_computation": None,
         "home_office_docs": [], "inventory": [], "problems": []}
    seen = {}
    ledgers = []
    for src in sources:
        item = {"sid": src.sid, "name": src.name, "path": src.path, "url": src.url, "kind": src.kind, "wp": KIND_WP.get(src.kind, ""), "entity": "",
                "status": "used", "note": ""}
        d["inventory"].append(item)
        if src.error:
            item.update(status="unreadable", note=src.error)
            continue
        if src.kind in NOT_READ:
            item.update(status="not used", note={"gst": "GST is the WP Agent's GST reconciliation", "prior_workpapers": "a workpapers file",
                                                  "other": "not a workpaper document"}[src.kind])
            continue
        # Every document in the job's folder is the job's (AFIT, 18 Nov 2026): none is set aside for not
        # naming the client or a supplier. Whether it names the client is still noted, for information.
        item["entity"] = X.entity_check(src, su.entity, su.ird_number, src.kind)
        fp = X.fingerprint(src)
        if fp in seen:
            item.update(status="duplicate", note=f"same content as {seen[fp]}")
            continue
        seen[fp] = src.name
        ref = f"{src.sid} {src.name}"
        k = src.kind

        def extract(kind, src=src, item=item):
            """The reader's record of the document; {} (and the document marked unreadable) when it couldn't be read."""
            got = reader.extract(kind, src)
            if not got:
                item.update(status="unreadable", note="the reader couldn't read it - try again, or add it as Excel/CSV")
                d["problems"].append({"text": f"{src.name} couldn't be read, so its figures are missing.", "source": src.sid})
            return got
        if k in ("general_ledger", "trial_balance"):
            got = X.read_ledger_accounts(src, reader) if k == "general_ledger" else X.read_tb(src, reader)
            if got.get("problem"):
                item.update(status="unreadable", note=got["problem"])
                continue
            ledgers.append((src, got))
        elif k == "ird_income_summary":
            g = extract("ewp_income_summary", src)
            d["income_summary"].append({
                "interest": [{"payer": r.get("payer", ""), "date": day(r.get("date")), "gross": amt(r.get("gross")) or ZERO, "tax": amt(r.get("tax")) or ZERO,
                              "source": f"{ref}, {r.get('source', '')}".strip(", ")} for r in g.get("interest", []) if amt(r.get("gross")) is not None],
                "dividends": [{"payer": r.get("payer", ""), "date": day(r.get("date")), "gross": amt(r.get("gross")) or ZERO, "tax": amt(r.get("tax")) or ZERO,
                               "imputation": amt(r.get("imputation")) or ZERO, "source": f"{ref}, {r.get('source', '')}".strip(", ")}
                              for r in g.get("dividends", []) if amt(r.get("gross")) is not None]})
        elif k == "interest_statement":
            g = extract("ewp_interest_statement", src)
            if amt(g.get("gross")) is not None:
                d["interest_statements"].append({"payer": g.get("payer", ""), "date": day(g.get("period_end")), "gross": amt(g.get("gross")),
                                                 "tax": amt(g.get("rwt")) or ZERO, "source": ref})
        elif k == "dividend_received":
            g = extract("ewp_dividend_received", src)
            if amt(g.get("gross")) is not None:
                d["dividends_received"].append({"payer": g.get("payer", ""), "date": day(g.get("date")), "gross": amt(g.get("gross")),
                                                "imputation": amt(g.get("imputation")) or ZERO, "rwt": amt(g.get("rwt")) or ZERO, "source": ref})
        elif k == "dividend_paid":
            g = extract("ewp_dividend_paid", src)
            if amt(g.get("gross")) is not None:
                d["dividends_paid"].append({"date": day(g.get("date")), "gross": amt(g.get("gross")), "imputation": amt(g.get("imputation")) or ZERO,
                                            "rwt": amt(g.get("rwt")) or ZERO, "net": amt(g.get("net")), "source": ref})
        elif k == "ica_statement":
            g = extract("ewp_ica", src)
            if amt(g.get("ica_closing")) is not None:
                d["ica"].append({"period_end": day(g.get("period_end")) or _period_of(src), "ica_closing": amt(g.get("ica_closing")), "source": ref})
        elif k == "bank_statement":
            g = extract("ewp_bank_statement", src)
            if g:
                d["bank_statements"].append({"account": g.get("account_name", ""), "number": g.get("account_number", ""), "closing_date": day(g.get("closing_date")),
                                         "closing_balance": amt(g.get("closing_balance")), "source": ref})
        elif k == "bank_reconciliation":
            g = extract("ewp_bank_rec", src)

            def items(rows):
                return [{"date": day(r.get("date")), "reference": r.get("reference", ""), "description": r.get("description", ""),
                         "amount": abs(amt(r.get("amount")) or ZERO)} for r in rows if amt(r.get("amount"))]
            if g:
                d["bank_recs"].append({"account": g.get("account", ""), "number": g.get("account_number", ""), "date": day(g.get("date")), "statement_balance": amt(g.get("statement_balance")),
                                   "ledger_balance": amt(g.get("ledger_balance")), "withdrawals": items(g.get("outstanding_withdrawals", [])),
                                   "deposits": items(g.get("outstanding_deposits", [])), "source": ref})
        elif k == "fee_statement":
            g = extract("ewp_fee_statement", src)  # used whoever it is addressed to: it is in the job's folder
            invoices = [{"date": day(r.get("date")), "reference": r.get("reference", ""), "amount": amt(r.get("debit")), "source": ref}
                        for r in g.get("lines", []) if amt(r.get("debit")) and re.search(r"invoice|inv\b|fee", f"{r.get('description', '')} {r.get('reference', '')}", re.I)]
            if g:
                d["fee_statements"].append({"source": ref, "invoices": [x for x in invoices if x["date"]]})
        elif k == "creditors":
            g = extract("ewp_creditors", src)
            if g:
                d["creditors"].append({"name": src.name, "source": ref, "none_stated": bool(g.get("none_stated")),
                                   "rows": [{"supplier": r.get("supplier", ""), "reference": r.get("reference", ""), "amount": amt(r.get("amount")) or ZERO,
                                             "gst_included": bool(r.get("gst_included"))} for r in g.get("rows", []) if amt(r.get("amount"))]})
        elif k == "ird_tax_transactions":
            got = read_myir(src, reader)
            period = _period_of(src)
            for ln in got["lines"]:
                ln["period_end"] = ln.get("period_end") or period
            d["tax_transactions"] += got["lines"]
            d["tax_docs"].append({"period_end": period, "source": ref, "lines": len(got["lines"])})
        elif k == "tax_computation":
            g = extract("ewp_tax_computation", src)
            if amt(g.get("tax_payable")) is not None:
                d["tax_computation"] = {"tax_payable": amt(g.get("tax_payable")), "taxable_income": amt(g.get("taxable_income")), "source": ref}
        elif k == "home_office":
            d["home_office_docs"].append(ref)
        elif k == "debtors":
            pass  # listed on Supporting Docs; S2 takes the receivables from the ledger
    # The ledger: the entity's general ledger covering the year, else its trial balance.
    def score(pair):
        src, got = pair
        start, end = got.get("period", (None, None)) or (None, None)
        return (src.kind == "general_ledger", end == su.balance_date, start == su.fy_start, len(got["accounts"]))
    if ledgers:
        src, got = max(ledgers, key=score)
        d["gl_source"] = {"sid": src.sid, "name": src.name, "entity": "confirmed", "layout": got.get("layout", "trial balance")}
        for acc in got["accounts"]:
            group, kind = C.b1_group(acc.get("code", ""), acc["name"], acc.get("type", ""))
            acc.update(group=group, type=kind)
        d["accounts"] = got["accounts"]
        for other, _ in ledgers:
            if other is not src:
                next(i for i in d["inventory"] if i["sid"] == other.sid).update(status="not used", note=f"{src.name} is the ledger used")
    return d


def supporting_docs(template: bytes, inventory: list[dict]) -> list[dict]:
    """Cells for the Supporting Docs sheet: each workpaper's documents on its own row (B to G)."""
    coords = [f"{c}{r}" for r in range(1, 330) for c in ("H", "I")]
    cells = xlsm.read(template, "Supporting Docs", coords)
    row_of = {}
    for r in range(1, 330):
        h, i = cells.get(f"H{r}"), cells.get(f"I{r}")
        if h and h == i and h not in row_of:
            row_of[h] = r
    out, by_wp = [], {}
    for item in inventory:
        if item["status"] == "used" and item["wp"] and item["wp"] in row_of:
            by_wp.setdefault(item["wp"], []).append(item)
    for wp, items in by_wp.items():
        for col, item in zip(C.SUPPORTING_DOCS_COLS, items):
            url = item.get("url") or ""
            if url.startswith("http"):
                value, kind = f'HYPERLINK("{url.replace(chr(34), "")}","{item["name"].replace(chr(34), "")}")', "formula"
            else:
                value, kind = item["name"], "text"
            out.append({"sheet": "Supporting Docs", "cell": f"{col}{row_of[wp]}", "value": value, "kind": kind})
    return out


def template_bytes() -> bytes:
    if not C.TEMPLATE.exists():
        raise WpStop("The electronic workpapers template isn't installed on the agent (templates/Electronic Workpapers Static 2026.xlsm).")
    return C.TEMPLATE.read_bytes()


_BANK_SHEET = re.compile(r"^F1\.(\d+)$")


def template_sheet(sheet: str) -> str:
    """The template sheet a sheet was made from: F1.2, F1.3 ... are copies of F1.1."""
    return "F1.1" if _BANK_SHEET.match(sheet) else sheet


def protected(template: bytes, sheets) -> dict[str, set[str]]:
    return {s: xlsm.formula_cells(template, template_sheet(s)) for s in set(sheets)}


def bank_links(template: bytes, sheets: list[str]) -> list[dict]:
    """What the template's macro does when the Workbench's bank quantity goes up (AFIT, 18 Nov 2026),
    for the sheets the agent made: the F1 group's count and a row per sheet in the hidden link table
    (so the Workbench and B1 link to them), the F lead sheet's rows, and B1's link to each sheet's
    workpaper balance (row 18 already links to F1.1)."""
    if not sheets:
        return []
    cells = [{"sheet": "Hidden", "cell": C.HIDDEN_F1_COUNT, "value": len(sheets), "kind": "number"}]
    extra = sheets[1:]
    if extra:
        col_l = xlsm.column(template, "Hidden", "L", 400)
        last = max(r for r, v in col_l.items() if v not in (None, ""))
        base = xlsm.read(template, "Hidden", [f"{c}{C.HIDDEN_F1_ROW}" for c in "KMNOP"])
        for i, name in enumerate(extra, start=1):
            r = last + i
            k = int(_BANK_SHEET.match(name).group(1))
            cells += [{"sheet": "Hidden", "cell": f"K{r}", "value": base[f"K{C.HIDDEN_F1_ROW}"], "kind": "text"},
                      {"sheet": "Hidden", "cell": f"L{r}", "value": name, "kind": "text"},
                      {"sheet": "Hidden", "cell": f"M{r}", "value": base[f"M{C.HIDDEN_F1_ROW}"], "kind": "text"},
                      {"sheet": "Hidden", "cell": f"N{r}", "value": 1, "kind": "number"},
                      {"sheet": "Hidden", "cell": f"O{r}", "value": round(float(base[f"O{C.HIDDEN_F1_ROW}"] or 15.1) + (k - 1) / 100, 2), "kind": "number"},
                      {"sheet": "Hidden", "cell": f"P{r}", "value": base[f"P{C.HIDDEN_F1_ROW}"], "kind": "text"},
                      {"sheet": "Hidden", "cell": f"Q{r}", "value": f'IF($N{r}=1,"#\'{name}\'!A1","#rc")', "kind": "formula"}]
    for row, name in zip(C.B1_BANK_ROWS[1:], extra):
        cells.append({"sheet": "B1", "cell": f"H{row}", "value": f"IFERROR('{name}'!WPBal1,0)", "kind": "formula"})
    for row, name in zip(C.F_LEAD_ROWS[1:], extra):
        cells += [{"sheet": "F", "cell": f"B{row}", "value": name, "kind": "text"},
                  {"sheet": "F", "cell": f"C{row}", "value": f"IFERROR('{name}'!nameBank,\"\")", "kind": "formula"},
                  {"sheet": "F", "cell": f"D{row}", "value": f"IFERROR(SUM('{name}'!bank_statement_bal),\"\")", "kind": "formula"},
                  {"sheet": "F", "cell": f"H{row}", "value": f"IFERROR('{name}'!GLBal,\"\")", "kind": "formula"}]
    return cells


def write_workbook(result: dict, inventory: list[dict]) -> tuple[bytes, list[dict]]:
    template = template_bytes()
    sheets = result.get("bank_sheets") or []
    # One bank reconciliation sheet per bank account: F1.2 onwards are copies of F1.1.
    book = xlsm.clone_sheets(template, "F1.1", sheets[1:]) if len(sheets) > 1 else template
    cells = [{"sheet": f["sheet"], "cell": f["cell"], "value": f["value"], "kind": f["kind"]} for f in result["fields"] if f["value"] not in (None, "")]
    cells += bank_links(template, sheets)
    cells += supporting_docs(template, inventory)
    book, refused = xlsm.patch(book, cells, protected(template, {c["sheet"] for c in cells}))
    return book, refused


def apply_edits(workbook: bytes, cells: list[dict]) -> tuple[bytes, list[dict]]:
    """An accountant's corrections on a finished workbook: the template's formulas stay protected."""
    template = template_bytes()
    return xlsm.patch(workbook, cells, protected(template, {c["sheet"] for c in cells}))


def execute(run_id: str, job_id: str, options: dict, pm, check=lambda: None) -> dict:
    started = time.time()

    def emit(stage, label, state="running", **counts):
        pm.send_event(run_id, {"type": "ai_precheck.progress", "job_id": job_id, "stage": stage, "state": state, "label": label, "counts": counts})

    job = pm.get_job(job_id)
    su = setup_from(options, job, EXTRA)
    if not su.entity:
        raise WpStop("Give the entity's name in the settings: documents are matched to it.")
    selected = [k for k in (options.get("workpapers") or C.KEYS) if k in C.KEYS]
    reader = Reader(run_id, purpose="New Zealand year-end electronic workpapers (CCH layout)", method=SKILL)
    emit("read", "Reading the documents from Google Drive")
    try:
        sources = gather(options.get("drive_link", ""))
    except SourceProblem as exc:
        raise WpStop(str(exc)) from exc
    check()
    X.classify(sources, reader)
    emit("read", f"{len(sources)} documents found", "done", documents=len(sources))
    emit("checked", "Reading every document in the folder and its subfolders")
    data = read_all(sources, reader, su)
    used = sum(1 for i in data["inventory"] if i["status"] == "used")
    emit("checked", f"{used} of {len(sources)} documents were read and used", "done")
    check()
    emit("compared", "Preparing the workpapers: " + ", ".join(selected))
    result = Ewp(su, data, selected).run()
    for p in data["problems"]:
        result["exceptions"].append({"id": f"read-{len(result['exceptions'])}", "wp": "", "code": "reading", "severity": "review", "text": p["text"],
                                     "next_evidence": "", "amount": None})
    emit("compared", result["status"], "done")
    check()
    emit("verified", "Writing the workbook (input cells only; formulas and macros untouched)")
    book, refused = write_workbook(result, data["inventory"])
    for r in refused:
        result["exceptions"].append({"id": f"refused-{r['sheet']}-{r['cell']}", "wp": r["sheet"], "code": "refused", "severity": "info",
                                     "text": f"{r['sheet']}!{r['cell']} wasn't written: {r['reason']}", "next_evidence": "", "amount": None})
    refused_ids = {(r["sheet"], r["cell"]) for r in refused}
    result["fields"] = [f for f in result["fields"] if (f["sheet"], f["cell"]) not in refused_ids]
    facts = (f"Status {result['status']}. " + "; ".join(f"{w['key']} {w['title']}: {w['status']}" for w in result["workpapers"]) + "\n"
             + "\n".join(f"{c['wp']} {c['label']}: workpaper {c['workpaper']}, ledger {c['ledger']}, variance {c['variance']}" for c in result["checks"])
             + "\nExceptions: " + "; ".join(f"[{x['severity']}] {x['wp']}: {x['text']}" for x in result["exceptions"][:25]))
    summary = reader.summary(facts) or f"{result['status']}: " + "; ".join(f"{w['key']} {w['status'].lower()}" for w in result["workpapers"] if w["key"] != "Workbench")
    result.update(summary=summary, inventory=data["inventory"], sources=[x.brief() for x in sources], template=C.TEMPLATE_NAME,
                  settings={"Entity": su.entity, "Entity type": su.extra.get("entity_type", ""), "IRD number": su.ird_number,
                            "Financial year start": su.fy_start, "Balance date": su.balance_date, "GST": su.extra.get("gst_status") or "We do GST",
                            "Prepared by": su.prepared_by, "Reviewed by": su.extra.get("reviewed_by", ""), "Tolerance": su.tolerance,
                            "Ledger used": (data["gl_source"] or {}).get("name", "")},
                  edits=[])
    emit("verified", "Workbook written", "done")
    from .. import memory
    from ..knowledge import Scope

    final = envelope(run_id, job_id, "ewp", result, book, reader, started, sources, result["counts"], summary, result["status"], RULES)
    memory.safely(memory.remember_wp, Scope.of(job), "wp_ewp", final["gst"])
    return final


def apply_request(workbook_b64: str, cells: list[dict]) -> dict:
    book, refused = apply_edits(base64.b64decode(workbook_b64), cells)
    return {"workbook_b64": base64.b64encode(book).decode(), "refused": refused}


__all__ = ["execute", "apply_request", "read_all", "write_workbook", "apply_edits", "q"]
