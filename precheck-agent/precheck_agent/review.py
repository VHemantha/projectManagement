"""The review: one Opus call that reviews the financial statements a preparer has drafted, round
after round, until the reviewer says the review is complete.

Code prepares the input and checks the answer; the model does the reviewer's judgment. Every line
of the input carries an id, so the answer can cite it and code can check the citation:
    S  this year's draft financial statements, line by line (label, this year, comparative)
    T  this year's trial balance, one line per account
    F  last year's signed financial statements
    A  the preparer's assumptions and judgements (from the task card)
    E  passages from this year's documents, found in the knowledge store for each assumption,
       each open finding and the largest statement lines: filtered on the card's tags first
       (this task, this year's documents), then by meaning
    Q  this year's client questionnaire
    C  checks done by code (comparatives agree to last year, bank data covers the year, …)
    D  every file received
    R  findings from earlier rounds, with the reviewer's response and note
    L  lessons and learned rules

Answer — structured JSON: findings (each with its area, statement line, issue, why, severity,
action and sources), findings from earlier rounds now resolved, and a verdict on each assumption.
Code keeps only sources that exist, never re-raises what the reviewer closed, flags a finding with
no source or with a figure not in the input, and numbers new findings in the PM application.
"""
import json
import re

from langchain_core.messages import HumanMessage

from .analysis import statement_lines, tb_lines
from .archives import display_name
from .budget import usage_from_message
from .config import Settings
from .embeddings import get_embedder
from .evidence import evidence_from, file_evidence
from .keydocs import placed
from .knowledge import Scope, get_knowledge
from .llm import get_model, model_id, stop_reason, text_of
from .precheck import TYPES, Unusable, _line, figures_ok, known_numbers
from .prompting import system_message
from .skills_loader import get_skill
from .textutil import clip_words, est_tokens, sha

NATURE_SKILLS = {"residential_rental": "nz-residential-rental", "general": "nz-general-business", "investment": "nz-investment"}
SEVERITIES = ["high", "medium", "low"]
VERDICTS = ["supported", "challenged", "needs_evidence"]
RESPONSES = {"agree": "agreed, to be fixed", "fixed": "says fixed", "not_an_issue": "NOT AN ISSUE (closed)", "wrong_reason": "wrong reason"}
FS_CLASSES = ("financial_statements",)

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "findings", "resolved", "assumption_reviews", "lessons_applied"],
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["ref", "area", "fs_line", "issue", "why", "severity", "action", "sources", "assumptions"],
            "properties": {
                "ref": {"type": "string"},
                "area": {"type": "string"},
                "fs_line": {"type": "string"},
                "issue": {"type": "string"},
                "why": {"type": "string"},
                "severity": {"type": "string", "enum": SEVERITIES},
                "action": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
                "assumptions": {"type": "array", "items": {"type": "string"}},
            },
        }},
        "resolved": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["ref", "reason", "sources"],
            "properties": {"ref": {"type": "string"}, "reason": {"type": "string"}, "sources": {"type": "array", "items": {"type": "string"}}},
        }},
        "assumption_reviews": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["assumption", "verdict", "reason", "sources"],
            "properties": {
                "assumption": {"type": "string"},
                "verdict": {"type": "string", "enum": VERDICTS},
                "reason": {"type": "string"},
                "sources": {"type": "array", "items": {"type": "string"}},
            },
        }},
        "lessons_applied": {"type": "array", "items": {"type": "string"}},
    },
}

ANSWER = """Answer in the JSON shape given.
- summary: at most 60 words: the state of the draft and the most important points.
- findings: every problem still open. "ref": the R id when it continues an earlier finding, else "". "area" (e.g. "Fixed assets", "Rental income", "Shareholder current account"), "fs_line": the statement line it concerns, "issue": what is wrong (at most 40 words), "why": why it matters, with the rule or evidence (at most 60 words), "severity": high, medium or low, "action": what the preparer should do (at most 30 words), "sources": the ids it rests on, "assumptions": the A ids it concerns.
- resolved: earlier findings (R ids) the draft now shows dealt with, with the reason and sources.
- assumption_reviews: one per A item: supported, challenged or needs_evidence, the reason (at most 50 words) and sources.
- lessons_applied: the L ids you applied.
Never raise again a finding the reviewer closed as not an issue unless the input shows something new, and then say what. Never invent a figure, file or fact."""


