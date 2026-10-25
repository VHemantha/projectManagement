"""The preparation guide: after the pre-check, an eight-section briefing for the accountant preparing
this year's financial statements (AFIT's agreed structure, 21 Oct 2026): job snapshot, significant
events and alerts, prior-year continuity, priority risks, starting sequence, judgments, queries and
a completion checklist, within one to one-and-a-half A4 pages. What this year's guide hands on
(its roll-forward list, events still to confirm, checks left open) reaches next year's guide for the
same client, and code makes sure each one is taken up in its prior-year section.

One Opus call. The input is the pre-check's own (every line with an id: questionnaire, last year's
statements and trial balance, workpapers, this year's documents, bank exports and the general ledger
summarised by code, code checks, earlier corrections), plus the latest pre-check's result. Code checks
the answer: only real sources; any amount not in the input is flagged; an event called confirmed with
no document behind it becomes suspected; every event is followed through to the work sequence, the
queries and the checklist, or flagged; a client query that repeats an outstanding request is dropped.
"""
import json
import re

from langchain_core.messages import HumanMessage

from . import precheck as P
from .budget import usage_from_message
from .config import Settings
from .llm import get_model, model_id, stop_reason, text_of
from .prompting import system_message
from .skills_loader import get_skill
from .textutil import clip_words, sha

SKILL = "nz-preparation-guide"
FORMAT = 2  # the eight-section guide; format 1 was a flat list of steps

PRIOR_KINDS = ["error", "reviewer_point", "unresolved", "policy", "balance"]
CHECK_STATUSES = ["done", "open", "na"]
# About one to one-and-a-half A4 pages; past this the guide is flagged as too long.
MAX_WORDS = 900

_STR = {"type": "string"}
# Ids as one comma-separated string ("B1, G2.1"), not an array, and the three query lists as one
# list: the API compiles the answer shape into a grammar, and with an array of ids on every item
# of eight sections it refused it as too large (21 Oct 2026).
_IDS = _STR
QUERY_TO = ["manager", "client", "outstanding"]


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


SCHEMA = _obj({
    "snapshot": _obj({"activities": _STR, "assets_and_funding": _STR, "records": _STR, "bookkeeping": _STR, "period": _STR, "sources": _IDS}),
    "events": {"type": "array", "items": _obj({
        "id": _STR, "event": _STR, "status": {"type": "string", "enum": ["confirmed", "suspected"]},
        "why_it_matters": _STR, "action": _STR, "effect": _STR, "sources": _IDS})},
    "prior_year": {"type": "array", "items": _obj({
        "item": _STR, "kind": {"type": "string", "enum": PRIOR_KINDS}, "follow_through": _STR, "sources": _IDS})},
    "risks": {"type": "array", "items": _obj({
        "area": _STR, "what_could_be_wrong": _STR, "examine": _STR, "evidence": _STR, "events": _IDS, "sources": _IDS})},
    "sequence": {"type": "array", "items": _obj({
        "step": _STR, "depends_on": _STR, "can_start_now": {"type": "boolean"}, "escalate": _STR, "events": _IDS, "sources": _IDS})},
    "judgments": {"type": "array", "items": _obj({
        "judgment": _STR, "evidence": _STR, "manager_approval": {"type": "boolean"}, "reference": _STR, "events": _IDS, "sources": _IDS})},
    "queries": {"type": "array", "items": _obj({
        "to": {"type": "string", "enum": QUERY_TO}, "text": _STR, "events": _IDS, "sources": _IDS})},
    "checklist": {"type": "array", "items": _obj({"check": _STR, "status": {"type": "string", "enum": CHECK_STATUSES}, "events": _IDS})},
    "roll_forward": {"type": "array", "items": _obj({"item": _STR, "why": _STR, "sources": _IDS})},
})

ANSWER = """Answer in the JSON shape given: the eight sections of the preparation guide skill (snapshot, events, prior_year, risks, sequence, judgments, queries, checklist), within one to one-and-a-half A4 pages (about 500 to 800 words in all). Use only figures, names and dates in the input; mark an event confirmed only when a document shows it; give "sources" as the ids each item rests on and "events" as the event ids it follows through (E1, E2, ...), each as one comma-separated string ("B1, G2.1"; "" for none); give every query with "to": manager, client or outstanding; list in "roll_forward" what next year's preparer must pick up; take up every rolled-forward (Y) line in "prior_year"."""

