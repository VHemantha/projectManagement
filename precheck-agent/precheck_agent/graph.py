"""The pre-check graph: nine nodes, of which only read, judge and escalate call a model — with
one exception in `index`: a picture or a scanned PDF has no text for code to extract, so the
reader model writes out what it says, once per file version (see vision.py).

    load_job -> sync_drive -> index -> run_rules -> analyse -> [draft_directions] -> plan
             -> read (fan-out) -> collect -> judge -> [escalate] -> publish

`analyse` compares this year's documents with last year's accounts (see analysis.py): code
extracts and checks the figures, one judge-model call reads the compact result.

(`collect` is not a tenth step: it only gathers the parallel readers and, when the readers'
prompt prefix is long enough to be cached, lets one reader per type finish first so the others
read the cache instead of all paying to write it.)
"""
import logging
import operator
import os
import time
from typing import Annotated, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import CachePolicy, Send
from pydantic import ValidationError

from . import analysis as A
from . import directions as D
from . import judge as J
from . import vision
from .archives import attachments as email_attachments
from .archives import container_of, display_name
from .archives import members as archive_members
from .budget import budget_for, cost_usd, empty_usage
from .classify import READER_CLASSES, READER_FOR_CLASS, classify, classify_email, reader_for_question
from .config import get_settings
from .drive import DriveError, get_drive, is_zip
from .emails import is_email
from .embeddings import get_embedder
from .llm import model_id, prefix_is_cacheable
from .parsing import chunk_blocks, parse_file
from .periods import assign_years, year_label
from .pm_client import get_pm
from .readers import cache_key as reader_cache_key
from .readers import evidence_from, run_reader, skill_versions, system_prompt
from .rules import run_rules as apply_rules
from .skills_loader import all_skills
from .store import StoreCache, get_store
from .textutil import est_tokens, sha

logger = logging.getLogger(__name__)

DONE_NS = "reader-done"  # marker written when a reader result is cached, so plan can see it
PENDING_NS = "pending"  # a file with an image still to read: looked at again on the next run


def _pending_key(client_id: str, job_id: str, file_id: str) -> str:
    return sha(client_id, job_id, file_id)


class PrecheckStop(Exception):
    """The run cannot continue, for a reason a person can act on (shown on the job card)."""


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class State(TypedDict, total=False):
    run_id: str
    job_id: str
    mode: str  # "precheck" (default) | "draft" (only draft the Direction Note, do not verify)
    drafted: dict
    started_at: float
    job: dict
    listing: list[dict]
    sync: dict
    files: dict[str, dict]
    ai_read: list[str]  # ids of files whose text was read from an image by the model
    rule_results: list[dict]
    rule_findings: list[dict]
    periods: dict
    analysis: dict
    analysis_findings: list[dict]
    tasks: list[dict]
    round: int
    evidence: Annotated[dict, _merge]
    reader_results: Annotated[list, operator.add]
    usage: Annotated[list, operator.add]
    skipped: Annotated[list, operator.add]
    judge_inputs: list[dict]
    result: dict
    notes: dict
    final: dict


def emit(stage: str, label: str, state: str = "done", **counts) -> None:
    """One custom stream event per node: which of the five trail steps it belongs to, a plain
    label and real counts. The job card's "How the AI got here" strip is built from these."""
    get_stream_writer()({"stage": stage, "state": state, "label": label, "counts": counts})


# --- 1. load_job (code) -----------------------------------------------------------------------