def skills_for(nature: str) -> list[str]:
    return ["nz-fs-review", NATURE_SKILLS.get(nature, "nz-general-business")]


def system_text(nature: str) -> str:
    return "\n\n".join(f"# Skill: {get_skill(n).name}\n{get_skill(n).body}" for n in skills_for(nature))


def skill_versions(nature: str) -> dict[str, str]:
    return {n: get_skill(n).version for n in skills_for(nature)}


# --- what is reviewed ----------------------------------------------------------------------------

def draft_statements(docs: list[dict], key: dict, job: dict, folders: dict) -> tuple[list[dict], str]:
    """(this year's draft financial statements, where they came from). The task card may say
    where they are; otherwise this year's financial statements in the folder, never last year's."""
    on_card = ((job.get("key_paths") or {}).get("draft_fs") or "").strip()
    if on_card:
        files, _ = placed(docs, on_card, folders)
        ids = {f["file_id"] for f in files}
        return [d for d in docs if d["file"]["file_id"] in ids], "task card"
    last_year = {f["file_id"] for k in key["documents"] if k["role"] == "last_year_fs" for f in k.get("files_all", k["files"])}
    found = [d for d in docs if d["file"]["document_class"] in FS_CLASSES and d["file"].get("year_role") == "current"
             and d["file"]["file_id"] not in last_year and not d["file"].get("error")]
    return found, "folder"


def comparative_checks(draft: list[dict], last_year: list[dict]) -> list[dict]:
    """The draft's comparative column against last year's signed statements, line by line (a
    reviewer's first test). Lines matched by their label."""
    signed = {}
    for d in last_year:
        for ln in statement_lines(d):
            signed.setdefault(_norm(ln["label"]), ln)
    checks = []
    for d in draft:
        for ln in statement_lines(d):
            prior = signed.get(_norm(ln["label"]))
            if prior is None or ln["comparative"] is None:
                continue
            ok = abs(ln["comparative"] - prior["amount"]) < 1
            checks.append({
                "id": "comparative:" + _norm(ln["label"]),
                "label": f"Comparative for {ln['label']} agrees to last year's signed statements",
                "passed": ok,
                "detail": "" if ok else f"draft comparative {ln['comparative']:,.2f}; last year's statements {prior['amount']:,.2f}",
                "evidence": [(ln["file"], ln["block"]), (prior["file"], prior["block"])],
            })
    return checks


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _fmt(n) -> str:
    return "" if n is None else f"{n:,.2f}"


# --- input -----------------------------------------------------------------------------------------

