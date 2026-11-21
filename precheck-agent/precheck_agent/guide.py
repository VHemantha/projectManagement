"""The preparation guide: after the pre-check, a briefing for the accountant preparing this year's
financial statements.

Format 3 (AFIT, 21 Nov 2026): the guide gives points, never questions; it opens with the job's areas
of caution as a summary; the significant events are worked out but not shown as a section of their own
(they are followed through into the steps, the points and the checklist); the work is a step-by-step
plan from the start of preparation to finalisation, by phase, shown as a flow chart; the areas that
need judgment are set out with their evidence and references; and everything is shown as tables and
charts. Sections: areas of caution, job snapshot, prior-year continuity, priority risks, the steps to
finalisation, areas needing judgment, points to note, and the completion checklist with the
roll-forward to next year. (Format 2, 21 Oct 2026, had eight sections with queries to ask.)

What this year's guide hands on (its roll-forward list, events still to confirm, checks left open)
reaches next year's guide for the same client, and code makes sure each one is taken up in its
prior-year section.

One Opus call. The input is the pre-check's own (every line with an id), plus the latest pre-check's
result. Code checks the answer: only real sources; any amount not in the input is flagged; an event
called confirmed with no document behind it becomes suspected; every event is followed through to a
step, a point and the checklist, or flagged; anything worded as a question is dropped from the points
(and flagged elsewhere); the documents still outstanding are listed by code from the pre-check, not by
the model; and the steps always run through review to finalisation.
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
FORMAT = 3  # 3: points not questions, cautions, steps to finalisation (21 Nov 2026); 2: eight sections; 1: a flat list of steps

PRIOR_KINDS = ["error", "reviewer_point", "unresolved", "policy", "balance"]
CHECK_STATUSES = ["done", "open", "na"]
LEVELS = ["high", "medium", "low"]
# The phases of preparing a set of financial statements, start to finalisation, in order.
PHASES = ["start", "records", "reconcile", "income_expenses", "assets_liabilities", "adjustments", "tax", "draft", "review", "finalise"]
PHASE_LABELS = {"start": "Start", "records": "Records and coding", "reconcile": "Bank and reconciliations", "income_expenses": "Income and expenses",
                "assets_liabilities": "Assets and liabilities", "adjustments": "Year-end adjustments", "tax": "Tax", "draft": "Draft statements",
                "review": "Review", "finalise": "Finalisation"}
POINT_KINDS = ["action", "note", "escalate"]
# About two A4 pages of words; past this the guide is flagged as too long.
MAX_WORDS = 1200

_STR = {"type": "string"}
# Ids as one comma-separated string ("B1, G2.1"), not an array: the API compiles the answer shape into a
# grammar, and with an array of ids on every item it refused it as too large (21 Oct 2026).
_IDS = _STR


def _obj(props: dict) -> dict:
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


SCHEMA = _obj({
    "snapshot": _obj({"activities": _STR, "assets_and_funding": _STR, "records": _STR, "bookkeeping": _STR, "period": _STR, "sources": _IDS}),
    "cautions": {"type": "array", "items": _obj({"area": _STR, "caution": _STR, "level": {"type": "string", "enum": LEVELS}, "sources": _IDS})},
    "events": {"type": "array", "items": _obj({
        "id": _STR, "event": _STR, "status": {"type": "string", "enum": ["confirmed", "suspected"]},
        "why_it_matters": _STR, "action": _STR, "effect": _STR, "sources": _IDS})},
    "prior_year": {"type": "array", "items": _obj({
        "item": _STR, "kind": {"type": "string", "enum": PRIOR_KINDS}, "follow_through": _STR, "sources": _IDS})},
    "risks": {"type": "array", "items": _obj({
        "area": _STR, "what_could_be_wrong": _STR, "examine": _STR, "evidence": _STR, "events": _IDS, "sources": _IDS})},
    "steps": {"type": "array", "items": _obj({
        "phase": {"type": "string", "enum": PHASES}, "step": _STR, "depends_on": _STR, "can_start_now": {"type": "boolean"}, "escalate": _STR,
        "events": _IDS, "sources": _IDS})},
    "judgments": {"type": "array", "items": _obj({
        "area": _STR, "judgment": _STR, "evidence": _STR, "manager_approval": {"type": "boolean"}, "reference": _STR, "events": _IDS, "sources": _IDS})},
    "points": {"type": "array", "items": _obj({"kind": {"type": "string", "enum": POINT_KINDS}, "text": _STR, "events": _IDS, "sources": _IDS})},
    "checklist": {"type": "array", "items": _obj({"check": _STR, "status": {"type": "string", "enum": CHECK_STATUSES}, "events": _IDS})},
    "roll_forward": {"type": "array", "items": _obj({"item": _STR, "why": _STR, "sources": _IDS})},
})

ANSWER = """Answer in the JSON shape given, following the preparation guide skill: cautions, snapshot, events (worked out for the follow-through; not shown as a section), prior_year, risks, steps (from the start of preparation to finalisation, each with its phase, in order), judgments (each with its area), points, checklist and roll_forward. Write statements and instructions, never questions: no item may be a question to the accountant, the manager or the client. Do not list the documents still requested from the client: code lists them from the pre-check. Use only figures, names and dates in the input; mark an event confirmed only when a document shows it; give "sources" as the ids each item rests on and "events" as the event ids it follows through (E1, E2, ...), each as one comma-separated string ("B1, G2.1"; "" for none); list in "roll_forward" what next year's preparer must pick up; take up every rolled-forward (Y) line in "prior_year"."""