# Words kept per field: about half as much again as the skill asks for, so an answer that runs a
# little long is kept whole rather than cut mid-sentence (the page limit is checked on the total).
LIMITS = {"snapshot": 45, "event": 45, "why_it_matters": 40, "action": 55, "effect": 40, "item": 35, "follow_through": 35,
          "area": 8, "what_could_be_wrong": 35, "examine": 35, "evidence": 35, "step": 45, "depends_on": 20, "escalate": 30,
          "judgment": 35, "reference": 25, "question": 45, "check": 30, "why": 35}
MAX_ITEMS = {"events": 7, "prior_year": 6, "risks": 5, "sequence": 12, "judgments": 6, "manager": 6, "client": 8, "outstanding": 12, "checklist": 14, "roll_forward": 8}


def system_text() -> str:
    return P.system_text() + f"\n\n# Skill: {get_skill(SKILL).name}\n{get_skill(SKILL).body}"


def skill_version() -> str:
    return get_skill(SKILL).version


def with_precheck(body: str, last: dict | None, rolled: list[dict] | None = None, index: dict | None = None) -> str:
    """The pre-check input with the pre-check's own result added: what is still requested (the
    outstanding requests, and the steps that wait for them) and what it noted for the preparer;
    and what the client's earlier guide handed on to this year (Y lines, added to `index`)."""
    lines = []
    if rolled:
        lines.append("\n== ROLLED FORWARD FROM THE CLIENT'S EARLIER GUIDE (take up each one in prior_year) ==")
        for n, r in enumerate(rolled[:20], start=1):
            yid = f"Y{n}"
            if index is not None:
                index[yid] = {"kind": "rolled_forward", "row": r}
            kind = {"roll_forward": "handed on", "open_event": "event not confirmed", "open_check": "check left open"}.get(r.get("kind"), "")
            lines.append(f"{yid} | from {r.get('from', '')} ({r.get('period') or 'earlier year'}) | {kind} | {r.get('item', '')}"
                         + (f" | {r['why']}" if r.get("why") else ""))
    lines.append("\n== THE LATEST PRE-CHECK'S RESULT ==")
    if not last:
        lines.append("(no pre-check has finished for this task yet)")
    else:
        nature = (last.get("business_nature") or {}).get("label") or ""
        if nature:
            lines.append(f"Business nature: {nature}")
        for r in last.get("requests") or []:
            lines.append(f"Still requested from the client: {r.get('group', '')} — {r.get('item', '')}")
        for n in last.get("preparer_notes") or []:
            lines.append(f"Note for the preparer: {n.get('text', '')}")
    base = body.rsplit("\n" + P.ANSWER, 1)[0]  # the pre-check's answer instructions do not apply here
    return base + "\n".join(lines) + "\n\n" + ANSWER


def cache_key(client_id: str, job_id: str, body: str, settings: Settings) -> str:
    return sha("guide", FORMAT, client_id, job_id, model_id("precheck", settings), settings.prompt_version, skill_version(),
               *sorted(f"{k}={v}" for k, v in P.skill_versions().items()), body)