def build_input(job: dict, scope: Scope, key: dict, docs: list[dict], files: dict, draft: list[dict], checks: list[dict],
                settings: Settings, caps: dict | None = None) -> tuple[str, dict]:
    caps = caps or {"S": 400, "T": 300, "F": 400, "A": 60, "E": 120, "E_per_query": 3, "Q": 400, "D": 300, "R": 80}
    review = job.get("review") or {}
    index: dict[str, dict] = {}
    out: list[str] = []
    nature = review.get("nature") or (job.get("precheck_type") if job.get("precheck_type") in TYPES else "")
    out.append(f"TASK: client {job.get('client_name') or ''}; task {job.get('title') or ''}; this year {key['this_year']}; "
               f"business nature {TYPES.get(nature, 'not decided')}; review round {review.get('round', 1)}")

    def section(title: str, prefix: str, rows: list[tuple[str, dict]], cap: int) -> None:
        out.append(f"\n== {title} ==")
        for n, (text, item) in enumerate(rows[:cap], start=1):
            sid = f"{prefix}{n}"
            index[sid] = item
            out.append(f"{sid} | {text}")
        if len(rows) > cap:
            out.append(f"({len(rows) - cap} more lines not shown)")

    s_rows = []
    for d in draft:
        lines = statement_lines(d)
        if lines:
            s_rows += [(f"{_line(ln['label'], 90)} | {ln['section'] or '-'} | this year {_fmt(ln['amount'])} | comparative {_fmt(ln['comparative'])}  "
                        f"[{display_name(ln['file'])}, {ln['block']['loc']}]", {"kind": "draft", "file": ln["file"], "block": ln["block"], "line": ln})
                       for ln in lines]
        else:  # not laid out as label + amounts: give its text
            s_rows += [(f"{_line(b['text'])}  [{display_name(d['file'])}, {b['loc']}]", {"kind": "draft", "file": d["file"], "block": b})
                       for b in d["parsed"]["blocks"]]
    section("THIS YEAR'S DRAFT FINANCIAL STATEMENTS (to review)", "S", s_rows, caps["S"])

    tb_rows = []
    for d in docs:
        if d["file"]["document_class"] == "trial_balance" and d["file"].get("year_role") == "current":
            tb_rows += [(f"{_line(ln['label'], 90)} | {ln.get('type') or ln['section']} | {_fmt(ln['amount'])}",
                         {"kind": "tb", "file": ln["file"], "block": ln["block"]}) for ln in tb_lines(d)]
    section("THIS YEAR'S TRIAL BALANCE (code: debit positive, credit negative)", "T", tb_rows, caps["T"])

    parsed = {d["file"]["file_id"]: d["parsed"] for d in docs}

    def blocks_of(role: str, kind: str) -> list[tuple[str, dict]]:
        rows = []
        for f in next(k for k in key["documents"] if k["role"] == role)["files"]:
            for b in parsed.get(f["file_id"], {}).get("blocks", []):
                rows.append((f"{_line(b['text'])}  [{display_name(f)}, {b['loc']}]", {"kind": kind, "file": f, "block": b}))
        return rows

    section("LAST YEAR'S SIGNED FINANCIAL STATEMENTS", "F", blocks_of("last_year_fs", "last_year_fs"), caps["F"])

    assumptions = review.get("assumptions") or []
    a_rows = [(f"{a.get('area', '')} | line: {_line(a.get('fs_line', ''), 80)} | amount {a.get('amount') or '-'} | judgement: {_line(a.get('judgement', ''), 300)} | "
               f"basis: {_line(a.get('basis', ''), 300)} | evidence named: {_line(a.get('evidence', ''), 120) or 'none'}",
               {"kind": "assumption", "assumption": a}) for a in assumptions]
    out.append("\n== THE PREPARER'S ASSUMPTIONS AND JUDGEMENTS ==")
    for text, item in a_rows[: caps["A"]]:
        aid = item["assumption"]["ref"]
        index[aid] = item
        out.append(f"{aid} | {text}")

    # Evidence from the knowledge store: filtered on this task's tags and this year's documents
    # first, then the passages closest in meaning to each question a reviewer would ask.
    previous = review.get("findings") or []
    queries = [f"{a.get('fs_line', '')} {a.get('judgement', '')} {a.get('evidence', '')}" for a in assumptions]
    queries += [f"{f.get('fs_line', '')} {f.get('issue', '')}" for f in previous if f.get("status") == "open"]
    largest = sorted((r for r in s_rows if r[1].get("line")), key=lambda r: -abs(r[1]["line"]["amount"] or 0))[:12]
    queries += [r[1]["line"]["label"] for r in largest]
    draft_ids = {d["file"]["file_id"] for d in draft}
    e_rows, seen = [], set()
    kn, embedder = get_knowledge(), get_embedder()
    vectors = embedder.embed(queries) if queries else []
    for vec in vectors:
        for hit in kn.search(scope, vec, caps["E_per_query"], year_role=["current", "unknown"]):
            if hit["id"] in seen or hit.get("file_id") in draft_ids or hit.get("file_id") not in files:
                continue
            seen.add(hit["id"])
            f = files[hit["file_id"]]
            body = hit["text"].split("\n", 1)[-1]
            e_rows.append((f"{_line(body, 300)}  [{display_name(f)}, {hit.get('location', '')}]", {"kind": "chunk", "file": f, "blocks": hit.get("blocks", [])}))
    section("EVIDENCE FROM THIS YEAR'S DOCUMENTS (found for the assumptions, open findings and largest lines)", "E", e_rows, caps["E"])

    section("THIS YEAR'S CLIENT QUESTIONNAIRE", "Q", blocks_of("questionnaire", "questionnaire"), caps["Q"])
    out.append("\n== CHECKS DONE BY CODE ==")
    for n, c in enumerate(checks, start=1):
        index[f"C{n}"] = {"kind": "check", "check": c}
        out.append(f"C{n} | {c['label']} | {'passed' if c['passed'] else 'FAILED'} | {c['detail']}")
    d_rows = [(f"{display_name(f)} | {f['document_class'].replace('_', ' ')} | {f.get('year_label') or 'year not stated'}", {"kind": "document", "file": f})
              for f in sorted(files.values(), key=lambda f: f["name"].lower()) if f.get("document_class") != "archive"]
    section("FILES RECEIVED", "D", d_rows, caps["D"])

    out.append("\n== FINDINGS FROM EARLIER ROUNDS, WITH THE REVIEWER'S RESPONSE ==")
    for f in previous[: caps["R"]]:
        index[f["ref"]] = {"kind": "previous", "finding": f}
        response = RESPONSES.get(f.get("response") or "", "no response yet")
        out.append(f"{f['ref']} | {f.get('status', 'open')} | {f.get('severity', '')} | {f.get('area', '')} | line: {_line(f.get('fs_line', ''), 80)} | "
                   f"{_line(f.get('issue', ''), 200)} | reviewer: {response}{(' — ' + _line(f['note'], 200)) if f.get('note') else ''}")

    out.append("\n== LESSONS AND LEARNED RULES (apply each one that fits) ==")
    for lesson in (job.get("lessons") or [])[:40]:
        lid = f"L{lesson['id']}"
        index[lid] = {"kind": "lesson", "lesson": lesson}
        out.append(f"{lid} | {lesson.get('kind', '')} | {_line(lesson.get('item', ''), 120)} | {_line(lesson.get('note', ''), 300)}")
    out.append("\n" + ANSWER)
    return "\n".join(out), index


