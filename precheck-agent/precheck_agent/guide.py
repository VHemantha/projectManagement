"""The preparation guide: after the pre-check, the steps a preparer takes to prepare this year's
financial statements, each with the figures from the documents and how to verify it.

One Opus call. The input is the pre-check's own (every line with an id: questionnaire, last year's
statements and trial balance, workpapers, this year's documents, bank exports and the general ledger
summarised by code, code checks), plus the latest pre-check's result. Code checks the answer: only
real sources, and a step with an amount not in the input is flagged.
"""
import json

from langchain_core.messages import HumanMessage

from . import precheck as P
from .budget import usage_from_message
from .config import Settings
from .llm import get_model, model_id, stop_reason, text_of
from .prompting import system_message
from .skills_loader import get_skill
from .textutil import clip_words, sha

SKILL = "nz-preparation-guide"
SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["summary", "steps"],
    "properties": {
        "summary": {"type": "string"},
        "steps": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["area", "step", "check", "waits_on_client", "sources"],
            "properties": {
                "area": {"type": "string"},
                "step": {"type": "string"},
                "check": {"type": "string"},
                "waits_on_client": {"type": "boolean"},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
        }},
    },
}

ANSWER = """Answer in the JSON shape given: a summary (at most 50 words) and the preparation steps in the order the work is done, as the preparation guide skill says. Use only figures and names in the input; cite the ids each step rests on."""


def system_text() -> str:
    return P.system_text() + f"\n\n# Skill: {get_skill(SKILL).name}\n{get_skill(SKILL).body}"


def skill_version() -> str:
    return get_skill(SKILL).version


def with_precheck(body: str, last: dict | None) -> str:
    """The pre-check input with the pre-check's own result added: what is still requested (the steps
    that depend on it wait for the client) and what it noted for the preparer."""
    lines = ["\n== THE LATEST PRE-CHECK'S RESULT =="]
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
    return sha("guide", client_id, job_id, model_id("precheck", settings), settings.prompt_version, skill_version(),
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


def clean(raw: dict, index: dict, known_text: str) -> dict:
    known = P.known_numbers(known_text)
    valid = lambda ids: [i for i in dict.fromkeys(str(x).strip() for x in ids) if i in index and index[i]["kind"] != "lesson"][:6]  # noqa: E731
    steps, seen = [], set()
    for s in raw.get("steps", []):
        step = clip_words(str(s.get("step", "")), 45)
        if not step or step.lower() in seen:
            continue
        seen.add(step.lower())
        check = clip_words(str(s.get("check", "")), 30)
        sources = valid(s.get("sources", []))
        flags = []
        if not sources:
            flags.append("no_source")
        if not (P.figures_ok(step, known) and P.figures_ok(check, known)):
            flags.append("figure_not_in_documents")
        steps.append({"area": clip_words(str(s.get("area", "")) or "General", 6), "step": step, "check": check,
                      "waits_on_client": bool(s.get("waits_on_client")), "sources": sources, "flags": flags})
    summary = clip_words(str(raw.get("summary", "")), 50)
    return {"summary": summary if P.figures_ok(summary, known) else "", "steps": steps}


def assemble(cleaned: dict, index: dict) -> tuple[dict, dict]:
    evidence: dict[str, dict] = {}

    def ev(e: dict | None) -> str | None:
        if not e:
            return None
        evidence[e["id"]] = e
        return e["id"]

    steps = [{**s, "sources": [P._source_view(i, index, ev) for i in s["sources"]]} for s in cleaned["steps"]]
    waiting = sum(1 for s in steps if s["waits_on_client"])
    out = {
        "summary": cleaned["summary"],
        "steps": steps,
        "decision": {"state": "guide", "label": "Preparation guide",
                     "reason": f"{len(steps)} step{'s' if len(steps) != 1 else ''}; {waiting} wait{'s' if waiting == 1 else ''} on information from the client."},
    }
    out["evidence"] = {k: {f: e[f] for f in ("file_name", "location", "quote", "drive_url")} for k, e in evidence.items()}
    return out, evidence
