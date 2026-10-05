"""The professional pre-check: one Opus call that reads what a New Zealand accountant would read
and lists what is still needed for this year's accounts, each with its reason.

Code prepares the input and checks the answer; the model does the professional judgment.

Input — every line carries an id so the answer can cite it and code can check the citation:
    Q  this year's client questionnaire, line by line (the most important document)
    F  last year's financial statements, line by line
    T  last year's trial balance, one line per account
    W  last year's workpapers, each with its first lines
    D  every file received, with its kind and year
    R  this year's documents, the first lines of each
    B  this year's bank exports as summarised by code; B1.2 = one payer or payee
    C  checks done by code (opening balance follows on, bank covers the year)
    N  the task's Direction Note (the firm's own instructions)
    L  lessons from earlier corrections by AFIT staff

Answer — structured JSON: the business nature with its reasoning and facts, then items, each
`request`, `already_provided` (with the files) or `not_needed`, with a reason and sources. Code
keeps only sources and files that exist, sends anything "already provided" without a file back to
"request", flags a reason whose figures are not in the input, and writes the client email from the
checked items — the email can only say what the list says.
"""
import json
import re

from langchain_core.messages import HumanMessage

from .analysis import counterparties
from .archives import display_name
from .budget import usage_from_message
from .config import Settings
from .evidence import evidence_from, file_evidence
from .llm import get_model, model_id, stop_reason, text_of
from .prompting import system_message
from .rules import _block_for
from .skills_loader import get_skill
from .textutil import clip_words, est_tokens, sha, to_number

TYPES = {"residential_rental": "Residential rental", "general": "General business", "investment": "Investment"}
DECISIONS = ["request", "already_provided", "not_needed"]
SKILLS = ["precheck-method", "nz-residential-rental", "nz-general-business", "nz-investment"]
SOURCE_KINDS = {"Q": "questionnaire", "F": "last_year_fs", "T": "last_year_tb", "W": "workpaper", "D": "document",
                "B": "bank", "C": "check", "N": "direction", "R": "received"}

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["business_nature", "items", "preparer_notes", "lessons_applied"],
    "properties": {
        "business_nature": {
            "type": "object",
            "additionalProperties": False,
            "required": ["type", "summary", "reasoning", "sources", "facts"],
            "properties": {
                "type": {"type": "string", "enum": list(TYPES)},
                "summary": {"type": "string"},
                "reasoning": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "facts": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["text", "sources"],
                    "properties": {"text": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}},
                }},
            },
        },
        "items": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["group", "item", "decision", "reason", "sources", "documents"],
            "properties": {
                "group": {"type": "string"},
                "item": {"type": "string"},
                "decision": {"type": "string", "enum": DECISIONS},
                "reason": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "documents": {"type": "array", "items": {"type": "string"}},
            },
        }},
        "preparer_notes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["text", "sources"],
            "properties": {"text": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}},
        }},
        "lessons_applied": {"type": "array", "items": {"type": "string"}},
    },
}

ANSWER = """Answer in the JSON shape given.
- business_nature: the type, a one-sentence summary, your reasoning (at most 80 words) and the facts that drive what is needed, each with its sources.
- items: everything this year's accounts need. decision: request, already_provided (list the D ids that provide it in "documents") or not_needed (say why). "group" is the property, bank account, loan or area (e.g. "12 Kauri Street", "ANZ 01-0702-0311954-00", "Tax"). "reason": at most 60 words, plain language a client understands, saying why it is needed and where that comes from. "sources": the ids (Q, F, T, W, D, R, B, C, N) the reason rests on.
- preparer_notes: points the preparer must decide or watch (tax positions, risks), each with sources.
- lessons_applied: the L ids you applied.
Never invent a figure, file or fact: use only what is in the input."""


def system_text() -> str:
    return "\n\n".join(f"# Skill: {get_skill(n).name}\n{get_skill(n).body}" for n in SKILLS)


def skill_versions() -> dict[str, str]:
    return {n: get_skill(n).version for n in SKILLS}


# --- input --------------------------------------------------------------------------------------