def fit_input(build, settings: Settings) -> tuple[str, dict]:
    caps = {"S": 400, "T": 300, "F": 400, "A": 60, "E": 120, "E_per_query": 3, "Q": 400, "D": 300, "R": 80}
    body, index = build(caps)
    while est_tokens(body) > settings.precheck_max_input_tokens and caps["F"] > 60:
        caps = {k: (v if k in ("S", "A", "R", "E_per_query") else max(int(v * 0.75), 40)) for k, v in caps.items()}
        body, index = build(caps)
    return body, index


def cache_key(client_id: str, job_id: str, nature: str, body: str, settings: Settings) -> str:
    return sha("review", client_id, job_id, model_id("precheck", settings), settings.prompt_version,
               *sorted(f"{k}={v}" for k, v in skill_versions(nature).items()), body)


def call_model(body: str, nature: str, settings: Settings) -> tuple[dict, dict]:
    message = get_model("precheck", settings).invoke(
        [system_message("precheck", system_text(nature), settings), HumanMessage(content=body)],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}},
    )
    usage = usage_from_message(message)
    if stop_reason(message) in ("refusal", "max_tokens"):
        raise Unusable(f"The review model stopped early ({stop_reason(message)}).", usage)
    try:
        return json.loads(text_of(message)), usage
    except json.JSONDecodeError as exc:
        raise Unusable("The review model's answer was not valid JSON.", usage) from exc


# --- checking the answer ---------------------------------------------------------------------------