# Words kept per field: about half as much again as the skill asks for, so an answer that runs a
# little long is kept whole rather than cut mid-sentence (the page limit is checked on the total).
LIMITS = {"snapshot": 45, "event": 45, "why_it_matters": 40, "action": 55, "effect": 40, "item": 35, "follow_through": 35,
          "area": 8, "caution": 35, "what_could_be_wrong": 35, "examine": 35, "evidence": 35, "step": 30, "depends_on": 20, "escalate": 30,
          "judgment": 35, "reference": 25, "text": 35, "check": 30, "why": 35}
MAX_ITEMS = {"cautions": 6, "events": 7, "prior_year": 6, "risks": 5, "steps": 20, "judgments": 8, "points": 10, "outstanding": 20,
             "checklist": 14, "roll_forward": 8}

# The last two phases, written in by code when the model stops short of them.
CLOSING_STEPS = {
    "review": "Review the draft financial statements, the tax return and the workpapers with the reviewer, and clear the review points.",
    "finalise": "Finalise: send the statements to the client for approval and signature, file the tax return, and file the signed copies with the workpapers.",
}


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


def outstanding_from(last: dict | None) -> list[dict]:
    """The documents still requested from the client, from the latest pre-check: listed by code."""
    return [{"group": r.get("group", ""), "item": r.get("item", "")} for r in (last or {}).get("requests") or [] if r.get("item")]


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


def is_question(text: str) -> bool:
    """A question to someone, which the guide never asks (AFIT, 21 Nov 2026)."""
    return str(text or "").rstrip().rstrip('"\')').endswith("?")


def clean(raw: dict, index: dict, known_text: str, outstanding: list[dict] | None = None) -> dict:
    known = P.known_numbers(known_text)

    def sources(ids) -> list[str]:
        return [i for i in _ids(ids) if i in index][:6]

    def text(value, field: str) -> str:
        return clip_words(" ".join(str(value or "").split()), LIMITS[field])

    def figures(item: dict, *fields: str) -> list[str]:
        out = [] if all(P.figures_ok(item[f], known) for f in fields) else ["figure_not_in_documents"]
        if any(is_question(item[f]) for f in fields):
            out.append("worded_as_question")
        return out

    # Events first (not shown, but followed through): their ids are renumbered E1, E2, ... and every
    # later reference is mapped.
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

    order = {lv: n for n, lv in enumerate(LEVELS)}
    cautions = rows(raw.get("cautions"), MAX_ITEMS["cautions"], {"caution": "caution", "area": "area"},
                    lambda r: {"level": r.get("level") if r.get("level") in LEVELS else "medium"})
    cautions = [c for c in cautions if "worded_as_question" not in c["flags"]]
    cautions.sort(key=lambda c: order[c["level"]])
    for c in cautions:
        c.pop("events", None)
    prior = rows(raw.get("prior_year"), MAX_ITEMS["prior_year"], {"item": "item", "follow_through": "follow_through"},
                 lambda r: {"kind": r.get("kind") if r.get("kind") in PRIOR_KINDS else "unresolved"})
    risks = rows(raw.get("risks"), MAX_ITEMS["risks"],
                 {"what_could_be_wrong": "what_could_be_wrong", "area": "area", "examine": "examine", "evidence": "evidence"})
    steps = rows(raw.get("steps"), MAX_ITEMS["steps"], {"step": "step", "depends_on": "depends_on", "escalate": "escalate"},
                 lambda r: {"can_start_now": bool(r.get("can_start_now")), "phase": r.get("phase") if r.get("phase") in PHASES else "start"})
    steps = [s for s in steps if "worded_as_question" not in s["flags"]]
    # The steps run from the start to finalisation: in phase order (the model's order within a phase),
    # with the review and finalisation written in by code when the answer stops short of them.
    phase_of = {p: n for n, p in enumerate(PHASES)}
    for phase, step in CLOSING_STEPS.items():
        if not any(s["phase"] == phase for s in steps):
            steps.append({"step": step, "depends_on": "the steps before", "escalate": "", "can_start_now": False, "phase": phase,
                          "events": [], "sources": [], "flags": ["added_by_code"]})
    steps.sort(key=lambda s: phase_of[s["phase"]])  # stable: the model's order within a phase
    for n, s in enumerate(steps, start=1):
        s["n"] = n
    judgments = rows(raw.get("judgments"), MAX_ITEMS["judgments"],
                     {"judgment": "judgment", "area": "area", "evidence": "evidence", "reference": "reference"},
                     lambda r: {"manager_approval": bool(r.get("manager_approval"))})
    for j in judgments:
        j["area"] = j["area"] or "General"
    points = rows(raw.get("points"), MAX_ITEMS["points"] * 2, {"text": "text"},
                  lambda r: {"kind": r.get("kind") if r.get("kind") in POINT_KINDS else "note"})
    questions_dropped = sum(1 for p in points if "worded_as_question" in p["flags"])
    points = [p for p in points if "worded_as_question" not in p["flags"]][: MAX_ITEMS["points"]]
    # What is still to come from the client: from the pre-check, by code, so it is never re-asked.
    docs = [{"group": text(o.get("group"), "area"), "item": text(o.get("item"), "item"), "flags": []}
            for o in (outstanding or [])[: MAX_ITEMS["outstanding"]] if str(o.get("item", "")).strip()]
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
    # suspected event a point saying how to confirm it.
    def mentions(items) -> set[str]:
        return {e for it in items for e in it.get("events", [])}

    in_steps, in_checklist, in_points = mentions(steps), mentions(checklist), mentions(points + judgments + risks)
    for e in events:
        missing = [part for part, ok in (("step", e["id"] in in_steps), ("checklist", e["id"] in in_checklist),
                                         ("point", e["status"] == "confirmed" or e["id"] in in_points)) if not ok]
        e["not_followed_through"] = missing
        if missing:
            e["flags"].append("not_followed_through")

    return {"format": FORMAT, "cautions": cautions, "snapshot": snapshot, "events": events, "prior_year": prior, "risks": risks, "steps": steps,
            "judgments": judgments, "points": points, "outstanding": docs, "checklist": checklist, "roll_forward": roll_forward,
            "questions_dropped": questions_dropped}


