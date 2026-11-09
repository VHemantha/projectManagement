"""One WP Agent run: the GST reconciliation from the accountant's Drive link to the workpaper.

gather -> classify -> read -> reconcile -> summary -> workbook. Progress goes to the task card as it
happens; the result comes back in the same envelope as a guide or review run, with the reconciliation
("gst") and the workbook (base64) added. Nothing is written to Drive or posted anywhere."""
import base64
import logging
import time
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

from ..budget import cost_usd, empty_usage
from ..config import get_settings
from ..llm import model_id
from ..skills_loader import all_skills
from . import readers
from .ai import Reader
from .classify import KINDS, classify
from .engine import BASES, FREQ_MONTHS, Data, Recon, Setup
from .money import ZERO, amount, day, q
from .sources import SourceProblem, gather
from .workbook import build

logger = logging.getLogger(__name__)
# Short: AFIT Connect keeps it in a 40-character column. (AFIT spec 7 Nov 2026, amendments 8 Nov 2026.)
RULES_VERSION = "gst-1.0"
STATUS_VERDICT = {"Reconciled": "ready", "Reconciled subject to corrections": "ready_with_exceptions", "Unreconciled": "not_ready",
                  "Incomplete evidence": "not_ready"}


class GstStop(Exception):
    """A problem the accountant must fix before the run can go on (shown as it is)."""


def jsonable(value):
    if isinstance(value, Decimal):
        return str(q(value))
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [jsonable(v) for v in value]
    return value


def setup_from(options: dict, job: dict) -> Setup:
    raw = options.get("setup") or {}
    bd = day(raw.get("balance_date"))
    if bd is None:
        raise GstStop("Give the balance date (the financial year end) in the job settings.")
    start = day(raw.get("fy_start"))
    if start is None:  # a year: the day after the same date a year earlier
        try:
            year_ago = date(bd.year - 1, bd.month, bd.day)
        except ValueError:  # 29 February
            year_ago = date(bd.year - 1, bd.month, 28)
        start = year_ago + timedelta(days=1)
    if start >= bd:
        raise GstStop("The financial year start must be before the balance date.")
    basis = str(raw.get("basis") or "payments").lower()
    if basis not in BASES:
        raise GstStop("GST basis must be payments, invoice or hybrid.")
    freq = str(raw.get("frequency") or "two_monthly").lower()
    if freq not in FREQ_MONTHS:
        raise GstStop("Filing frequency must be monthly, two-monthly or six-monthly.")
    choices = options.get("choices") or {}
    accounts = raw.get("gst_accounts") or []
    if isinstance(accounts, str):
        accounts = [a.strip() for a in accounts.replace(";", ",").split(",") if a.strip()]
    return Setup(entity=raw.get("entity") or job.get("client_name") or "", balance_date=bd, fy_start=start, basis=basis, frequency=freq,
                 ird_number=str(raw.get("ird_number") or ""), software=str(raw.get("software") or "Xero"), currency=str(raw.get("currency") or "NZD"),
                 gl_version=str(raw.get("gl_version") or ""), gst_accounts=accounts, first_year=bool(raw.get("first_year")),
                 tolerance=abs(amount(raw.get("tolerance")) or ZERO), ar_gl_fallback=bool(choices.get("ar_gl_fallback")),
                 ap_gl_fallback=bool(choices.get("ap_gl_fallback")), prep_date=date.today(),
                 firm=str(options.get("firm") or "BDS Chartered Accountants Ltd"), prepared_by=str(options.get("prepared_by") or ""))


def read_all(sources, reader, su: Setup) -> tuple[Data, dict]:
    data, pyr = Data(), {}
    kinds = Counter()
    seen_versions: dict[str, str] = {}
    for src in sources:
        if src.version and src.version in seen_versions and not src.error:
            data.reading_problems.append({"text": f"{src.name} is a duplicate of {seen_versions[src.version]}: read once.", "minor": True, "source": src.sid})
            src.kind, src.kind_how = "other", "duplicate"
            continue
        if src.version:
            seen_versions[src.version] = src.name
        kinds[src.kind] += 1
        if src.error:
            data.reading_problems.append({"text": f"{src.name}: {src.error}", "minor": True, "source": src.sid,
                                          "evidence": "Upload it again as Excel, CSV or a text PDF."})
            continue
        k = src.kind
        problem = ""
        if k in ("ar_ageing", "ap_ageing"):
            got = readers.read_ageing(src, reader)
            side = "ar" if k == "ar_ageing" else "ap"
            current = getattr(data, side)
            if current is None:
                setattr(data, side, {**got, "source": src.sid})
            else:  # a second report for the same side: rows added (e.g. a revised export kept alongside)
                current["rows"] += got.get("rows", [])
                current["has_gst_column"] = current.get("has_gst_column") and got.get("has_gst_column")
            problem = got.get("problem", "")
        elif k == "general_ledger":
            got = readers.read_ledger(src, reader)
            data.gl += got["lines"]
            for acc, v in got["opening"].items():
                data.gl_opening[acc] = data.gl_opening.get(acc, ZERO) + v
            problem = got["problem"]
        elif k == "trial_balance":
            got = readers.read_trial_balance(src, reader)
            data.tb += got["rows"]
            problem = got["problem"]
        elif k == "journal_report":
            got = readers.read_journals(src, reader)
            data.journals += got["lines"]
            problem = got["problem"]
        elif k == "gst_returns":
            got = readers.read_returns(src, reader)
            data.returns += got["returns"]
            problem = got["problem"]
        elif k == "ird_statement":
            got = readers.read_ird(src, reader)
            data.ird += got["lines"]
            problem = got["problem"]
        elif k == "late_claims":
            got = readers.read_late_claims(src, reader)
            data.late_claims += got["items"]
            data.has_return_detail = True
            problem = got["problem"]
        elif k == "prior_year_recon":
            pyr = readers.read_prior_year(src, reader)
            if not pyr.get("problem"):
                data.prior_year = {**pyr, "source": f"{src.sid} {src.name}"}
            problem = pyr.get("problem", "")
        elif k == "customs":
            data.customs_sources.append(src.sid)
        if problem:
            data.reading_problems.append({"text": f"{src.name} ({KINDS.get(k, k)}): {problem}", "source": src.sid,
                                          "minor": k in ("journal_report", "late_claims", "xero_gst_recon"),
                                          "evidence": "A structured export (Excel or CSV) of the same report."})
    data.present = {k for k, n in kinds.items() if n}
    return data, pyr