def load_job(state: State) -> dict:
    emit("read", "Opening the task", "running")
    s = get_settings()
    if s.llm_mode != "fake" and not (s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")):
        raise PrecheckStop("The pre-check service has no Claude API key configured. Ask an administrator to set it.")
    job = get_pm().get_job(state["job_id"])
    if not job.get("drive_folder_id"):
        raise PrecheckStop("This task has no Google Drive folder linked. Add the folder on the task card, then run the pre-check.")
    job = {**job, "direction_items": D.normalize_items(job.get("direction_items") or [])}
    if not job.get("client_id"):
        raise PrecheckStop("This task's project is not in a sub-workspace, so the pre-check cannot keep its documents separate. Put the project in a sub-workspace first.")
    return {"job": job, "started_at": state.get("started_at") or time.time(), "round": 0}


# --- 2. sync_drive (code) ---------------------------------------------------------------------

def sync_drive(state: State) -> dict:
    """List the folder (metadata only) and compare with the stored manifest. Only new or
    changed files continue; an unchanged file costs nothing (token rule 6)."""
    s, store, job = get_settings(), get_store(), state["job"]
    try:
        listing = [f.as_dict() for f in get_drive(s).list_folder(job["drive_folder_id"])]
    except DriveError as exc:
        raise PrecheckStop(str(exc)) from exc
    manifest = store.get_manifest(job["client_id"], state["job_id"])
    cache = StoreCache(store)
    changed = [
        f["id"] for f in listing
        if f["id"] not in manifest or manifest[f["id"]]["version"] != f["version"] or manifest[f["id"]]["parser_version"] != s.parser_version
        or cache.get_value(PENDING_NS, _pending_key(job["client_id"], state["job_id"], f["id"]))
    ]
    present = {f["id"] for f in listing}
    # A document inside a zip ("<zip id>!<path>") stays for as long as its zip is in the folder.
    removed = [fid for fid in manifest if container_of(fid) not in present]
    for fid in removed:
        store.delete_file(job["client_id"], state["job_id"], fid)
    if not listing:
        raise PrecheckStop("The task's Drive folder is empty, so there is nothing to check yet.")
    sync = {"total": len(listing), "changed": changed, "removed": len(removed), "first_run": not manifest}
    since = "all new" if not manifest else f"{len(changed)} changed since last run"
    emit("read", f"{len(listing)} files in the folder, {since}", "running", documents=len(listing), changed=len(changed))
    return {"listing": listing, "sync": sync}


# --- 3. index (code) --------------------------------------------------------------------------

ARCHIVE_CLASS = "archive"  # the manifest row of a zip itself; its documents have their own rows


def _read_image(f: dict, data: bytes, name: str, kind: str, ctx: dict) -> tuple[dict, bool]:
    """Have the reader model write out a picture or a scan. Returns (parsed document, pending):
    pending means it was not read this time and the next run should try again."""
    s, shown = get_settings(), display_name(f)
    empty = {"blocks": [], "tables": []}
    reason = budget_for(ctx["run_id"]).try_image_call()
    if reason:
        ctx["skipped"].append({"task_id": "image", "direction_ref": "none", "what": f"Reading the image {shown}", "reason": reason})
        return {**empty, "error": "Not read yet: this run reached its limit of images. Run the pre-check again to read it."}, True
    emit("read", f"Reading the image {shown}", "running")
    try:
        parsed, usage = vision.transcribe(data, name, kind, s)
    except vision.Unreadable as exc:
        return {**empty, "error": str(exc)}, False
    except Exception:  # the model could not be reached, or would not take the file
        logger.exception("Reading image %s failed", f["id"])
        return {**empty, "error": "This image could not be read this time. Run the pre-check again."}, True
    ctx["usage"].append({"node": "read_image", "task_id": "image-" + sha(f["id"])[:10], "model": model_id("vision", s), "calls": 1, "run_id": ctx["run_id"], **usage})
    return parsed, False


def _index_document(f: dict, data_or_error, ctx: dict) -> bool:
    """Parse, classify, chunk, embed and store one document. `data_or_error` is a function
    returning (bytes, name to parse as, mime) — only called when the parse is not cached —
    or a string saying why the document cannot be read. Returns True when the document has an
    image that is still to be read (the next run looks at it again)."""
    s, store, embedder = get_settings(), get_store(), get_embedder()
    client_id, job_id = ctx["client_id"], ctx["job_id"]
    parsed_key = sha(f["id"], f["version"], s.parser_version)  # file id + version + parser version
    parsed = store.get_parsed(parsed_key)
    pending = False
    if parsed is None:
        if isinstance(data_or_error, str):
            parsed = {"blocks": [], "tables": [], "error": data_or_error}
        else:
            data, parse_name, mime = data_or_error()
            parsed = parse_file(data, parse_name, mime) if data else {"blocks": [], "tables": [], "error": "This file is empty, too large or not a readable type."}
            if parsed.get("vision"):
                parsed, pending = _read_image(f, data, parse_name, parsed["vision"], ctx)
        if not pending:  # an image still to be read is not stored, so the next run reads it
            store.set_parsed(parsed_key, parsed)
    StoreCache(store).set_value(PENDING_NS, _pending_key(client_id, job_id, f["id"]), pending)
    shown = display_name(f)
    sample = "\n".join(b["text"] for b in parsed["blocks"][:40])
    doc_class = classify_email(f["name"], sample) if is_email(f["name"], f["mime_type"]) else classify(f["name"], sample)
    chunks = chunk_blocks(parsed["blocks"], s.chunk_tokens)
    texts = [f"{shown} {c['location']}\n" + "\n".join(b["text"] for b in c["blocks"]) for c in chunks]
    hashes = [sha(t) for t in texts]
    keys = [sha(embedder.name, h) for h in hashes]
    have = store.get_embeddings(keys)
    missing = [i for i, k in enumerate(keys) if k not in have]
    if missing:
        vectors = embedder.embed([texts[i] for i in missing])
        fresh = {keys[i]: vectors[n] for n, i in enumerate(missing)}
        store.set_embeddings(fresh)
        have.update(fresh)
    rows = [{
        "id": sha(job_id, f["id"], f["version"], str(seq))[:32], "file_version": f["version"], "seq": seq,
        "location": c["location"], "document_class": doc_class, "text": text, "blocks": c["blocks"],
        "content_hash": h, "tokens": est_tokens(text), "embedding": have[k],
    } for seq, (c, text, h, k) in enumerate(zip(chunks, texts, hashes, keys))]
    store.replace_chunks(client_id, job_id, f["id"], rows)
    store.upsert_manifest({
        "job_id": job_id, "file_id": f["id"], "client_id": client_id, "name": f["name"], "mime_type": f["mime_type"],
        "version": f["version"], "parser_version": s.parser_version, "document_class": doc_class, "web_url": f["web_url"],
        "path": f["path"], "n_blocks": len(parsed["blocks"]), "error": parsed.get("error", ""),
    })
    return pending


def _index_container(f: dict, drive, ctx: dict, before: dict) -> list[str]:
    """A zip, or an email with attachments: index each document it holds as its own file (the
    email itself is one of them). Returns the ids of the documents that are new or changed, so
    an unchanged document inside a re-uploaded zip is not read again."""
    from .drive import DriveFile

    s, store = get_settings(), get_store()
    client_id, job_id = ctx["client_id"], ctx["job_id"]
    cache = StoreCache(store)
    data, _, _ = drive.download(DriveFile(**f))
    email = not is_zip(f["name"], f["mime_type"])
    if email:
        docs, problem = ([{**f, "data": data}] + email_attachments(data, f, s) if data else [{**f, "error": "This email is empty or too large to read."}]), ""
    else:
        docs, problem = archive_members(data, f, s) if data else ([], "This zip file is empty or too large to open.")
    keep, changed, pending = set(), [], False
    for d in docs:
        keep.add(d["id"])
        old = before.get(d["id"])
        waiting = cache.get_value(PENDING_NS, _pending_key(client_id, job_id, d["id"]))
        if d["id"] != f["id"] and old and old["version"] == d["version"] and old["parser_version"] == s.parser_version and not waiting:
            continue
        changed.append(d["id"])
        content = d.get("data")
        pending |= _index_document(d, d["error"] if "error" in d else (lambda c=content, n=d["name"]: (c, n, "")), ctx)
    for fid in before:  # documents that were in it before and are gone now
        if container_of(fid) == f["id"] and fid != f["id"] and fid not in keep:
            store.delete_file(client_id, job_id, fid)
    if not email:
        store.replace_chunks(client_id, job_id, f["id"], [])
        store.upsert_manifest({
            "job_id": job_id, "file_id": f["id"], "client_id": client_id, "name": f["name"], "mime_type": f["mime_type"],
            "version": f["version"], "parser_version": s.parser_version, "document_class": ARCHIVE_CLASS, "web_url": f["web_url"],
            "path": f["path"], "n_blocks": 0, "error": problem,
        })
    # An image inside still to be read: the whole container is opened again on the next run.
    cache.set_value(PENDING_NS, _pending_key(client_id, job_id, f["id"]), pending)
    return changed


def index(state: State) -> dict:
    """Parse changed files with libraries, chunk, embed and store. A zip is opened and every
    document inside it is indexed as its own file; so is every attachment of an email. The only
    model call here is for a picture or a scan, which has no text for a library to read."""
    from .drive import DriveFile

    store, drive, job = get_store(), get_drive(), state["job"]
    client_id, job_id = job["client_id"], state["job_id"]
    ctx = {"client_id": client_id, "job_id": job_id, "run_id": state["run_id"], "usage": [], "skipped": []}
    before = store.get_manifest(client_id, job_id)
    changed: list[str] = []
    for f in state["listing"]:
        if f["id"] not in state["sync"]["changed"]:
            continue
        if is_zip(f["name"], f["mime_type"]) or is_email(f["name"], f["mime_type"]):
            changed += _index_container(f, drive, ctx, before)
        else:
            changed.append(f["id"])
            _index_document(f, lambda f=f: drive.download(DriveFile(**f)), ctx)
    manifest = store.get_manifest(client_id, job_id)
    # A zip that could not be opened stays in the list (so the problem is reported); a zip that
    # opened is represented by the documents inside it.
    files = {fid: row for fid, row in manifest.items() if row["document_class"] != ARCHIVE_CLASS or row["error"]}
    if not any(row["document_class"] != ARCHIVE_CLASS for row in files.values()):
        raise PrecheckStop("The task's Drive folder has no documents the pre-check can read.")
    sync = {**state["sync"], "total": len(files), "changed": changed}
    label = f"{len(files)} documents, " + ("all new" if sync["first_run"] else f"{len(changed)} changed since last run")
    emit("read", label, documents=len(files), changed=len(changed))
    return {"files": files, "sync": sync, "usage": ctx["usage"], "skipped": ctx["skipped"]}


# --- 4. run_rules (code) ----------------------------------------------------------------------

def run_rules(state: State) -> dict:
    """Deterministic checks. A passed rule needs no model; a failed rule is a finding with
    source = rule, quoting the rows it looked at."""
    s, store = get_settings(), get_store()
    emit("checked", "Running the automatic checks", "running")
    docs, ai_read = [], []
    for row in state["files"].values():
        parsed = store.get_parsed(sha(row["file_id"], row["version"], row["parser_version"])) or {"blocks": [], "tables": []}
        docs.append({"file": row, "parsed": parsed})
        if parsed.get("read_by") == vision.AI_READ:
            ai_read.append(row["file_id"])
    # Which year each document belongs to. When the folder holds last year's finished pack as
    # well, the checks run on this year's documents; last year's are the baseline for analyse.
    periods = assign_years(docs, state["job"])
    files = {}
    for fid, row in state["files"].items():
        info = periods["by_file"].get(fid, {"year": None, "role": "unknown"})
        files[fid] = {**row, "year": info["year"], "year_role": info["role"], "year_label": year_label(info["role"], info["year"])}
    checked_docs = [d for d in docs if periods["by_file"][d["file"]["file_id"]]["role"] in ("current", "unknown")] if periods["split"] else docs
    results, findings, evidence = [], [], {}
    for r in apply_rules(checked_docs, s):
        if periods["split"] and r["rule_id"].startswith("required:") and r["passed"] is False:
            # Last year's is in the folder; this year's simply has not arrived yet.
            r.update(severity="medium", title=f"No {r['area']} for FY{periods['current']} yet",
                     why=f"Last year's {r['area']} is in the folder, but none for FY{periods['current']} has arrived yet.")
        ev_ids = []
        for file_row, block in r.pop("evidence"):
            ev = evidence_from(file_row, [block])
            evidence[ev["id"]] = ev
            ev_ids.append(ev["id"])
        r["evidence_ids"] = ev_ids
        results.append(r)
        if r["passed"] is False:
            findings.append({
                "id": "R-" + sha(r["rule_id"])[:8], "rule_id": r["rule_id"], "direction_ref": "none", "area": r["area"], "status": r["status"],
                "severity": r["severity"], "title": r["title"], "why": r["why"], "evidence_ids": ev_ids, "source": "rule",
                "needs_judgment": r["needs_judgment"], "question": r["question"],
            })
    emit("checked", rules_label(results), rules=len(results), failed=sum(1 for r in results if r["passed"] is False and not r["needs_judgment"]))
    return {"rule_results": results, "rule_findings": findings, "evidence": evidence, "ai_read": ai_read, "periods": periods, "files": files}


# --- analyse: this year against last year's accounts -------------------------------------------------

def analyse(state: State) -> dict:
    """Code extracts last year's lines and this year's figures and runs the checks with a right
    answer; one judge-model call says what this year's documents cover. Skipped in draft mode."""
    s, store, job, run_id = get_settings(), get_store(), state["job"], state["run_id"]
    if state.get("mode") == "draft":
        return {}
    periods = state["periods"]
    docs = []
    for row in state["files"].values():
        parsed = store.get_parsed(sha(row["file_id"], row["version"], row["parser_version"])) or {"blocks": [], "tables": []}
        docs.append({"file": row, "parsed": parsed})
    ctx = A.prepare(job, docs, periods, s)
    if not ctx["prior_lines"]:
        reason = ("No last-year accounts were found in the folder (a final trial balance or signed financial statements), "
                  "so there is nothing to compare this year with.")
        emit("compared", "No last-year accounts to compare with", "running")
        return {"analysis": A.unavailable(reason), "analysis_findings": []}
    emit("compared", f"Comparing this year with last year's accounts ({len(ctx['prior_lines'])} lines)", "running")
    body, index = A.build_input(job, periods.get("current"), periods.get("prior"), ctx["start"], ctx["end"], ctx["prior_lines"],
                                ctx["current_lines"], ctx["exports"], ctx["current_docs"], ctx["checks"])
    cache = StoreCache(store)
    key = A.cache_key(job["client_id"], state["job_id"], body, s)
    usage, skipped, how = [], [], "model"
    answer = cache.get_value("analysis", key)
    if answer is not None:
        how = "cache"
    else:
        reason = budget_for(run_id).can_call(est_tokens(A.ROLE + A.TASK) + est_tokens(body))
        if reason:
            answer, how = None, "code only"
            skipped.append({"task_id": "analysis", "direction_ref": "none", "what": "Year-on-year analysis by AI", "reason": reason})
        else:
            try:
                raw, u = A.call_model(body, s)
                budget_for(run_id).add(u)
                usage.append({"node": "analysis", "task_id": "analysis", "model": model_id("analyst", s), "calls": 1, "run_id": run_id, **u})
                answer = A.clean_answer(raw, index, body)
                cache.set_value("analysis", key, answer)
            except (ValueError, KeyError, TypeError):
                logger.exception("Year-on-year analysis answer could not be used")
                answer, how = None, "code only"
    output, findings, evidence = A.assemble(ctx, periods, answer, index, how, evidence_from, s)
    return {"analysis": output, "analysis_findings": findings, "evidence": evidence, "usage": usage, "skipped": skipped}


def rules_label(results: list[dict]) -> str:
    """"22 rules run, 2 failed" — plus how many were only flagged for a reader to look into
    (a large movement is not a failure in itself)."""
    failed = sum(1 for r in results if r["passed"] is False and not r["needs_judgment"])
    flagged = sum(1 for r in results if r["passed"] is False and r["needs_judgment"])
    label = f"{len(results)} rules run, {failed} failed"
    return label + (f", {flagged} flagged for a closer look" if flagged else "")


# --- draft_directions (model, only when needed) ---------------------------------------------------

def needs_draft(state: State) -> bool:
    return state.get("mode") == "draft" or not state["job"].get("direction_items")


def route_after_rules(state: State):
    return "draft_directions" if needs_draft(state) else "plan"


def draft_directions(state: State) -> dict:
    """The job has no Direction Note (or a draft was asked for): draft one from this client's
    past jobs and what is in the folder now. One call to the judge model, cached by exact
    match; if the model cannot be used, code falls back to the standard list for the kinds of
    document present. In a full run the drafted items are then verified like any others."""
    s, store, job, run_id = get_settings(), get_store(), state["job"], state["run_id"]
    emit("compared", "Drafting the Direction Note from past tasks and the folder", "running")
    cache = StoreCache(store)
    body = D.draft_input(job, state["files"], state["rule_results"])
    key = D.draft_cache_key(job["client_id"], state["job_id"], body, s)
    usage, skipped, how = [], [], "model"
    items = cache.get_value("draft", key)
    if items is not None:
        how = "cache"
    else:
        classes = {f["document_class"] for f in state["files"].values()}
        reason = budget_for(run_id).can_call(est_tokens(D.draft_system()) + est_tokens(body))
        if reason:
            items, how = D.standard_items(classes), "standard list"
            skipped.append({"task_id": "draft", "direction_ref": "none", "what": "Drafting the Direction Note with AI", "reason": reason})
        else:
            try:
                raw, u = D.call_draft(body, s)
                budget_for(run_id).add(u)
                usage.append({"node": "draft", "task_id": "draft", "model": model_id("judge", s), "calls": 1, "run_id": run_id, **u})
                items = D.clean_items(raw, job.get("history"))
                if not items:
                    raise ValueError("empty draft")
                cache.set_value("draft", key, items)
            except (ValueError, KeyError, TypeError):
                items, how = D.standard_items(classes), "standard list"
    existing = job.get("direction_items") or []
    taken = {i["id"] for i in existing}
    have = {D._norm(i["text"]) for i in existing}
    new = D.number_items([i for i in items if D._norm(i["text"]) not in have], taken)
    drafted = {"items": new, "how": how, "jobs_seen": (job.get("history") or {}).get("jobs_seen", 0)}
    emit("compared", f"{len(new)} Direction Note items drafted", "running", drafted=len(new))
    final = state.get("mode") == "draft"
    # Sent before anything else so the job card has the items (and their reasons) to show.
    get_pm().send_event(run_id, {
        "type": "ai_precheck.directions_drafted", "job_id": state["job_id"], "items": new, "how": how, "final": final,
        "usage": usage, "versions": {"prompt": s.prompt_version, "skills": {n: sk.version for n, sk in all_skills().items()}},
    })
    update = {"drafted": drafted, "usage": usage, "skipped": skipped}
    if not final:
        update["job"] = {**job, "direction_items": existing + new}
    return update


def route_after_draft(state: State):
    return END if state.get("mode") == "draft" else "plan"


# --- 5. plan (code) ---------------------------------------------------------------------------

ITEM_QUESTION = "Do these passages show that this Direction Note item was done? Say what is addressed, and report anything missing, inconsistent or still open."


def relevant_files(text: str, files: dict[str, dict], limit: int) -> list[str]:
    """Ids of the files whose names best match an item's words (code, no model)."""
    words = {w.rstrip("s") for w in __import__("re").findall(r"[a-z]{3,}", text.lower())} - {"the", "and", "for", "with", "any", "other", "this", "that", "year", "documents", "information"}
    scored = []
    for fid, f in files.items():
        if f.get("document_class") == "archive":
            continue
        name = f"{f['name']} {f.get('document_class', '').replace('_', ' ')}".lower()
        hits = sum(1 for w in words if w in name)
        if hits:
            scored.append((-hits, f.get("year_role") != "current", f["name"].lower(), fid))
    return [fid for *_, fid in sorted(scored)[:limit]]


def plan(state: State) -> dict:
    """One task per Direction Note item, plus one per rule exception that needs judgment.
    Each task has a reader type, one question and its retrieved chunks. All in code: the reader
    type comes from the item's wording, or failing that from the kind of document that matches
    it best — so no model is needed here."""
    s, store, embedder, job = get_settings(), get_store(), get_embedder(), state["job"]
    client_id, job_id, run_id = job["client_id"], state["job_id"], state["run_id"]
    cache = StoreCache(store)
    budget = budget_for(run_id)
    wanted = [
        {"direction_ref": i["id"], "direction_text": i["text"], "question": ITEM_QUESTION, "search": i["text"], "rule_id": ""}
        for i in job["direction_items"]
    ] + [
        {"direction_ref": "none", "direction_text": "", "question": f["question"], "search": f["question"] + " " + f["area"], "rule_id": f["id"]}
        for f in state["rule_findings"] if f["needs_judgment"]
    ]
    tasks, skipped, direct = [], [], []
    for n, w in enumerate(wanted, start=1):
        query = embedder.embed([w["search"]])[0]
        reader = reader_for_question(w["search"])
        chunks = []
        if reader:  # retrieval filter: this job only (in the SQL), this reader's kinds of document
            chunks = store.search(client_id, job_id, query, s.top_k, READER_CLASSES[reader], s.reader_context_tokens)
        if not chunks:
            chunks = store.search(client_id, job_id, query, s.top_k, None, s.reader_context_tokens)
            if chunks and not reader:
                reader = READER_FOR_CLASS[chunks[0]["document_class"]]
        reader = reader or "workpaper_reader"
        task = {
            **w, "task_id": f"T{n}", "reader": reader, "chunk_ids": [c["id"] for c in chunks], "client_id": client_id, "job_id": job_id,
            "origin_run_id": run_id,
            "chunk_refs": [{"file": display_name(state["files"][c["file_id"]]), "location": c["location"]} for c in chunks],
            # The files in the folder that best match the item: "was X provided?" is answered
            # by what is in the folder, not only by what a passage says.
            "listing_ids": relevant_files(w["search"], state["files"], s.listing_files),
        }
        if not chunks and not task["listing_ids"]:
            direct.append(task)  # nothing to read: no model call; the judge step reports it as unclear
            continue
        task["cache_key"] = reader_cache_key(task, chunks, s, [state["files"][f] for f in task["listing_ids"]])
        # system prompt + chunks + file list + the two tool definitions and the question (~500 tokens measured)
        task["est_input"] = est_tokens(system_prompt(reader)) + sum(c["tokens"] for c in chunks) + 30 * len(task["listing_ids"]) + 500
        task["cached"] = cache.get_value(DONE_NS, task["cache_key"]) is not None
        tasks.append(task)

    # Budget (token rule 11), reserved here in code before anything is sent to a model. It is
    # first grown to fit the work found, within the hard caps in config.
    fresh = [t for t in tasks if not t["cached"]]
    budget.fit(len(fresh), sum(t["est_input"] for t in fresh), s)
    spare = budget.spare_calls(len(fresh))
    for i, t in enumerate(fresh):
        reason = budget.try_reader_call(t["est_input"])
        if reason:
            t["skip_reason"] = reason
            skipped.append({"task_id": t["task_id"], "direction_ref": t["direction_ref"], "what": t["direction_text"] or t["question"], "reason": reason})
        t["allow_tools"] = i < spare  # a tool round-trip is a second call; only when there is room
    tasks = [t for t in tasks if "skip_reason" not in t]

    # Token rule 5: parallel calls cannot share a cache entry that is still being written. When
    # the reader prefix is long enough to cache, one task per reader type goes first (round 0)
    # and the rest fan out after it (round 1). When it is too short to cache, all go at once.
    seen_readers = set()
    for t in tasks:
        cacheable = prefix_is_cacheable("reader", system_prompt(t["reader"]), s)
        t["round"] = 1 if (cacheable and not t["cached"] and t["reader"] in seen_readers) else 0
        if not t["cached"]:
            seen_readers.add(t["reader"])
    emit("compared", f"{len(job['direction_items'])} Direction Note items to compare", "running", items=len(job["direction_items"]), tasks=len(tasks))
    return {"tasks": tasks + [{**t, "no_evidence": True} for t in direct], "skipped": skipped}


def _sends(state: State, round_no: int) -> list[Send]:
    files = state["files"]
    out = []
    for t in state["tasks"]:
        if t.get("no_evidence") or t["round"] != round_no:
            continue
        out.append(Send("read", {"task": t, "files": files}))
    return out


def route_after_plan(state: State):
    return _sends(state, 0) or "judge"


# --- 6. read (model, parallel fan-out) --------------------------------------------------------

def read(payload: dict) -> dict:
    """One reader subagent per task. The result is a pure function of the task (question, chunk
    hashes, model and skill versions), so it is cached by exact match with LangGraph's node
    cache: an unchanged task makes no model call on a later run."""
    task, files = payload["task"], payload["files"]
    s, store = get_settings(), get_store()
    chunks = store.get_chunks(task["client_id"], task["job_id"], task["chunk_ids"])  # scoped to this client and job
    needed = {c["file_id"] for c in chunks} | set(task.get("listing_ids", []))
    result = run_reader(task, chunks, {k: v for k, v in files.items() if k in needed}, store, task.get("allow_tools", False), s)
    # `cached` tasks reserved nothing in plan; if the cache entry turned out to be gone, count the real usage.
    reserved = 0 if task.get("cached") else task["est_input"]
    budget_for(task["origin_run_id"]).settle(reserved, result["usage"], extra_calls=result["calls"] - (0 if task.get("cached") else 1))
    StoreCache(store).set_value(DONE_NS, task["cache_key"], True)
    return {
        "reader_results": [{
            "task_id": task["task_id"], "cache_key": task["cache_key"], "reader": task["reader"], "direction_ref": task["direction_ref"],
            "rule_id": task["rule_id"], "findings": result["findings"], "tool_used": result["tool_used"],
            "origin_run_id": task["origin_run_id"], "skill_versions": result["skill_versions"],
        }],
        "evidence": result["evidence"],
        "usage": [{"node": "read", "task_id": task["task_id"], "model": result["model"], "calls": result["calls"],
                   "run_id": task["origin_run_id"], **result["usage"]}],
    }


def collect(state: State) -> dict:
    return {"round": state.get("round", 0) + 1}


def route_after_collect(state: State):
    if state["round"] == 1:
        later = _sends(state, 1)
        if later:
            return later
    return "judge"


# --- 7. judge (model, one call) ---------------------------------------------------------------

AREA = {"ledger_reader": "ledger", "statements_reader": "financial statements", "tax_reader": "tax", "workpaper_reader": "workpapers"}


def _judge_inputs(state: State) -> list[dict]:
    """Compact findings for the judge: rule findings, reader findings, and items with nothing
    to read. Ids are stable across runs so the judge's answer can be cached by exact match."""
    answered_rules = {r["rule_id"] for r in state.get("reader_results", []) if r["rule_id"]}
    rule_by_id = {f["id"]: f for f in state["rule_findings"]}
    inputs = []
    for f in state["rule_findings"]:
        if f["needs_judgment"] and f["id"] in answered_rules:
            continue  # a reader looked into it; its answer carries the point
        inputs.append({k: f[k] for k in ("id", "direction_ref", "area", "status", "severity", "title", "why", "evidence_ids", "source")})
    for r in sorted(state.get("reader_results", []), key=lambda r: r["cache_key"]):
        rule = rule_by_id.get(r["rule_id"])
        for n, f in enumerate(r["findings"], start=1):
            inputs.append({
                "id": f"A-{r['cache_key'][:8]}-{n}", "direction_ref": r["direction_ref"], "area": rule["area"] if rule else AREA[r["reader"]],
                "status": f["status"], "severity": f["severity"], "title": f["title"], "why": f["why"],
                "evidence_ids": list(dict.fromkeys(f["evidence_ids"] + (rule["evidence_ids"] if rule else []))), "source": "ai",
            })
    for t in state["tasks"]:
        if t.get("no_evidence") and t["direction_ref"] != "none":
            inputs.append({
                "id": f"none-{t['direction_ref']}", "direction_ref": t["direction_ref"], "area": "Direction Note", "status": "unclear", "severity": "medium",
                "title": "Nothing in the folder relates to this item", "why": "No document in the job folder matches this item. Where is it covered?",
                "evidence_ids": [], "source": "rule",
            })
    return inputs


def _passthrough(inputs: list[dict]) -> dict:
    """Used only when the judge cannot run (budget reached, or its answer was unusable): the
    findings go through as they are, clearly marked, rather than losing the run."""
    return {
        "summary": "The findings below were not consolidated by the judge step.",
        "findings": [{**f, "kind": "rule" if f["source"] == "rule" else "ai_suggestion", "confidence": "high" if f["source"] == "rule" else "low"} for f in inputs],
    }


def judge(state: State) -> dict:
    s, store, job = get_settings(), get_store(), state["job"]
    run_id = state["run_id"]
    emit("judged", "Weighing the findings", "running")
    inputs = _judge_inputs(state)
    # Items a reader never got to (the run's limit): reported as "not checked", not as "no evidence".
    not_checked = {k["direction_ref"] for k in state.get("skipped", []) if k["task_id"].startswith("T")}
    evidence = state.get("evidence", {})
    items = job["direction_items"]
    cache = StoreCache(store)
    body = J.judge_input(items, inputs)
    key = J.judge_cache_key(job["client_id"], state["job_id"], body, s)
    usage, skipped, source = [], [], "model"
    raw = cache.get_value("judge", key)  # exact match only; never a semantic cache for the judge
    if raw is not None:
        source = "cache"
    elif not inputs:
        raw, source = {"summary": "Nothing needed judgment.", "findings": []}, "code"
    else:
        est = est_tokens(J.judge_system()) + est_tokens(body)
        reason = budget_for(run_id).can_call(est)
        if reason:
            raw, source = _passthrough(inputs), "passthrough"
            skipped.append({"task_id": "judge", "direction_ref": "none", "what": "Consolidating the findings", "reason": reason})
        else:
            try:
                raw, u = J.call_judge(items, inputs, s)
                budget_for(run_id).add(u)
                usage.append({"node": "judge", "task_id": "judge", "model": model_id("judge", s), "calls": 1, "run_id": run_id, **u})
                J.validate_result(raw, inputs, evidence, items, not_checked)  # must validate before it is cached
                cache.set_value("judge", key, raw)
            except (ValueError, ValidationError, KeyError) as exc:
                if isinstance(exc, J.Unusable):  # paid for even though it cannot be used
                    budget_for(run_id).add(exc.usage)
                    usage.append({"node": "judge", "task_id": "judge", "model": model_id("judge", s), "calls": 1, "run_id": run_id, **exc.usage})
                raw, source = _passthrough(inputs), "passthrough"
                skipped.append({"task_id": "judge", "direction_ref": "none", "what": "Consolidating the findings", "reason": f"the judge's answer could not be used ({exc if isinstance(exc, J.Unusable) else type(exc).__name__})"})
    result, notes = J.validate_result(raw, inputs, evidence, items, not_checked)
    notes.update(findings_in=len(inputs), findings_out=len(result["findings"]), judge_source=source)
    emit("judged", f"{len(inputs)} findings weighed, {len(result['findings'])} kept", findings_in=len(inputs), findings_out=len(result["findings"]))
    return {"judge_inputs": inputs, "result": result, "notes": notes, "usage": usage, "skipped": skipped}


def route_after_judge(state: State):
    return "escalate" if any(J.needs_escalation(f) for f in state["result"]["findings"]) else "publish"


# --- 8. escalate (model, conditional) ---------------------------------------------------------

def escalate(state: State) -> dict:
    """Only findings that are high severity and low confidence go to the larger model, one
    finding per call."""
    s, store, run_id = get_settings(), get_store(), state["run_id"]
    cache = StoreCache(store)
    evidence = state.get("evidence", {})
    findings, usage, skipped, escalated = [], [], [], 0
    for f in state["result"]["findings"]:
        if not J.needs_escalation(f):
            findings.append(f)
            continue
        ev = [evidence[e] for e in f["evidence_ids"] if e in evidence]
        key = sha(state["job"]["client_id"], state["job_id"], model_id("escalate", s), s.prompt_version, f["title"], f["why"], *[e["id"] for e in ev])
        verdict = cache.get_value("escalate", key)
        if verdict is None:
            reason = budget_for(run_id).can_call(600)
            if reason:
                skipped.append({"task_id": f["id"], "direction_ref": f["direction_ref"], "what": f"Second look at: {f['title']}", "reason": reason})
                findings.append(f)
                continue
            try:
                verdict, u = J.call_escalate(f, ev, s)
            except (ValueError, KeyError):
                findings.append(f)
                continue
            budget_for(run_id).add(u)
            usage.append({"node": "escalate", "task_id": f["id"], "model": model_id("escalate", s), "calls": 1, "run_id": run_id, **u})
            cache.set_value("escalate", key, verdict)
        escalated += 1
        updated = {**f, **verdict}
        if not updated["evidence_ids"] and updated["status"] not in ("missing", "unclear"):
            updated["status"] = "unclear"
        findings.append(updated)
    notes = {**state["notes"], "escalated": escalated}
    emit("judged", f"{escalated} finding{'s' if escalated != 1 else ''} given a second look", escalated=escalated)
    return {"result": {**state["result"], "findings": findings}, "notes": notes, "usage": usage, "skipped": skipped}


# --- 9. publish (code) ------------------------------------------------------------------------

def build_final(state: State) -> dict:
    s, job, run_id = get_settings(), state["job"], state["run_id"]
    result, notes = state["result"], state["notes"]
    evidence = state.get("evidence", {})
    order = {"high": 0, "medium": 1, "low": 2}
    # Findings of the year-on-year analysis are added as they are: code made the checks, and the
    # model's coverage statements were already checked against real ids and figures.
    findings = sorted(result["findings"] + state.get("analysis_findings", []),
                      key=lambda f: (f["status"] == "addressed", order[f["severity"]], f["id"]))
    used_evidence = {e for f in findings for e in f["evidence_ids"]}
    verdict = J.compute_verdict(findings, job["direction_items"])

    calls = [u for u in state.get("usage", []) if u["run_id"] == run_id]  # this run's own model calls
    run_budget = budget_for(run_id)
    totals = empty_usage()
    cost = 0.0
    for u in calls:
        for k in totals:
            totals[k] += u[k]
        cost += cost_usd(u["model"], u, s) if not u["model"].startswith("fake-") else 0.0
    all_input = totals["input"] + totals["cache_read"] + totals["cache_write"]
    results = state.get("reader_results", [])
    reused = [r for r in results if r["origin_run_id"] != run_id]
    reader_calls = sum(u["calls"] for u in calls if u["node"] == "read")
    skipped = state.get("skipped", [])
    by_key = {r["cache_key"]: r for r in results}
    drafted_n = len((state.get("drafted") or {}).get("items", []))
    files = state["files"]
    changed = set(state["sync"]["changed"])
    rules = state["rule_results"]
    ai_read = set(state.get("ai_read", []))
    images_now = sum(u["calls"] for u in calls if u["node"] == "read_image")
    read_label = f"{len(files)} documents, " + ("all new" if state["sync"]["first_run"] else f"{len(changed)} changed since last run")
    if images_now:
        read_label += f", {images_now} image{'s' if images_now != 1 else ''} read by AI"

    trail = {
        "read": {
            "label": read_label,
            "documents": len(files), "changed": len(changed), "removed": state["sync"]["removed"], "images_read": images_now,
            "detail": [{"name": display_name(f), "kind": f["document_class"].replace("_", " "), "changed": fid in changed, "problem": f["error"],
                        "note": "text read from the image by AI" if fid in ai_read else "", "year": f.get("year_label", "")}
                       for fid, f in sorted(files.items(), key=lambda kv: (kv[1].get("year") or 0, kv[1]["name"].lower()), reverse=False)],
        },
        "checked": {
            "label": rules_label(rules),
            "rules": len(rules), "failed": sum(1 for r in rules if r["passed"] is False and not r["needs_judgment"]),
            "flagged": sum(1 for r in rules if r["passed"] is False and r["needs_judgment"]),
            "detail": [{"label": r["label"], "passed": r["passed"], "flagged": bool(r["needs_judgment"]) and not r["passed"],
                        "note": "" if r["passed"] else r["title"]} for r in rules],
        },
        "compared": {
            "label": f"{len(job['direction_items'])} Direction Note items compared" + (f", {drafted_n} drafted by AI" if drafted_n else "")
                     + (f"; compared with {state['analysis']['last_year']} accounts" if (state.get("analysis") or {}).get("available") else ""),
            "items": len(job["direction_items"]), "drafted": drafted_n, "drafted_how": (state.get("drafted") or {}).get("how", ""),
            "history_jobs": (state.get("drafted") or {}).get("jobs_seen", 0), "reader_calls": reader_calls, "reused": len(reused), "skipped": len([k for k in skipped if k["task_id"].startswith("T")]),
            "detail": [{
                "ref": t["direction_ref"], "what": t["direction_text"] or t["question"], "reader": t["reader"].replace("_", " "),
                "passages": t["chunk_refs"],
                "outcome": "nothing to read" if t.get("no_evidence") else ("reused from an earlier run" if t["cache_key"] in by_key and by_key[t["cache_key"]]["origin_run_id"] != run_id else "read"),
            } for t in state["tasks"]],
        },
        "judged": {
            "label": f"{notes['findings_in']} findings weighed, {notes['findings_out']} kept",
            "findings_in": notes["findings_in"], "findings_out": len(findings), "escalated": notes.get("escalated", 0), "how": notes["judge_source"],
            "detail": [],
        },
        "verified": {
            "label": f"{len(used_evidence)} source passages linked",
            "evidence": len(used_evidence), "rejected_no_evidence": notes["rejected_no_evidence"],
            "rules_restored": notes["rules_restored"], "items_filled": notes["items_filled"],
            "detail": [],
        },
    }
    status = "partial" if skipped else "complete"
    return {
        "run_id": run_id, "job_id": state["job_id"], "status": status, **verdict,
        "summary": result["summary"], "findings": findings,
        "evidence": [evidence[e] for e in sorted(used_evidence) if e in evidence],
        "trail": trail, "skipped": skipped,
        "analysis": state.get("analysis") or A.unavailable("The year-on-year analysis did not run."),
        "periods": {"this_year": (state.get("periods") or {}).get("current"), "last_year": (state.get("periods") or {}).get("prior"),
                    "split": (state.get("periods") or {}).get("split", False)},
        "usage": {
            "calls": calls, "totals": totals, "model_calls": sum(u["calls"] for u in calls), "reader_calls": reader_calls,
            "cost_usd": round(cost, 6), "cache_share": round(totals["cache_read"] / all_input, 3) if all_input else 0.0,
            "reused_answers": len(reused),
            # The budget this run actually had, after it grew to fit the work.
            "budget": {"reader_calls": run_budget.reader_calls, "image_calls": run_budget.image_calls,
                       "uncached_input_tokens": run_budget.uncached_input, "output_tokens": run_budget.output,
                       "reserved_for_judge_and_analysis": run_budget.reserve},
        },
        "models": {role: model_id(role, s) for role in ("reader", "judge", "escalate")},
        "versions": {"prompt": s.prompt_version, "parser": s.parser_version, "skills": {name: sk.version for name, sk in all_skills().items()}},
        "knowledge_ids": job.get("knowledge_ids", []),
        "demo": s.llm_mode == "fake",
        "duration_s": round(time.time() - state["started_at"], 1),
    }


def publish(state: State) -> dict:
    """Compute the verdict in code, save, emit the completion event. Nothing here touches the
    job itself: this service never marks a job as reviewed."""
    final = build_final(state)
    get_store().save_run(state["run_id"], state["job_id"], final["status"], final)
    emit("verified", final["trail"]["verified"]["label"], evidence=final["trail"]["verified"]["evidence"])
    get_pm().send_event(state["run_id"], {"type": "ai_precheck.completed", "job_id": state["job_id"], "result": final})
    return {"final": final}


def build_graph(checkpointer=None):
    g = StateGraph(State)
    g.add_node("load_job", load_job)
    g.add_node("sync_drive", sync_drive)
    g.add_node("index", index)
    g.add_node("run_rules", run_rules)
    g.add_node("plan", plan)
    # Exact-match node cache (token rule 6): the key is the hash of model, skill versions,
    # question and chunk hashes. Needs langgraph-checkpoint >= 4.0.0, which fixes a cache
    # deserialization vulnerability; requirements.txt pins it.
    g.add_node("read", read, cache_policy=CachePolicy(key_func=lambda payload: payload["task"]["cache_key"]))
    g.add_node("collect", collect)
    g.add_node("judge", judge)
    g.add_node("escalate", escalate)
    g.add_node("publish", publish)
    g.add_edge(START, "load_job")
    g.add_edge("load_job", "sync_drive")
    g.add_edge("sync_drive", "index")
    g.add_edge("index", "run_rules")
    g.add_node("draft_directions", draft_directions)
    g.add_node("analyse", analyse)
    g.add_edge("run_rules", "analyse")
    g.add_conditional_edges("analyse", route_after_rules, ["draft_directions", "plan"])
    g.add_conditional_edges("draft_directions", route_after_draft, ["plan", END])
    g.add_conditional_edges("plan", route_after_plan, ["read", "judge"])
    g.add_edge("read", "collect")
    g.add_conditional_edges("collect", route_after_collect, ["read", "judge"])
    g.add_conditional_edges("judge", route_after_judge, ["escalate", "publish"])
    g.add_edge("escalate", "publish")
    g.add_edge("publish", END)
    return g.compile(checkpointer=checkpointer, cache=StoreCache(get_store()))