SECTIONS = ("cautions", "snapshot", "prior_year", "risks", "steps", "judgments", "points", "outstanding", "checklist", "roll_forward")


def word_count(guide: dict) -> int:
    def walk(v) -> int:
        if isinstance(v, str):
            return len(v.split())
        if isinstance(v, dict):
            return sum(walk(x) for k, x in v.items() if k not in ("sources", "events", "flags", "id", "status", "kind", "phase", "level",
                                                                  "not_followed_through"))
        if isinstance(v, list):
            return sum(walk(x) for x in v)
        return 0
    return walk({k: guide.get(k, []) for k in SECTIONS})


def size(guide: dict) -> int:
    """How many items the guide holds (older guides: what they held)."""
    if guide.get("format") == FORMAT:
        return sum(len(guide.get(k, [])) for k in SECTIONS if k != "snapshot")
    if guide.get("format") == 2:
        q = guide["queries"]
        return sum(len(guide.get(k, [])) for k in ("events", "prior_year", "risks", "sequence", "judgments", "checklist", "roll_forward")) + sum(len(v) for v in q.values())
    return len(guide.get("steps", []))


def flagged(guide: dict) -> int:
    """How many items code flagged (an amount not in the documents, an event not followed through...)."""
    if guide.get("format") == FORMAT:
        items = [guide["snapshot"]] + [x for k in SECTIONS if k != "snapshot" for x in guide.get(k, [])] + guide.get("events", [])
        return sum(1 for x in items if x.get("flags"))
    if guide.get("format") == 2:
        items = [guide["snapshot"]] + [x for k in ("events", "prior_year", "risks", "sequence", "judgments", "checklist", "roll_forward") for x in guide.get(k, [])]
        return sum(1 for x in items + [q for v in guide["queries"].values() for q in v] if x.get("flags"))
    return sum(1 for s in guide.get("steps", []) if s.get("flags"))


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
        return P._source_view(sid, index, ev)  # special notes included

    def with_views(v):
        if isinstance(v, dict):
            return {k: ([view(i) for i in x] if k == "sources" else with_views(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [with_views(x) for x in v]
        return v

    out = with_views(cleaned)
    high = sum(1 for c in out["cautions"] if c["level"] == "high")
    open_checks = sum(1 for c in out["checklist"] if c["status"] == "open")
    words = word_count(out)
    plural = lambda n, word: f"{n} {word}{'s' if n != 1 else ''}"  # noqa: E731
    parts = [plural(len(out["cautions"]), "area") + " of caution" + (f" ({high} high)" if high else ""),
             plural(len(out["steps"]), "step") + " to finalisation",
             plural(len(out["judgments"]), "judgment"),
             plural(open_checks, "open check")]
    out["summary"] = "; ".join(filter(None, (out["snapshot"]["activities"], out["snapshot"]["period"])))
    out["words"] = words
    out["phase_labels"] = PHASE_LABELS
    out["flags"] = (["longer_than_two_pages"] if words > MAX_WORDS else []) + (["questions_dropped"] if out.get("questions_dropped") else [])
    out["decision"] = {"state": "guide", "label": "Preparation guide", "reason": "; ".join(parts) + "."}
    out["evidence"] = {k: {f: e[f] for f in ("file_name", "location", "quote", "drive_url")} for k, e in evidence.items()}
    return out, evidence