def clean(raw: dict, index: dict, body: str, previous: list[dict]) -> dict:
    known = known_numbers(body)
    valid = lambda ids: [i for i in dict.fromkeys(str(x).strip() for x in ids)  # noqa: E731
                         if i in index and index[i]["kind"] not in ("lesson", "assumption", "previous")][:8]
    by_ref = {f["ref"]: f for f in previous}
    closed = {r for r, f in by_ref.items() if f.get("status") == "closed" or f.get("response") == "not_an_issue"}
    assumption_ids = {i for i, v in index.items() if v["kind"] == "assumption"}
    findings, seen, dropped = [], set(), []
    for f in raw.get("findings", []):
        ref = str(f.get("ref") or "").strip()
        if ref and ref not in by_ref:
            ref = ""  # not one of ours: a new finding
        if ref in closed:
            dropped.append(ref)  # the reviewer closed it; the model raised it again
            continue
        issue = clip_words(str(f.get("issue", "")), 40)
        key = ref or _norm(f"{f.get('fs_line', '')} {issue}")
        if not issue or key in seen:
            continue
        seen.add(key)
        why, action = clip_words(str(f.get("why", "")), 60), clip_words(str(f.get("action", "")), 30)
        sources = valid(f.get("sources", []))
        flags = []
        if not sources:
            flags.append("no_source")
        if not all(figures_ok(t, known) for t in (issue, why, action)):
            flags.append("figure_not_in_documents")
        findings.append({"ref": ref, "area": clip_words(str(f.get("area", "")) or "General", 6), "fs_line": clip_words(str(f.get("fs_line", "")), 12),
                         "issue": issue, "why": why, "action": action,
                         "severity": f.get("severity") if f.get("severity") in SEVERITIES else "medium",
                         "sources": sources, "assumptions": [a for a in dict.fromkeys(f.get("assumptions", [])) if a in assumption_ids],
                         "flags": flags})
    open_refs = {f["ref"] for f in findings if f["ref"]}
    resolved = [{"ref": r["ref"], "reason": clip_words(str(r.get("reason", "")), 40), "sources": valid(r.get("sources", []))}
                for r in raw.get("resolved", []) if r.get("ref") in by_ref and r.get("ref") not in open_refs and r.get("ref") not in closed]
    reviews, done = [], set()
    for r in raw.get("assumption_reviews", []):
        aid = r.get("assumption")
        if aid not in assumption_ids or aid in done:
            continue
        done.add(aid)
        reason = clip_words(str(r.get("reason", "")), 50)
        reviews.append({"assumption": aid, "verdict": r.get("verdict") if r.get("verdict") in VERDICTS else "needs_evidence",
                        "reason": reason if figures_ok(reason, known) else "", "sources": valid(r.get("sources", []))})
    summary = clip_words(str(raw.get("summary", "")), 60)
    lessons = [lid for lid in dict.fromkeys(raw.get("lessons_applied", [])) if index.get(lid, {}).get("kind") == "lesson"]
    order = {s: n for n, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: order[f["severity"]])
    return {"summary": summary if figures_ok(summary, known) else "", "findings": findings, "resolved": resolved,
            "assumption_reviews": reviews, "lessons_applied": lessons, "reraised_closed": dropped}


# --- what the task card shows ----------------------------------------------------------------------

def _source_view(sid: str, index: dict, ev) -> dict:
    item = index[sid]
    kind = item["kind"]
    if kind in ("draft", "tb", "last_year_fs", "questionnaire"):
        prefix = {"draft": "Draft", "tb": "Trial balance", "last_year_fs": "Last year's statements", "questionnaire": "Questionnaire"}[kind]
        return {"id": sid, "label": f"{prefix}: {_line(item['block']['text'], 90)}", "evidence_id": ev(evidence_from(item["file"], [item["block"]]))}
    if kind == "chunk":
        blocks = item["blocks"][:3]
        e = evidence_from(item["file"], blocks) if blocks else file_evidence(item["file"])
        return {"id": sid, "label": f"{display_name(item['file'])}: {_line(e['quote'], 80)}", "evidence_id": ev(e)}
    if kind == "document":
        return {"id": sid, "label": display_name(item["file"]), "evidence_id": ev(file_evidence(item["file"]))}
    if kind == "check":
        c = item["check"]
        first = next(((f, b) for f, b in c["evidence"] if b), None)
        return {"id": sid, "label": f"Check: {c['label']}", "evidence_id": ev(evidence_from(first[0], [first[1]])) if first else None}
    return {"id": sid, "label": sid, "evidence_id": None}