def detected(data: Data, recon: dict, su: Setup) -> dict:
    """What the documents say about the job's settings, beside what the accountant gave."""
    ends = sorted({r["period_end"] for r in data.returns if r["period_end"] >= su.fy_start})
    gaps = sorted({(b.year - a.year) * 12 + b.month - a.month for a, b in zip(ends, ends[1:])})
    freq = {1: "monthly", 2: "two_monthly", 6: "six_monthly"}.get(gaps[0]) if len(gaps) == 1 else ""
    return {"return_periods": [e.isoformat() for e in ends], "frequency": freq, "gst_accounts": recon["ledger"]["gst_accounts"],
            "ar_control": recon["ledger"]["ar_accounts"], "ap_control": recon["ledger"]["ap_accounts"],
            "latest_return": ends[-1].isoformat() if ends else ""}


def code_summary(recon: dict) -> str:
    b = recon["bridge"]
    parts = [f"{recon['status']}."]
    if b["F"] is not None:
        parts.append(f"Expected GST control balance {q(b['E']):,} (A {q(b['A']):,} + B {q(b['B']):,} - C {q(b['C']):,} + D {q(b['D']):,}); "
                     f"adjusted GL {q(b['F']):,}; unexplained {q(b['unexplained']):,}.")
    if recon["counts"]["blocking"]:
        parts.append(f"{recon['counts']['blocking']} blocking exception(s) need evidence before it can be relied on.")
    if b["corrections"]:
        parts.append(f"It depends on proposed corrections of {q(b['corrections']):,} that are not posted.")
    return " ".join(parts)