def _line(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt(n) -> str:
    return "" if n is None else f"{n:,.2f}"


def build_input(job: dict, key: dict, docs: list[dict], files: dict, periods: dict, facts: dict, lessons: list[dict],
                settings: Settings, caps: dict | None = None) -> tuple[str, dict]:
    """The input text and the id -> item index used to check the answer. `key` is keydocs.find(),
    `facts` is analysis.prepare() (last year's TB lines, bank exports, code checks)."""
    caps = caps or {"Q": 700, "F": 500, "T": 250, "W": 240, "D": 400, "R": 1200, "R_per_doc": 30}
    parsed = {d["file"]["file_id"]: d["parsed"] for d in docs}
    index: dict[str, dict] = {}
    out: list[str] = []
    fixed = job.get("precheck_type") if job.get("precheck_type") in TYPES else ""
    out.append(f"TASK: client {job.get('client_name') or ''}; task {job.get('title') or ''}; this year {key['this_year']}; "
               f"last year {key['last_year']}; business nature fixed by AFIT: {TYPES[fixed] if fixed else 'no — decide it'}")

    def section(title: str, prefix: str, rows: list[tuple[str, dict]], cap: int) -> None:
        out.append(f"\n== {title} ==")
        for n, (text, item) in enumerate(rows[:cap], start=1):
            sid = f"{prefix}{n}"
            index[sid] = item
            out.append(f"{sid} | {text}")
        if len(rows) > cap:
            out.append(f"({len(rows) - cap} more lines not shown)")

    def blocks_of(role: str) -> list[tuple[str, dict]]:
        rows = []
        for f in next(k for k in key["documents"] if k["role"] == role)["files"]:
            for b in parsed.get(f["file_id"], {}).get("blocks", []):
                rows.append((f"{_line(b['text'])}  [{display_name(f)}, {b['loc']}]", {"kind": SOURCE_KINDS["Q" if role == "questionnaire" else "F"], "file": f, "block": b}))
        return rows

    section("THIS YEAR'S CLIENT QUESTIONNAIRE", "Q", blocks_of("questionnaire"), caps["Q"])
    section("LAST YEAR'S FINANCIAL STATEMENTS", "F", blocks_of("last_year_fs"), caps["F"])
    tb = [(f"{_line(ln['label'], 90)} | {ln.get('type') or ln['section']} | {_fmt(ln['amount'])} | year before {_fmt(ln['comparative'])}",
           {"kind": "last_year_tb", "file": ln["file"], "block": ln["block"], "label": ln["label"]}) for ln in facts.get("all_prior_lines", [])]
    section("LAST YEAR'S TRIAL BALANCE (code: debit positive, credit negative)", "T", tb, caps["T"])
    wp_rows = []
    for f in next(k for k in key["documents"] if k["role"] == "last_year_workpapers")["files_all"]:
        blocks = parsed.get(f["file_id"], {}).get("blocks", [])
        head = " / ".join(_line(b["text"], 90) for b in blocks[:8])
        wp_rows.append((f"{display_name(f)} | {f['document_class'].replace('_', ' ')} | {head}", {"kind": "workpaper", "file": f, "block": blocks[0] if blocks else None}))
    section("LAST YEAR'S WORKPAPERS (first lines of each)", "W", wp_rows, caps["W"] // 8 or 1)
    doc_rows = []
    for f in sorted(files.values(), key=lambda f: (f.get("year") or 0, f["name"].lower()), reverse=True):
        if f.get("document_class") == "archive" and not f.get("error"):
            continue
        extra = f"; cannot be read: {f['error']}" if f.get("error") else ""
        doc_rows.append((f"{display_name(f)} | {f['document_class'].replace('_', ' ')} | {f.get('year_label') or 'year not stated'}{extra}",
                         {"kind": "document", "file": f}))
    section("FILES RECEIVED (a file listed here has been received)", "D", doc_rows, caps["D"])
    # What this year's documents say, so "already provided" and "complete" can be judged from
    # their contents, not their names. Bank exports are summarised below instead.
    key_ids = {f["file_id"] for k in key["documents"] for f in k.get("files_all", k["files"])}
    received = []
    for f in sorted(files.values(), key=lambda f: f["name"].lower()):
        if f.get("year_role") not in ("current", "unknown") or f["file_id"] in key_ids or f.get("error") or f.get("document_class") == "archive":
            continue
        if any(e["file"]["file_id"] == f["file_id"] for e in facts.get("exports", [])):
            continue
        for b in parsed.get(f["file_id"], {}).get("blocks", [])[: caps.get("R_per_doc", 30)]:
            received.append((f"{_line(b['text'], 160)}  [{display_name(f)}, {b['loc']}]", {"kind": "received", "file": f, "block": b}))
    section("THIS YEAR'S DOCUMENTS (first lines of each)", "R", received, caps.get("R", 1200))
    out.append("\n== THIS YEAR'S BANK EXPORTS (summarised by code) ==")
    for n, e in enumerate(facts.get("exports", []), start=1):
        bid = f"B{n}"
        index[bid] = {"kind": "bank", "export": e}
        out.append(f"{bid} | {e['account'] or e['file']['name']} | {e['from']:%d %b %Y} to {e['to']:%d %b %Y} | opening {_fmt(e['opening'])} | "
                   f"closing {_fmt(e['closing'])} | money in {_fmt(e['money_in'])} | money out {_fmt(e['money_out'])} | {e['count']} transactions")
        for m, cp in enumerate(counterparties(e), start=1):
            index[f"{bid}.{m}"] = {"kind": "counterparty", "export": e, "party": cp}
            out.append(f"{bid}.{m} | {cp['name']} | {cp['type']} | {cp['count']} payments | total {_fmt(cp['total'])}")
    out.append("\n== CHECKS DONE BY CODE ==")
    for n, c in enumerate(facts.get("checks", []), start=1):
        index[f"C{n}"] = {"kind": "check", "check": c}
        out.append(f"C{n} | {c['label']} | {'passed' if c['passed'] else 'FAILED'} | {c['detail']}")
    section("DIRECTION NOTE (the firm's instructions for this task)", "N",
            [(i["text"], {"kind": "direction", "text": i["text"]}) for i in job.get("direction_items", [])], 40)
    out.append("\n== LESSONS FROM EARLIER CORRECTIONS (apply each one that fits) ==")
    for lesson in lessons[:40]:
        lid = f"L{lesson['id']}"
        index[lid] = {"kind": "lesson", "lesson": lesson}
        where = "this client" if lesson.get("scope") == "client" else f"all {TYPES.get(lesson.get('precheck_type'), 'clients')}"
        out.append(f"{lid} | {where} | {lesson.get('kind', '')} | item: {_line(lesson.get('item', ''), 120)} | {_line(lesson.get('note', ''), 300)}")
    out.append("\n" + ANSWER)
    return "\n".join(out), index


def fit_input(build, settings: Settings) -> tuple[str, dict]:
    """Build the input, shrinking the longest sections until it fits the cap (cost stays bounded)."""
    caps = {"Q": 700, "F": 500, "T": 250, "W": 240, "D": 400, "R": 1200, "R_per_doc": 30}
    body, index = build(caps)
    while est_tokens(body) > settings.precheck_max_input_tokens and caps["F"] > 60:
        caps = {k: max(int(v * 0.75), 8 if k == "R_per_doc" else 40) for k, v in caps.items()}
        caps["Q"] = max(caps["Q"], 300)  # the questionnaire is cut last
        body, index = build(caps)
    return body, index


def cache_key(client_id: str, job_id: str, body: str, settings: Settings) -> str:
    versions = skill_versions()
    return sha(client_id, job_id, model_id("precheck", settings), settings.prompt_version, *sorted(f"{k}={v}" for k, v in versions.items()), body)


# --- the call -------------------------------------------------------------------------------------

class Unusable(ValueError):
    def __init__(self, message: str, usage: dict):
        super().__init__(message)
        self.usage = usage


def call_model(body: str, settings: Settings) -> tuple[dict, dict]:
    message = get_model("precheck", settings).invoke(
        [system_message("precheck", system_text(), settings), HumanMessage(content=body)],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    usage = usage_from_message(message)
    if stop_reason(message) in ("refusal", "max_tokens"):
        raise Unusable(f"The pre-check model stopped early ({stop_reason(message)}).", usage)
    try:
        return json.loads(text_of(message)), usage
    except json.JSONDecodeError as exc:
        raise Unusable("The pre-check model's answer was not valid JSON.", usage) from exc


# --- checking the answer ------------------------------------------------------------------------------

_NUMBER = re.compile(r"(?<![\w.])\$?\(?-?\d[\d,]*(?:\.\d+)?\)?%?")


def known_numbers(body: str) -> set[float]:
    known = set()
    for token in re.findall(r"-?\d[\d,]*(?:\.\d+)?", body):
        value = to_number(token)
        if value is not None:
            known.update({round(abs(value), 2), float(round(abs(value)))})
    return known


def figures_ok(text: str, known: set[float]) -> bool:
    """Every amount in the text is one the input holds. Years, days, counts up to 31 and
    percentages are not amounts."""
    for token in _NUMBER.findall(text):
        if token.endswith("%"):
            continue
        value = to_number(token.strip("$()%"))
        if value is None or abs(value) <= 31 or (1990 <= abs(value) <= 2100 and float(value).is_integer()):
            continue
        if round(abs(value), 2) not in known and float(round(abs(value))) not in known:
            return False
    return True


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def clean(raw: dict, index: dict, body: str, fixed_type: str = "") -> dict:
    known = known_numbers(body)
    valid = lambda ids: [i for i in dict.fromkeys(str(x).strip() for x in ids) if i in index and index[i]["kind"] != "lesson"][:6]  # noqa: E731
    nature = raw.get("business_nature") or {}
    btype = fixed_type or (nature.get("type") if nature.get("type") in TYPES else "general")
    facts = [{"text": clip_words(f.get("text", ""), 30), "sources": valid(f.get("sources", []))}
             for f in nature.get("facts", []) if f.get("text") and figures_ok(f.get("text", ""), known)][:12]
    items, seen = [], set()
    for it in raw.get("items", []):
        text = clip_words(str(it.get("item", "")), 25)
        if not text or _norm(text) in seen:
            continue
        seen.add(_norm(text))
        decision = it.get("decision") if it.get("decision") in DECISIONS else "request"
        documents = [d for d in valid(it.get("documents", [])) if index[d]["kind"] == "document"]
        sources = valid(it.get("sources", []))
        reason = clip_words(str(it.get("reason", "")), 60)
        flags = []
        if decision == "already_provided" and not documents:
            decision = "request"  # said to be provided, but no file named: safer to ask
            flags.append("no_file_named")
        if not sources and not documents:
            flags.append("no_source")
        if not figures_ok(reason, known):
            flags.append("figure_not_in_documents")
        items.append({"group": clip_words(str(it.get("group", "")) or "General", 8), "item": text, "decision": decision,
                      "reason": reason, "sources": sources, "documents": documents, "flags": flags})
    notes = [{"text": clip_words(n.get("text", ""), 40), "sources": valid(n.get("sources", []))}
             for n in raw.get("preparer_notes", []) if n.get("text") and figures_ok(n.get("text", ""), known)][:10]
    lessons = [lid for lid in dict.fromkeys(raw.get("lessons_applied", [])) if index.get(lid, {}).get("kind") == "lesson"]
    reasoning = clip_words(str(nature.get("reasoning", "")), 80)
    return {
        "business_nature": {"type": btype, "fixed": bool(fixed_type), "summary": clip_words(str(nature.get("summary", "")), 30),
                            "reasoning": reasoning if figures_ok(reasoning, known) else "", "sources": valid(nature.get("sources", [])), "facts": facts},
        "items": items, "preparer_notes": notes, "lessons_applied": lessons,
    }


# --- what the task card shows ---------------------------------------------------------------------------

def _source_view(sid: str, index: dict, ev) -> dict:
    item = index[sid]
    kind = item["kind"]
    if kind in ("questionnaire", "last_year_fs", "last_year_tb", "received"):
        prefix = {"questionnaire": "Questionnaire", "last_year_fs": "Last year's statements", "last_year_tb": "Last year's trial balance",
                  "received": f"Received: {display_name(item['file'])}"}[kind]
        return {"id": sid, "label": f"{prefix}: {_line(item['block']['text'], 90)}", "evidence_id": ev(evidence_from(item["file"], [item["block"]]))}
    if kind == "workpaper":
        e = evidence_from(item["file"], [item["block"]]) if item.get("block") else file_evidence(item["file"])
        return {"id": sid, "label": f"Workpaper: {display_name(item['file'])}", "evidence_id": ev(e)}
    if kind == "document":
        return {"id": sid, "label": display_name(item["file"]), "evidence_id": ev(file_evidence(item["file"]))}
    if kind == "bank":
        e = item["export"]
        block = _block_for(e["parsed"], e["table"], e["closing_row"])
        return {"id": sid, "label": f"Bank {e['account'] or e['file']['name']}, {e['from']:%d %b %Y} to {e['to']:%d %b %Y}",
                "evidence_id": ev(evidence_from(e["file"], [block])) if block else None}
    if kind == "counterparty":
        e, cp = item["export"], item["party"]
        block = _block_for(e["parsed"], e["table"], cp["rows"][0])
        return {"id": sid, "label": f"Bank: {cp['name']}, {cp['count']} payments, total {_fmt(cp['total'])}",
                "evidence_id": ev(evidence_from(e["file"], [block])) if block else None}
    if kind == "check":
        c = item["check"]
        first = next(((f, b) for f, b in c["evidence"] if b), None)
        return {"id": sid, "label": f"Check: {c['label']}", "evidence_id": ev(evidence_from(first[0], [first[1]])) if first else None}
    return {"id": sid, "label": f"Direction Note: {_line(item['text'], 90)}", "evidence_id": None}


def assemble(cleaned: dict, index: dict, key: dict, facts: dict, client_name: str) -> tuple[dict, dict]:
    """(the pre-check shown on the task card, evidence by id)."""
    evidence: dict[str, dict] = {}

    def ev(e: dict | None) -> str | None:
        if not e:
            return None
        evidence[e["id"]] = e
        return e["id"]

    views = lambda ids: [_source_view(i, index, ev) for i in ids]  # noqa: E731
    items = [{**it, "sources": views(it["sources"]), "documents": views(it["documents"])} for it in cleaned["items"]]
    nature = cleaned["business_nature"]
    out = {
        "key_documents": key_views(key, ev),
        "business_nature": {**nature, "label": TYPES[nature["type"]], "sources": views(nature["sources"]),
                            "facts": [{**f, "sources": views(f["sources"])} for f in nature["facts"]]},
        "requests": [i for i in items if i["decision"] == "request"],
        "provided": [i for i in items if i["decision"] == "already_provided"],
        "not_needed": [i for i in items if i["decision"] == "not_needed"],
        "preparer_notes": [{**n, "sources": views(n["sources"])} for n in cleaned["preparer_notes"]],
        "lessons_applied": [{"id": lid, "text": index[lid]["lesson"].get("note") or index[lid]["lesson"].get("item", "")} for lid in cleaned["lessons_applied"]],
        "bank": bank_views(facts),
        "checks": [{"label": c["label"], "passed": c["passed"], "detail": c["detail"]} for c in facts.get("checks", [])],
    }
    requests = out["requests"]
    out["decision"] = ({"state": "requests", "label": "Requests to send",
                        "reason": f"{len(requests)} item{'s are' if len(requests) != 1 else ' is'} still needed before this year's accounts can be prepared."}
                       if requests else
                       {"state": "nothing", "label": "Nothing to request",
                        "reason": "Everything this year's accounts need appears to have been received."})
    out["email"] = email(requests, client_name, key)
    out["evidence"] = {k: {f: e[f] for f in ("file_name", "location", "quote", "drive_url")} for k, e in evidence.items()}
    return out, evidence


def key_views(key: dict, ev) -> list[dict]:
    return [{"role": k["role"], "label": k["label"], "found": k["found"], "note": k["note"],
             "files": [{"name": display_name(f), "evidence_id": ev(file_evidence(f))} for f in k["files"]]} for k in key["documents"]]


def bank_views(facts: dict) -> list[dict]:
    return [{"account": e["account"] or e["file"]["name"], "from": f"{e['from']:%d %b %Y}", "to": f"{e['to']:%d %b %Y}",
             "opening": e["opening"], "closing": e["closing"]} for e in facts.get("exports", [])]


def email(requests: list[dict], client_name: str, key: dict) -> dict:
    """The client email, written by code from the checked requests: it can only say what the
    list says. Grouped by property, account, loan or area; each item with its reason."""
    if not requests:
        return {"subject": "", "body": ""}
    groups: dict[str, list[dict]] = {}
    for r in requests:
        groups.setdefault(r["group"], []).append(r)
    parts = []
    for group, rows in groups.items():
        parts.append(group)
        parts.extend(f"- {r['item']}: {r['reason']}" for r in rows)
        parts.append("")
    body = (f"Hi {client_name or 'there'},\n\n"
            f"Thank you for your documents. To prepare your accounts for {key['this_year']}, we still need the following. "
            f"We have said why each item is needed.\n\n" + "\n".join(parts) + "\n" +
            "If something does not apply to you, just let us know and we will note it.\n\nThank you,\nAFIT")
    return {"subject": f"Information still needed for your accounts for {key['this_year']}", "body": body}