def assemble(cleaned: dict, index: dict, draft: list[dict], how_found: str, checks: list[dict]) -> tuple[dict, dict]:
    evidence: dict[str, dict] = {}

    def ev(e: dict | None) -> str | None:
        if not e:
            return None
        evidence[e["id"]] = e
        return e["id"]

    views = lambda ids: [_source_view(i, index, ev) for i in ids]  # noqa: E731
    findings = [{**f, "sources": views(f["sources"])} for f in cleaned["findings"]]
    counts = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    out = {
        "draft_fs": [{"name": display_name(d["file"]), "evidence_id": ev(file_evidence(d["file"]))} for d in draft],
        "draft_found_by": how_found,
        "summary": cleaned["summary"],
        "findings": findings,
        "resolved": [{**r, "sources": views(r["sources"])} for r in cleaned["resolved"]],
        "assumption_reviews": [{**r, "sources": views(r["sources"])} for r in cleaned["assumption_reviews"]],
        "lessons_applied": [{"id": lid, "text": index[lid]["lesson"].get("note") or index[lid]["lesson"].get("item", "")} for lid in cleaned["lessons_applied"]],
        "checks": [{"label": c["label"], "passed": c["passed"], "detail": c["detail"]} for c in checks],
        "counts": counts,
    }
    out["decision"] = ({"state": "findings", "label": "Findings to address",
                        "reason": f"{len(findings)} finding{'s' if len(findings) != 1 else ''} open: {counts['high']} high, {counts['medium']} medium, {counts['low']} low."}
                       if findings else {"state": "clear", "label": "No open findings",
                                         "reason": "Nothing open in this round. The reviewer decides when the review is complete."})
    out["evidence"] = {k: {f: e[f] for f in ("file_name", "location", "quote", "drive_url")} for k, e in evidence.items()}
    return out, evidence


def blocked(reason: str) -> dict:
    return {"draft_fs": [], "draft_found_by": "", "summary": "", "findings": [], "resolved": [], "assumption_reviews": [],
            "lessons_applied": [], "checks": [], "counts": {s: 0 for s in SEVERITIES}, "evidence": {},
            "decision": {"state": "blocked", "label": "Cannot review yet", "reason": reason}, "how": "code"}


# --- the knowledge store: what the review knows, searchable for questions later --------------------

def remember(scope: Scope, review: dict, round_findings: list[dict], run_id: str) -> None:
    """Assumptions, earlier findings and the reviewer's feedback (from the PM application, the
    record) and this round's findings go into the knowledge store with the card's tags, replacing
    what this task held before, so a question about the task can find them."""
    kn, embedder = get_knowledge(), get_embedder()
    old = kn.get(scope, source_types=["assumption", "finding", "feedback"])
    kn.delete([e["id"] for e in old])
    entries = {"assumption": [], "finding": [], "feedback": []}
    for a in review.get("assumptions") or []:
        text = f"Assumption {a['ref']} ({a.get('area', '')}, {a.get('fs_line', '')}): {a.get('judgement', '')} Basis: {a.get('basis', '')}"
        entries["assumption"].append({"id": f"{scope.task}:assumption:{a['ref']}", "text": text, "meta": {"ref": a["ref"], "area": a.get("area", "")}})
    for f in review.get("findings") or []:
        if f.get("response"):
            text = f"Reviewer on {f['ref']} ({f.get('fs_line', '')}): {RESPONSES.get(f['response'], f['response'])}. {f.get('note', '')}"
            entries["feedback"].append({"id": f"{scope.task}:feedback:{f['ref']}", "text": text, "meta": {"ref": f["ref"], "response": f["response"]}})
    for n, f in enumerate(round_findings):
        ref = f["ref"] or f"new-{run_id[:8]}-{n}"
        text = f"Review finding {f['ref'] or '(new)'} [{f['severity']}] {f['area']} — {f['fs_line']}: {f['issue']} Why: {f['why']} Action: {f['action']}"
        entries["finding"].append({"id": f"{scope.task}:finding:{ref}", "text": text, "meta": {"ref": f["ref"], "severity": f["severity"], "run": run_id}})
    for source_type, rows in entries.items():
        if rows:
            vectors = embedder.embed([r["text"] for r in rows])
            kn.put(scope, source_type, [{**r, "embedding": v} for r, v in zip(rows, vectors)])