def call_model(body: str, settings: Settings) -> tuple[dict, dict]:
    message = get_model("precheck", settings).invoke(
        [system_message("precheck", system_text(), settings), HumanMessage(content=body)],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    usage = usage_from_message(message)
    if stop_reason(message) in ("refusal", "max_tokens"):
        raise P.Unusable(f"The guide model stopped early ({stop_reason(message)}).", usage)
    try:
        return json.loads(text_of(message)), usage
    except json.JSONDecodeError as exc:
        raise P.Unusable("The guide model's answer was not valid JSON.", usage) from exc


# --- code checks ------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _ids(value) -> list[str]:
    """Ids as the model gives them: "B1, G2.1" (or a list)."""
    parts = value if isinstance(value, list) else re.split(r"[,;\s]+", str(value or ""))
    return [p for p in dict.fromkeys(str(x).strip().strip(".") for x in parts) if p]


def _queries(raw) -> dict:
    """The model's one list of queries ({to, text}) as the three lists the guide shows."""
    if isinstance(raw, dict):  # already split
        return raw
    out = {"manager": [], "client": [], "outstanding": []}
    for q in raw or []:
        to = q.get("to") if q.get("to") in QUERY_TO else "client"
        out[to].append({("item" if to == "outstanding" else "question"): q.get("text", ""), "events": q.get("events"), "sources": q.get("sources")})
    return out


def clean(raw: dict, index: dict, known_text: str) -> dict:
    known = P.known_numbers(known_text)

    def sources(ids) -> list[str]:
        return [i for i in _ids(ids) if i in index][:6]

    def text(value, field: str) -> str:
        return clip_words(" ".join(str(value or "").split()), LIMITS[field])

    def figures(item: dict, *fields: str) -> list[str]:
        return [] if all(P.figures_ok(item[f], known) for f in fields) else ["figure_not_in_documents"]

    # 2. Events first: their ids are renumbered E1, E2, ... and every later reference is mapped.
    events, renumber, seen = [], {}, set()
    for e in (raw.get("events") or [])[: MAX_ITEMS["events"]]:
        what = text(e.get("event"), "event")
        if not what or _norm(what) in seen:
            continue
        seen.add(_norm(what))
        eid = f"E{len(events) + 1}"
        renumber[str(e.get("id", "")).strip()] = eid
        item = {"id": eid, "event": what, "status": "confirmed" if e.get("status") == "confirmed" else "suspected",
                "why_it_matters": text(e.get("why_it_matters"), "why_it_matters"), "action": text(e.get("action"), "action"),
                "effect": text(e.get("effect"), "effect"), "sources": sources(e.get("sources")), "flags": []}
        if item["status"] == "confirmed" and not item["sources"]:
            item["status"] = "suspected"  # confirmed means documented
            item["flags"].append("confirmation_not_documented")
        item["flags"] += figures(item, "event", "why_it_matters", "action", "effect")
        events.append(item)

    def refs(ids) -> list[str]:
        return list(dict.fromkeys(renumber[i] for i in _ids(ids) if i in renumber))

    def rows(items, limit: int, fields: dict, extra=None) -> list[dict]:
        """Clean a list: text fields clipped, duplicates and empty rows dropped, sources and event
        references checked, figures checked."""
        out, dup = [], set()
        first = next(iter(fields))
        for r in (items or [])[:limit]:
            row = {f: text(r.get(f), limit_name) for f, limit_name in fields.items()}
            if not row[first] or _norm(row[first]) in dup:
                continue
            dup.add(_norm(row[first]))
            row.update(extra(r) if extra else {})
            row["events"] = refs(r.get("events"))
            if "sources" in r:
                row["sources"] = sources(r.get("sources"))
            row["flags"] = figures(row, *fields)
            out.append(row)
        return out

    snap = raw.get("snapshot") or {}
    snapshot = {f: text(snap.get(f), "snapshot") for f in ("activities", "assets_and_funding", "records", "bookkeeping", "period")}
    if not snapshot["period"]:
        snapshot["period"] = "Not established from the documents: confirm the balance date and the period to prepare."
    snapshot["sources"] = sources(snap.get("sources"))
    snapshot["flags"] = figures(snapshot, "activities", "assets_and_funding", "records", "bookkeeping", "period")

    prior = rows(raw.get("prior_year"), MAX_ITEMS["prior_year"], {"item": "item", "follow_through": "follow_through"},
                 lambda r: {"kind": r.get("kind") if r.get("kind") in PRIOR_KINDS else "unresolved"})
    risks = rows(raw.get("risks"), MAX_ITEMS["risks"],
                 {"what_could_be_wrong": "what_could_be_wrong", "area": "area", "examine": "examine", "evidence": "evidence"})
    sequence = rows(raw.get("sequence"), MAX_ITEMS["sequence"], {"step": "step", "depends_on": "depends_on", "escalate": "escalate"},
                    lambda r: {"can_start_now": bool(r.get("can_start_now"))})
    judgments = rows(raw.get("judgments"), MAX_ITEMS["judgments"], {"judgment": "judgment", "evidence": "evidence", "reference": "reference"},
                     lambda r: {"manager_approval": bool(r.get("manager_approval"))})
    q = _queries(raw.get("queries"))
    outstanding = rows(q.get("outstanding"), MAX_ITEMS["outstanding"], {"item": "item"})
    asked = {_norm(o["item"]) for o in outstanding}
    # A client question that only repeats an outstanding request is not asked twice.
    client = [c for c in rows(q.get("client"), MAX_ITEMS["client"], {"question": "question"}) if _norm(c["question"]) not in asked]
    manager = rows(q.get("manager"), MAX_ITEMS["manager"], {"question": "question"})
    checklist = rows(raw.get("checklist"), MAX_ITEMS["checklist"], {"check": "check"},
                     lambda r: {"status": r.get("status") if r.get("status") in CHECK_STATUSES else "open"})

    roll_forward = rows(raw.get("roll_forward"), MAX_ITEMS["roll_forward"], {"item": "item", "why": "why"})
    for r in roll_forward:
        r.pop("events", None)
    # What the earlier guide handed on is never dropped: a Y line the answer did not take up is
    # added to the prior-year section for the accountant to settle.
    taken = {s for p in prior for s in p.get("sources", [])}
    for yid, entry in index.items():
        if entry["kind"] == "rolled_forward" and yid not in taken:
            r = entry["row"]
            prior.append({"item": text(r.get("item"), "item"), "follow_through": f"Rolled forward from {r.get('from', 'the earlier job')}: confirm whether it is resolved this year.",
                          "kind": "unresolved", "events": [], "sources": [yid], "flags": ["added_by_code"]})

    # Every event is followed through: a step to deal with it, a line on the checklist, and for a
    # suspected event a question to confirm it.
    def mentions(items) -> set[str]:
        return {e for it in items for e in it.get("events", [])}

    in_sequence, in_checklist, in_queries = mentions(sequence), mentions(checklist), mentions(manager + client + outstanding)
    for e in events:
        missing = [part for part, ok in (("sequence", e["id"] in in_sequence), ("checklist", e["id"] in in_checklist),
                                         ("query", e["status"] == "confirmed" or e["id"] in in_queries)) if not ok]
        e["not_followed_through"] = missing
        if missing:
            e["flags"].append("not_followed_through")

    return {"format": FORMAT, "snapshot": snapshot, "events": events, "prior_year": prior, "risks": risks, "sequence": sequence,
            "judgments": judgments, "queries": {"manager": manager, "client": client, "outstanding": outstanding}, "checklist": checklist,
            "roll_forward": roll_forward}


def word_count(guide: dict) -> int:
    def walk(v) -> int:
        if isinstance(v, str):
            return len(v.split())
        if isinstance(v, dict):
            return sum(walk(x) for k, x in v.items() if k not in ("sources", "events", "flags", "id", "status", "kind", "not_followed_through"))
        if isinstance(v, list):
            return sum(walk(x) for x in v)
        return 0
    return walk({k: guide.get(k, []) for k in ("snapshot", "events", "prior_year", "risks", "sequence", "judgments", "queries", "checklist", "roll_forward")})


def size(guide: dict) -> int:
    """How many items the guide holds (old guides: their steps)."""
    if guide.get("format") != FORMAT:
        return len(guide.get("steps", []))
    q = guide["queries"]
    return sum(len(guide.get(k, [])) for k in ("events", "prior_year", "risks", "sequence", "judgments", "checklist", "roll_forward")) + sum(len(v) for v in q.values())


def flagged(guide: dict) -> int:
    """How many items code flagged (an amount not in the documents, an event not followed through...)."""
    if guide.get("format") != FORMAT:
        return sum(1 for s in guide.get("steps", []) if s.get("flags"))
    items = [guide["snapshot"]] + [x for k in ("events", "prior_year", "risks", "sequence", "judgments", "checklist", "roll_forward") for x in guide.get(k, [])]
    return sum(1 for x in items + [q for v in guide["queries"].values() for q in v] if x.get("flags"))


def assemble(cleaned: dict, index: dict) -> tuple[dict, dict]:
    evidence: dict[str, dict] = {}

    def ev(e: dict | None) -> str | None:
        if not e:
            return None
        evidence[e["id"]] = e
        return e["id"]

    def view(sid: str) -> dict:
        item = index[sid]
        if item["kind"] == "rolled_forward":
            r = item["row"]
            return {"id": sid, "label": f"Rolled forward from {r.get('from', 'an earlier job')}: {clip_words(r.get('item', ''), 14)}", "evidence_id": None}
        if item["kind"] == "lesson":  # an earlier correction: a reviewer point carried forward
            lesson = item["lesson"]
            return {"id": sid, "label": f"Earlier correction: {clip_words(lesson.get('note') or lesson.get('item', ''), 14)}", "evidence_id": None}
        return P._source_view(sid, index, ev)

    def with_views(v):
        if isinstance(v, dict):
            return {k: ([view(i) for i in x] if k == "sources" else with_views(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [with_views(x) for x in v]
        return v

    out = with_views(cleaned)
    events = out["events"]
    suspected = sum(1 for e in events if e["status"] == "suspected")
    open_checks = sum(1 for c in out["checklist"] if c["status"] == "open")
    words = word_count(out)
    parts = [f"{len(events)} significant event{'s' if len(events) != 1 else ''}" + (f" ({suspected} to confirm)" if suspected else ""),
             f"{len(out['risks'])} priority risk{'s' if len(out['risks']) != 1 else ''}",
             f"{open_checks} open check{'s' if open_checks != 1 else ''}"]
    out["summary"] = "; ".join(filter(None, (out["snapshot"]["activities"], out["snapshot"]["period"])))
    out["words"] = words
    out["flags"] = ["longer_than_a_page_and_a_half"] if words > MAX_WORDS else []
    out["decision"] = {"state": "guide", "label": "Preparation guide", "reason": "; ".join(parts) + "."}
    out["evidence"] = {k: {f: e[f] for f in ("file_name", "location", "quote", "drive_url")} for k, e in evidence.items()}
    return out, evidence