def execute(run_id: str, job_id: str, options: dict, pm, check=lambda: None) -> dict:
    s, started = get_settings(), time.time()

    def emit(stage, label, state="running", **counts):
        pm.send_event(run_id, {"type": "ai_precheck.progress", "job_id": job_id, "stage": stage, "state": state, "label": label, "counts": counts})

    job = pm.get_job(job_id)
    su = setup_from(options, job)
    reader = Reader(run_id)
    emit("read", "Reading the documents from Google Drive")
    try:
        sources = gather(options.get("drive_link", ""), {"ar_ageing": options.get("ar_link", ""), "ap_ageing": options.get("ap_link", "")})
    except SourceProblem as exc:
        raise GstStop(str(exc)) from exc
    check()
    classify(sources, reader)
    emit("read", f"{len(sources)} documents found", "done", documents=len(sources))
    check()
    emit("checked", "Reading returns, IRD statements, the ledger and the ageing reports")
    data, prior = read_all(sources, reader, su)
    emit("checked", "Documents read", "done", returns=len(data.returns), ird_lines=len(data.ird), gl_lines=len(data.gl))
    check()
    emit("compared", "Reconciling: returns and settlements, receivables and payables, journals, late claims, import GST, payments")
    recon = Recon(su, data, reader).run()
    emit("compared", recon["status"], "done")
    check()
    facts = (code_summary(recon) + "\nExceptions: " + "; ".join(f"[{x['severity']}] {x['text']}" for x in recon["exceptions"][:25])
             + "\nPaused: " + ", ".join(recon[s_]["paused"]["report"] for s_ in ("ar", "ap") if recon[s_].get("paused")))
    summary = reader.summary(facts) or code_summary(recon)
    if recon["status"] != "Reconciled" and "reconciled." in summary.lower() and "unreconciled" not in summary.lower():
        summary = code_summary(recon)  # never a clean summary for a result that isn't clean
    settings_used = {"Entity": su.entity, "IRD number": su.ird_number, "Financial year start": su.fy_start, "Balance date": su.balance_date,
                     "GST basis": su.basis, "Filing frequency": su.frequency, "Software": su.software, "Currency": su.currency, "GL version": su.gl_version,
                     "GST control accounts": su.gst_accounts or recon["ledger"]["gst_accounts"], "First-year entity": "Yes" if su.first_year else "No",
                     "AR: GL analysis chosen": "Yes" if su.ar_gl_fallback else "No", "AP: GL analysis chosen": "Yes" if su.ap_gl_fallback else "No",
                     "Tolerance": su.tolerance}
    found = detected(data, recon, su)
    if found["frequency"] and found["frequency"] != su.frequency:
        recon["exceptions"].append({"id": "X-frequency", "code": "frequency", "severity": "review", "next_evidence": "Confirm the filing frequency.",
                                    "text": f"The returns are {found['frequency'].replace('_', '-')}, but the job settings say {su.frequency.replace('_', '-')}.",
                                    "refs": [], "amount": None})
    meta = {"run_id": run_id, "prep_date": su.prep_date, "versions": {"rules": RULES_VERSION,
                                                                      "skills": ", ".join(f"{n} {all_skills()[n].version}" for n in ("nz-gst-reconciliation", "gst-document-reading"))}}
    result = {"recon": recon, "summary": summary, "settings": settings_used, "detected": found, "prior_year": data.prior_year or prior,
              "sources": [x.brief() for x in sources]}
    emit("verified", "Writing the workpaper")
    workbook = build(result, su, meta)
    emit("verified", "Workpaper written", "done")

    calls = reader.usage
    totals = empty_usage()
    cost = 0.0
    for u in calls:
        for k in totals:
            totals[k] += u[k]
        cost += cost_usd(u["model"], u, s) if not u["model"].startswith("fake-") else 0.0
    all_input = totals["input"] + totals["cache_read"] + totals["cache_write"]
    counts = recon["counts"]
    gst = jsonable({"status": recon["status"], "summary": summary, "bridge": recon["bridge"], "settings": settings_used, "detected": found,
                    "paused": {side: recon[side]["paused"] for side in ("ar", "ap") if recon[side].get("paused")},
                    "exceptions": recon["exceptions"], "corrections": recon["corrections"],
                    "adjustments": [{k: v for k, v in a.items() if k != "evidence"} for a in recon["adjustments"]],
                    "periods": [{k: v for k, v in p.items() if k not in ("allocations", "versions")} for p in recon["periods"]],
                    "receivables": {k: v for k, v in recon["ar"].items() if k != "items"} | {"items": len(recon["ar"]["items"])},
                    "payables": {k: v for k, v in recon["ap"].items() if k != "items"} | {"items": len(recon["ap"]["items"])},
                    "imports": recon["imports"], "counts": counts, "sources": result["sources"], "options": {k: v for k, v in options.items() if k != "firm"},
                    "rules_version": RULES_VERSION})
    trail = {
        "read": {"label": f"{len(sources)} documents read from Drive", "documents": len(sources), "changed": 0, "removed": [], "images_read": 0, "detail": []},
        "checked": {"label": f"{len(data.returns)} returns, {len(data.ird)} IRD lines, {len(data.gl)} ledger lines", "detail": []},
        "compared": {"label": f"A {q(recon['bridge']['A']):,}; B {q(recon['bridge']['B']):,}; C {q(recon['bridge']['C']):,}; D {q(recon['bridge']['D']):,}",
                     "detail": []},
        "judged": {"label": recon["status"], "how": "code", "detail": []},
        "verified": {"label": f"{counts['blocking']} blocking and {counts['review']} review exceptions", "evidence": 0, "detail": []},
    }
    return {
        "run_id": run_id, "job_id": job_id, "mode": "gst", "status": "complete", "verdict": STATUS_VERDICT[recon["status"]],
        "readiness": recon["status"][:40], "summary": summary[:400],
        "coverage": {"addressed": len(recon["adjustments"]) + len(recon["corrections"]), "total": len(recon["adjustments"]) + len(recon["corrections"]) + counts["review"]},
        "counts": {"high": counts["blocking"], "medium": counts["review"], "low": sum(1 for x in recon["exceptions"] if x["severity"] == "info")},
        "direction_items": [], "findings": [], "evidence": [], "precheck_type": "gst", "trail": trail, "skipped": [],
        "usage": {"calls": calls, "totals": totals, "model_calls": len(calls), "reader_calls": 0, "cost_usd": round(cost, 6),
                  "cache_share": round(totals["cache_read"] / all_input, 3) if all_input else 0.0, "reused_answers": 0,
                  "budget": {"reading_calls": s.gst_max_reading_calls}},
        "models": {"gst": model_id("gst", s)},
        "versions": {"prompt": RULES_VERSION, "parser": s.parser_version, "skills": {n: sk.version for n, sk in all_skills().items()}},
        "knowledge_ids": [], "demo": s.llm_mode == "fake", "duration_s": round(time.time() - started, 1),
        "gst": gst, "workbook_b64": base64.b64encode(workbook).decode(),
    }
