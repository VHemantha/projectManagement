"""What each agent concluded, kept in the knowledge store so Ask can answer questions about it (AFIT,
10 Nov 2026): the pre-check's result, the preparation guide and the WP Agent's GST reconciliation,
each as its own kind of entry ("precheck_result", "guide", "wp_gst").

The same technique as the review's record (review.remember): every fact becomes one short entry in
plain words, tagged with the task card's place (team / vendor / project / task) and its kind, then
embedded. A search filters on those tags first, so a question about one task never reaches another
client's results. A new run replaces that kind's entries for the task; an unchanged result (same
fingerprint) is not stored again.

Results are remembered when their run finishes, and again from the PM application's record when a
question is asked (runs from before this was added, or a store restored from an older backup).
"""
import json
import logging

from .embeddings import get_embedder
from .knowledge import Scope, get_knowledge
from .textutil import sha

logger = logging.getLogger(__name__)
KINDS = ("precheck_result", "guide", "wp_gst")
MAX_ENTRIES = 600


def _t(value) -> str:
    return " ".join(str(value or "").split())


def _money(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"({abs(n):,.2f})" if n < 0 else f"{n:,.2f}"


def remember(scope: Scope, kind: str, entries: list[dict], fingerprint_of) -> int:
    """Store one agent's result for a task, replacing what it held before. entries: [{"key", "text",
    "meta"?}]. Returns how many were stored (0 when the same result is already there)."""
    if kind not in KINDS or not entries:
        return 0
    kn = get_knowledge()
    digest = sha(json.dumps(fingerprint_of, sort_keys=True, default=str))[:16]
    held = kn.get(scope, source_types=[kind], limit=1)
    if held and held[0].get("digest") == digest:
        return 0
    old = kn.get(scope, source_types=[kind])
    kn.delete([e["id"] for e in old])
    entries = [e for e in entries if _t(e["text"])][:MAX_ENTRIES]
    vectors = get_embedder().embed([e["text"] for e in entries])
    kn.put(scope, kind, [{"id": f"{scope.task}:{kind}:{e['key']}", "text": _t(e["text"]), "embedding": v,
                          "meta": {**e.get("meta", {}), "digest": digest, "ref": e.get("ref", "")}} for e, v in zip(entries, vectors)])
    return len(entries)


def safely(fn, *args) -> int:
    """Remembering never stops a run or an answer."""
    try:
        return fn(*args)
    except Exception:
        logger.exception("Could not keep %s in the knowledge store", getattr(fn, "__name__", "a result"))
        return 0


# --- the pre-check -----------------------------------------------------------------------------------

DECISIONS = {"request": "to request from the client", "already_provided": "already provided", "not_needed": "not needed"}


def precheck_entries(p: dict) -> list[dict]:
    out = []
    d = p.get("decision") or {}
    nature = p.get("business_nature") or {}
    requests = p.get("requests") or []
    out.append({"key": "summary", "text": f"Pre-check result: {d.get('label', '')}. {d.get('reason', '')} Business nature: "
                                         f"{nature.get('label') or nature.get('type') or 'not decided'}. {len(requests)} item(s) to request from the client."})
    if nature:
        out.append({"key": "nature", "text": f"Pre-check: business nature {nature.get('label') or nature.get('type', '')}. "
                                            f"{nature.get('summary', '')} Reasoning: {nature.get('reasoning', '')}"})
    for group, rows in (("request", requests), ("already_provided", p.get("provided") or []), ("not_needed", p.get("not_needed") or [])):
        for n, r in enumerate(rows, start=1):
            out.append({"key": f"{group}-{n}", "ref": r.get("item", "")[:60],
                        "text": f"Pre-check item {DECISIONS[group]}: {r.get('item', '')} ({r.get('group', '')}). "
                                f"{'Priority ' + r['priority'] + '. ' if r.get('priority') else ''}Reason: {r.get('reason', '')}"})
    for n, q in enumerate(p.get("accountant_questions") or [], start=1):
        out.append({"key": f"question-{n}", "text": f"Pre-check question for the accountant: {q.get('question') or q.get('text') or q}"})
    for n, note in enumerate(p.get("preparer_notes") or [], start=1):
        out.append({"key": f"note-{n}", "text": f"Pre-check note for the preparer: {note.get('text') if isinstance(note, dict) else note}"})
    for n, k in enumerate(p.get("key_documents") or [], start=1):
        files = ", ".join(f.get("name", "") for f in k.get("files") or [])
        out.append({"key": f"keydoc-{n}", "text": f"Pre-check key document {k.get('label', '')}: {'found' if k.get('found') else 'not found'}"
                                                  f"{' — ' + files if files else ''}. {k.get('note', '')}"})
    for n, c in enumerate(p.get("checks") or [], start=1):
        out.append({"key": f"check-{n}", "text": f"Pre-check check by code: {c.get('label', '')} — {'passed' if c.get('passed') else 'failed'}. {c.get('detail', '')}"})
    for n, b in enumerate(p.get("bank") or [], start=1):
        out.append({"key": f"bank-{n}", "text": f"Pre-check bank account {b.get('account', '')}: from {b.get('from', '')} to {b.get('to', '')}, "
                                                f"opening {_money(b.get('opening'))}, closing {_money(b.get('closing'))}."})
    email = p.get("email") or {}
    if email.get("subject"):
        out.append({"key": "email", "text": f"Pre-check drafted email to the client (never sent): {email['subject']}. {_t(email.get('body', ''))[:600]}"})
    return out


def remember_precheck(scope: Scope, p: dict) -> int:
    return remember(scope, "precheck_result", precheck_entries(p), p) if p else 0


# --- the preparation guide ----------------------------------------------------------------------------

def guide_entries(g: dict) -> list[dict]:
    out = []
    d = g.get("decision") or {}
    out.append({"key": "summary", "text": f"Preparation guide: {g.get('summary', '')} {d.get('reason', '')}"})
    snap = g.get("snapshot") or {}
    if snap:
        out.append({"key": "snapshot", "text": "Guide job snapshot: " + "; ".join(f"{k.replace('_', ' ')}: {snap.get(k, '')}" for k in
                                                                              ("activities", "assets_and_funding", "records", "bookkeeping", "period") if snap.get(k))})
    for e in g.get("events") or []:
        out.append({"key": f"event-{e.get('id', '')}", "ref": e.get("id", ""),
                    "text": f"Guide significant event {e.get('id', '')} ({e.get('status', '')}): {e.get('event', '')} Why it matters: "
                            f"{e.get('why_it_matters', '')} Action: {e.get('action', '')} Effect: {e.get('effect', '')}"})
    for n, x in enumerate(g.get("prior_year") or [], start=1):
        out.append({"key": f"prior-{n}", "text": f"Guide prior-year continuity ({x.get('kind', '')}): {x.get('item', '')} Follow through: {x.get('follow_through', '')}"})
    for n, x in enumerate(g.get("risks") or [], start=1):
        out.append({"key": f"risk-{n}", "text": f"Guide priority risk — {x.get('area', '')}: {x.get('what_could_be_wrong', '')} Examine: {x.get('examine', '')} "
                                                f"Evidence: {x.get('evidence', '')}"})
    for n, x in enumerate(g.get("sequence") or [], start=1):
        out.append({"key": f"step-{n}", "text": f"Guide starting sequence, step {n}: {x.get('step', '')} Depends on: {x.get('depends_on', '') or 'nothing'}. "
                                                f"{'Can start now.' if x.get('can_start_now') else 'Cannot start yet.'} {x.get('escalate', '')}"})
    for n, x in enumerate(g.get("judgments") or [], start=1):
        out.append({"key": f"judgment-{n}", "text": f"Guide judgment: {x.get('judgment', '')} Evidence: {x.get('evidence', '')}"
                                                    f"{' Needs manager approval.' if x.get('manager_approval') else ''} {x.get('reference', '')}"})
    queries = g.get("queries") or {}
    for who in ("manager", "client", "outstanding"):
        for n, x in enumerate(queries.get(who) or [], start=1):
            out.append({"key": f"query-{who}-{n}", "text": f"Guide query ({who}): {x.get('question') or x.get('item', '')}"})
    for n, x in enumerate(g.get("checklist") or [], start=1):
        out.append({"key": f"check-{n}", "text": f"Guide completion checklist ({x.get('status', '')}): {x.get('check', '')}"})
    for n, x in enumerate(g.get("roll_forward") or [], start=1):
        out.append({"key": f"roll-{n}", "text": f"Guide roll-forward to next year: {x.get('item', '')} Why: {x.get('why', '')}"})
    for n, x in enumerate(g.get("steps") or [], start=1):  # a guide written before 21 Oct 2026
        out.append({"key": f"legacy-{n}", "text": f"Guide step {n} ({x.get('area', '')}): {x.get('step', '')} Check: {x.get('check', '')}"
                                                  f"{' Waits on the client.' if x.get('waits_on_client') else ''}"})
    return out


def remember_guide(scope: Scope, g: dict) -> int:
    return remember(scope, "guide", guide_entries(g), g) if g else 0


# --- the WP Agent's GST reconciliation ------------------------------------------------------------------

BRIDGE = [("A", "GST principal outstanding at balance date (component A)"), ("A_current", "of which current-year return periods"),
          ("A_prior", "of which prior-year return periods"), ("B", "GST on unpaid receivables not yet returned (component B, added)"),
          ("C", "GST on unpaid payables not yet claimed (component C, deducted)"), ("D", "other supported differences (component D)"),
          ("E", "expected GST control balance E = A + B - C + D"), ("reported", "reported GL GST control balance"),
          ("corrections", "proposed correction effects (not posted)"), ("F", "adjusted GST control balance F"),
          ("unexplained", "unexplained difference F - E")]


def gst_entries(g: dict) -> list[dict]:
    out = []
    b = g.get("bridge") or {}
    settings = g.get("settings") or {}
    when = settings.get("Balance date", "")
    out.append({"key": "summary", "text": f"WP Agent GST reconciliation at {when} ({settings.get('GST basis', '')} basis): status {g.get('status', '')}. "
                                         f"{g.get('summary', '')}"})
    out.append({"key": "bridge", "text": "WP Agent GST reconciliation bridge: " + "; ".join(f"{label} {_money(b.get(k))}" for k, label in BRIDGE if k in b)})
    for k, label in BRIDGE:
        if k in b:
            out.append({"key": f"bridge-{k}", "ref": k, "text": f"WP Agent GST reconciliation: {label} is {_money(b.get(k))}."})
    if settings:
        out.append({"key": "settings", "text": "WP Agent job settings used: " + "; ".join(f"{k}: {', '.join(v) if isinstance(v, list) else v}"
                                                                                       for k, v in settings.items() if v not in ("", None, []))})
    for p in g.get("periods") or []:
        out.append({"key": f"period-{p.get('period_end')}", "ref": p.get("period_end", ""),
                    "text": f"WP Agent GST return period ending {p.get('period_end')}{' (prior-year period)' if p.get('prior_year') else ''}: net GST "
                            f"{_money(p.get('net'))}, outstanding at balance date {_money(p.get('outstanding_bd'))}, settled after balance date "
                            f"{_money(p.get('settled_after'))}, {p.get('standing', '')}; filed {p.get('filed') or 'date not known'}, due {p.get('due', '')}."})
    for side, name in (("receivables", "Receivables (G1)"), ("payables", "Payables (M1)")):
        s = g.get(side) or {}
        if not s:
            continue
        ag = s.get("agreement") or {}
        out.append({"key": side, "text": f"WP Agent {name}: source {s.get('source') or 'none'}; in the bridge {_money(s.get('total'))}; GST identified "
                                         f"{_money(s.get('identified'))}. {s.get('basis_note', '')}"
                                         + (f" Ageing total {_money(ag.get('ageing_total'))} against GL control {_money(ag.get('gl_control'))}, difference "
                                            f"{_money(ag.get('difference'))}." if ag else "")})
        for n, it in enumerate(s.get("items") or [], start=1):
            out.append({"key": f"{side}-{n}", "ref": it.get("contact", "")[:60],
                        "text": f"WP Agent {name} line: {it.get('contact', '')} {it.get('ref', '')} balance {_money(it.get('balance'))}, GST "
                                f"{_money(it.get('gst'))} — {it.get('category', '')}; {'included' if it.get('included') else 'excluded: ' + it.get('reason', '')}."})
    for side, p in (g.get("paused") or {}).items():
        out.append({"key": f"paused-{side}", "text": f"WP Agent paused the {p.get('report', side)} side: {_t(p.get('message', ''))[:400]}"})
    for x in g.get("exceptions") or []:
        out.append({"key": f"exception-{x.get('id')}", "ref": x.get("id", ""),
                    "text": f"WP Agent exception ({x.get('severity', '')}): {x.get('text', '')} Next evidence needed: {x.get('next_evidence', '') or '—'}"})
    for c in g.get("corrections") or []:
        lines = "; ".join(f"Dr {ln['account']} {_money(ln['debit'])}" if float(ln.get("debit") or 0) else f"Cr {ln['account']} {_money(ln['credit'])}"
                          for ln in c.get("lines") or [])
        out.append({"key": f"correction-{c.get('id')}", "ref": c.get("id", ""),
                    "text": f"WP Agent proposed correction (not posted): {c.get('title', '')} — {lines}; GST control effect {_money(c.get('gst_effect'))}. "
                            f"{c.get('explanation', '')}"})
    for a in g.get("adjustments") or []:
        out.append({"key": f"adjustment-{a.get('id')}", "ref": a.get("id", ""),
                    "text": f"WP Agent adjustment {a.get('category', '')}: {_money(a.get('effect'))} — {a.get('status', '')}"
                            f"{'' if a.get('included', True) else ' (not in the bridge)'}. {a.get('description', '')}"
                            f"{' Cleared in the later return for ' + a['subsequent_return'] + '.' if a.get('subsequent_return') else ''}"})
    imports = g.get("imports") or {}
    if imports.get("note"):
        out.append({"key": "imports", "text": f"WP Agent import GST check: {imports['note']}"})
    for n, it in enumerate(imports.get("items") or [], start=1):
        out.append({"key": f"import-{n}", "text": f"WP Agent import GST check: {it.get('description', '')} {_money(it.get('amount'))} — {it.get('finding', '')}. "
                                                  f"{it.get('treatment', '')}"})
    for s_ in g.get("sources") or []:
        out.append({"key": f"source-{s_.get('sid')}", "text": f"WP Agent read {s_.get('name', '')} as {str(s_.get('kind', '')).replace('_', ' ')}"
                                                             f"{' — problem: ' + s_['error'] if s_.get('error') else ''}."})
    return out


def remember_gst(scope: Scope, g: dict) -> int:
    return remember(scope, "wp_gst", gst_entries(g), g) if g else 0


def sync_from_job(job: dict) -> dict:
    """Keep the store in step with the PM application's record of the task's latest results."""
    scope = Scope.of(job)
    return {"precheck_result": safely(remember_precheck, scope, job.get("last_precheck_result") or {}),
            "guide": safely(remember_guide, scope, job.get("last_guide") or {}),
            "wp_gst": safely(remember_gst, scope, job.get("last_gst") or {})}
