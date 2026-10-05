"""The pre-check graph.

    load_job -> sync_drive -> index -> run_rules -> key_documents -> precheck -> publish
                                                         \\-> publish (blocked: a key document is missing)
    draft mode:  ... -> run_rules -> draft_directions

Everything before `precheck` is code: the folder is listed and read (zips, emails, images — a
picture or scan is written out once by Haiku, see vision.py), each document's year is decided,
the checks with a right answer run, and the three key documents are looked for. If this year's
questionnaire, last year's financial statements or last year's workpapers are missing, the run
stops there and drafts the request for them. Otherwise one Opus call does the professional
pre-check (see precheck.py): business nature, and every item still needed with its reason.
"""
import logging
import os
import time
from typing import Annotated, TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from . import analysis as A
from . import directions as D
from . import keydocs as K
from . import precheck as P
from . import vision
from .archives import attachments as email_attachments
from .archives import container_of, display_name
from .archives import members as archive_members
from .budget import budget_for, cost_usd, empty_usage
from .classify import classify, classify_email
from .config import get_settings
from .drive import DriveError, get_drive, is_zip
from .emails import is_email
from .embeddings import get_embedder
from .llm import model_id
from .parsing import chunk_blocks, parse_file, scrub
from .periods import assign_years, year_label
from .pm_client import get_pm
from .rules import run_rules as apply_rules
from .skills_loader import all_skills
from .store import StoreCache, get_store
from .textutil import est_tokens, sha

logger = logging.getLogger(__name__)

PENDING_NS = "pending"  # a file with an image still to read: looked at again on the next run


def _pending_key(client_id: str, job_id: str, file_id: str) -> str:
    return sha(client_id, job_id, file_id)


class PrecheckStop(Exception):
    """The run cannot continue, for a reason a person can act on (shown on the task card)."""


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


def _concat(a: list, b: list) -> list:
    return a + b


class State(TypedDict, total=False):
    run_id: str
    job_id: str
    mode: str  # "precheck" (default) | "draft" (only draft the Direction Note)
    drafted: dict
    started_at: float
    job: dict
    listing: list[dict]
    sync: dict
    files: dict[str, dict]
    ai_read: list[str]  # ids of files whose text was read from an image by the model
    rule_results: list[dict]
    periods: dict
    key: dict
    precheck: dict
    evidence: Annotated[dict, _merge]
    usage: Annotated[list, _concat]
    skipped: Annotated[list, _concat]
    final: dict


def emit(stage: str, label: str, state: str = "done", **counts) -> None:
    """One custom stream event per step: which of the five trail steps it belongs to, a plain
    label and real counts. The task card's "How the AI got here" strip is built from these."""
    get_stream_writer()({"stage": stage, "state": state, "label": label, "counts": counts})


def _docs(files: dict[str, dict]) -> list[dict]:
    store = get_store()
    return [{"file": row, "parsed": store.get_parsed(sha(row["file_id"], row["version"], row["parser_version"])) or {"blocks": [], "tables": []}}
            for row in files.values()]


# --- 1. load_job (code) -----------------------------------------------------------------------

def load_job(state: State) -> dict:
    emit("read", "Opening the task", "running")
    s = get_settings()
    if s.llm_mode != "fake" and not (s.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")):
        raise PrecheckStop("The pre-check service has no Claude API key configured. Ask an administrator to set it.")
    job = get_pm().get_job(state["job_id"])
    if not job.get("drive_folder_id"):
        raise PrecheckStop("This task has no Google Drive folder linked. Add the folder on the task card, then run the pre-check.")
    if not job.get("client_id"):
        raise PrecheckStop("This task's project is not in a sub-workspace, so the pre-check cannot keep its documents separate. Put the project in a sub-workspace first.")
    job = {**job, "direction_items": D.normalize_items(job.get("direction_items") or [])}
    return {"job": job, "started_at": state.get("started_at") or time.time()}


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
            store.set_parsed(parsed_key, scrub(parsed))
    # Some files carry NUL and other control characters in their text; Postgres will not store
    # them, and a single such file used to stop the whole run. Cleaned on the way in, and again
    # here for anything cached before this existed.
    parsed = scrub(parsed)
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
    """Which year each document belongs to, then the checks with a right answer. When the folder
    holds last year's finished pack as well, the checks run on this year's documents only."""
    s = get_settings()
    emit("checked", "Running the checks done by code", "running")
    docs = _docs(state["files"])
    ai_read = [d["file"]["file_id"] for d in docs if d["parsed"].get("read_by") == vision.AI_READ]
    periods = assign_years(docs, state["job"])
    files = {}
    for fid, row in state["files"].items():
        info = periods["by_file"].get(fid, {"year": None, "role": "unknown"})
        files[fid] = {**row, "year": info["year"], "year_role": info["role"], "year_label": year_label(info["role"], info["year"])}
    checked = [d for d in docs if periods["by_file"][d["file"]["file_id"]]["role"] in ("current", "unknown")] if periods["split"] else docs
    results = []
    for r in apply_rules(checked, s):
        if r["rule_id"].startswith("required:"):
            continue  # the key documents step decides what must be there
        r["evidence_pairs"] = [(f, b) for f, b in r.pop("evidence") if b]
        results.append(r)
    failed = sum(1 for r in results if r["passed"] is False)
    emit("checked", f"{len(results)} checks by code, {failed} failed", checks=len(results), failed=failed)
    return {"rule_results": results, "ai_read": ai_read, "periods": periods, "files": files}


def route_after_rules(state: State):
    return "draft_directions" if state.get("mode") == "draft" else "key_documents"


# --- 5. key_documents (code) --------------------------------------------------------------------

def key_documents(state: State) -> dict:
    """This year's questionnaire, last year's financial statements, last year's workpapers. A
    pre-check does not start without all three (AFIT, 5 Oct 2026)."""
    docs = [{"file": state["files"][d["file"]["file_id"]], "parsed": d["parsed"]} for d in _docs(state["files"])]
    key = K.find(docs, state["periods"])
    # Every workpaper for the pre-check's input; the card shows a few per role.
    key["documents"] = [{**k, "files_all": k["files"]} for k in key["documents"]]
    wp = next(k for k in key["documents"] if k["role"] == "last_year_workpapers")
    if wp["found"]:
        wp["files_all"] = [d["file"] for d in docs if d["file"].get("year_role") in ("prior",) or (not state["periods"].get("current") and d["file"].get("year_role") == "unknown")]
        wp["files_all"] = [f for f in wp["files_all"] if f["document_class"] in K.WP_CLASSES]
    marks = ", ".join(f"{k['label'].lower()} {'found' if k['found'] else 'missing'}" for k in key["documents"])
    emit("compared", f"Key documents: {marks}", missing=len(key["missing"]))
    return {"key": key}


def route_after_key(state: State):
    return "publish" if state["key"]["missing"] else "precheck"


# --- 6. precheck (model: Opus, one call) -----------------------------------------------------------

def precheck(state: State) -> dict:
    s, store, job, run_id = get_settings(), get_store(), state["job"], state["run_id"]
    emit("judged", "Pre-checking: reading the questionnaire, last year's accounts and workpapers", "running")
    docs = [{"file": state["files"][d["file"]["file_id"]], "parsed": d["parsed"]} for d in _docs(state["files"])]
    last_year_ids = {f["file_id"] for k in state["key"]["documents"] if k["role"] != "questionnaire" for f in k["files_all"]}
    prior = [d for d in docs if d["file"].get("year_role") in ("prior", "older") or d["file"]["file_id"] in last_year_ids]
    current = [d for d in docs if d not in prior]
    facts = A.prepare(prior, current, state["periods"], s)
    facts["checks"] = facts["checks"] + [
        {"id": r["rule_id"], "label": r["title"] or r["label"], "passed": False, "detail": r["why"], "evidence": r["evidence_pairs"]}
        for r in state["rule_results"] if r["passed"] is False
    ]
    fixed = job.get("precheck_type") if job.get("precheck_type") in P.TYPES else ""
    body, index = P.fit_input(lambda caps: P.build_input(job, state["key"], docs, state["files"], state["periods"], facts,
                                                         job.get("lessons", []), s, caps), s)
    cache = StoreCache(store)
    key = P.cache_key(job["client_id"], state["job_id"], body, s)
    usage, how = [], "model"
    cleaned = cache.get_value("precheck", key)
    if cleaned is not None:
        how = "cache"
    else:
        reason = budget_for(run_id).can_call(est_tokens(P.system_text()) + est_tokens(body))
        if reason:
            raise PrecheckStop(f"The pre-check could not run: {reason}. Ask an administrator to raise the run budget.")
        try:
            raw, u = P.call_model(body, s)
        except P.Unusable as exc:
            logger.warning("Pre-check answer unusable: %s", exc)
            raise PrecheckStop(f"{exc} Nothing was changed. Please try again.") from exc
        budget_for(run_id).add(u)
        usage.append({"node": "precheck", "task_id": "precheck", "model": model_id("precheck", s), "calls": 1, "run_id": run_id, **u})
        cleaned = P.clean(raw, index, body, fixed)
        cache.set_value("precheck", key, cleaned)
    output, evidence = P.assemble(cleaned, index, state["key"], facts, job.get("client_name", ""))
    output["how"] = how
    n = {k: len(output[k]) for k in ("requests", "provided", "not_needed")}
    emit("judged", f"{output['business_nature']['label']}: {n['requests']} to request, {n['provided']} already provided, {n['not_needed']} not needed",
         **n)
    return {"precheck": output, "evidence": evidence, "usage": usage}


# --- draft_directions (model; only when a person asks for a draft) ---------------------------------------

def draft_directions(state: State) -> dict:
    """Draft a Direction Note from this client's past tasks and what is in the folder now. One
    call to the drafting model, cached by exact match; if the model cannot be used, code falls back
    to the standard list for the kinds of document present."""
    s, store, job, run_id = get_settings(), get_store(), state["job"], state["run_id"]
    emit("compared", "Drafting the Direction Note from past tasks and the folder", "running")
    cache = StoreCache(store)
    rule_results = [{**r, "evidence": []} for r in state["rule_results"]]
    body = D.draft_input(job, state["files"], rule_results)
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
                usage.append({"node": "draft", "task_id": "draft", "model": model_id("drafter", s), "calls": 1, "run_id": run_id, **u})
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
    emit("compared", f"{len(new)} Direction Note items drafted", drafted=len(new))
    get_pm().send_event(run_id, {
        "type": "ai_precheck.directions_drafted", "job_id": state["job_id"], "items": new, "how": how, "final": True,
        "usage": usage, "versions": {"prompt": s.prompt_version, "skills": {n: sk.version for n, sk in all_skills().items()}},
    })
    return {"drafted": drafted, "usage": usage, "skipped": skipped}


# --- 7. publish (code) ------------------------------------------------------------------------

def blocked_output(state: State) -> tuple[dict, dict]:
    """A key document is missing: the decision, what was found, and the email asking for the rest."""
    key, evidence = state["key"], {}

    def ev(e):
        evidence[e["id"]] = e
        return e["id"]

    names = [k["label"].lower() for k in key["documents"] if not k["found"]]
    names = [n if n.startswith("last year") else f"this year's {n}" for n in names]
    missing = " and ".join([", ".join(names[:-1]), names[-1]] if len(names) > 1 else names)
    it = "They have" if len(names) > 1 else "It has"
    out = {
        "decision": {"state": "blocked", "label": "Blocked",
                     "reason": f"The pre-check cannot start without {missing}. {it} been requested; run the pre-check again once "
                               f"{'they arrive' if len(names) > 1 else 'it arrives'}."},
        "key_documents": P.key_views(key, ev),
        "business_nature": None,
        "requests": [{"group": "To start the pre-check", "item": K.KEY[r]["ask"].format(this_year=key["this_year"], last_year=key["last_year"]),
                      "decision": "request", "reason": K.KEY[r]["why"], "sources": [], "documents": [], "flags": []} for r in key["missing"]],
        "provided": [], "not_needed": [], "preparer_notes": [], "lessons_applied": [], "bank": [], "checks": [],
        "email": K.request_email(state["job"].get("client_name", ""), key),
        "how": "code",
    }
    out["evidence"] = {k: {f: e[f] for f in ("file_name", "location", "quote", "drive_url")} for k, e in evidence.items()}
    return out, evidence


VERDICT = {"blocked": "not_ready", "requests": "ready_with_exceptions", "nothing": "ready"}


def build_final(state: State) -> dict:
    s, job, run_id = get_settings(), state["job"], state["run_id"]
    if state.get("precheck"):
        out = state["precheck"]
    else:
        out, _ = blocked_output(state)
    files, changed = state["files"], set(state["sync"]["changed"])
    ai_read = set(state.get("ai_read", []))
    calls = [u for u in state.get("usage", []) if u["run_id"] == run_id]
    totals = empty_usage()
    cost = 0.0
    for u in calls:
        for k in totals:
            totals[k] += u[k]
        cost += cost_usd(u["model"], u, s) if not u["model"].startswith("fake-") else 0.0
    images_now = sum(u["calls"] for u in calls if u["node"] == "read_image")
    rules = state.get("rule_results", [])
    shown = [f for f in files.values() if not (f["document_class"] == "archive" and not f["error"])]
    read_label = f"{len(shown)} documents, " + ("all new" if state["sync"]["first_run"] else f"{len(changed)} changed since last run")
    if images_now:
        read_label += f", {images_now} image{'s' if images_now != 1 else ''} read by AI"
    nature = out.get("business_nature")
    state_ = out["decision"]["state"]
    checks = out.get("checks") or [{"label": r["title"] or r["label"], "passed": r["passed"], "detail": r["why"]} for r in rules]
    trail = {
        "read": {
            "label": read_label, "documents": len(shown), "changed": len(changed), "removed": state["sync"]["removed"], "images_read": images_now,
            "detail": [{"name": display_name(f), "kind": f["document_class"].replace("_", " "), "changed": f["file_id"] in changed, "problem": f["error"],
                        "note": "text read from the image by AI" if f["file_id"] in ai_read else "", "year": f.get("year_label", "")}
                       for f in sorted(shown, key=lambda f: (f.get("year") or 0, f["name"].lower()))],
        },
        "checked": {
            "label": f"{len(checks)} checks by code, {sum(1 for c in checks if not c['passed'])} failed",
            "detail": [{"label": c["label"], "passed": c["passed"], "note": "" if c["passed"] else c["detail"]} for c in checks],
        },
        "compared": {
            "label": "Key documents: " + ", ".join(f"{k['label'].lower()} {'found' if k['found'] else 'missing'}" for k in out["key_documents"]),
            "detail": [{"label": k["label"], "passed": k["found"], "note": ", ".join(f["name"] for f in k["files"]) or k["note"] or "not in the folder"}
                       for k in out["key_documents"]],
        },
        "judged": {
            "label": (f"{nature['label']}: {len(out['requests'])} to request, {len(out['provided'])} already provided, {len(out['not_needed'])} not needed"
                      if nature else "Not run: a key document is missing"),
            "how": out.get("how", ""), "detail": [],
        },
        "verified": {
            "label": f"{len(out.get('evidence', {}))} sources linked; "
                     f"{sum(1 for i in out['requests'] + out['provided'] if i.get('flags'))} items flagged for a closer look",
            "evidence": len(out.get("evidence", {})), "detail": [],
        },
    }
    all_input = totals["input"] + totals["cache_read"] + totals["cache_write"]
    return {
        # Partial when something was left for the next run (e.g. images over the run's limit).
        "run_id": run_id, "job_id": state["job_id"], "status": "partial" if state.get("skipped") else "complete",
        "verdict": VERDICT[state_], "readiness": out["decision"]["label"], "summary": out["decision"]["reason"][:400],
        "coverage": {"addressed": len(out["provided"]), "total": len(out["provided"]) + len(out["requests"])},
        "counts": {"high": len(out["requests"]) if state_ == "blocked" else 0, "medium": len(out["requests"]) if state_ != "blocked" else 0, "low": 0},
        "direction_items": [{**i, "addressed": False} for i in job.get("direction_items", [])],
        "findings": [], "evidence": [],
        "precheck_type": nature["type"] if nature else (job.get("precheck_type") or "auto"),
        "precheck": out,
        "trail": trail, "skipped": state.get("skipped", []),
        "usage": {
            "calls": calls, "totals": totals, "model_calls": sum(u["calls"] for u in calls), "reader_calls": 0,
            "cost_usd": round(cost, 6), "cache_share": round(totals["cache_read"] / all_input, 3) if all_input else 0.0, "reused_answers": 0,
            "budget": {"image_calls": s.budget_image_calls, "uncached_input_tokens": s.run_input_tokens, "output_tokens": s.run_output_tokens},
        },
        "models": {role: model_id(role, s) for role in ("precheck", "vision")},
        "versions": {"prompt": s.prompt_version, "parser": s.parser_version, "skills": {name: sk.version for name, sk in all_skills().items()}},
        "knowledge_ids": job.get("knowledge_ids", []),
        "demo": s.llm_mode == "fake",
        "duration_s": round(time.time() - state["started_at"], 1),
    }


def publish(state: State) -> dict:
    """Save and send the result. Nothing here touches the task: the pre-check never marks a task
    reviewed, and the email is drafted, never sent."""
    final = build_final(state)
    get_store().save_run(state["run_id"], state["job_id"], final["status"], final)
    emit("verified", final["trail"]["verified"]["label"], evidence=final["trail"]["verified"]["evidence"])
    get_pm().send_event(state["run_id"], {"type": "ai_precheck.completed", "job_id": state["job_id"], "result": final})
    return {"final": final}


def build_graph(checkpointer=None):
    g = StateGraph(State)
    for name, fn in [("load_job", load_job), ("sync_drive", sync_drive), ("index", index), ("run_rules", run_rules),
                     ("key_documents", key_documents), ("precheck", precheck), ("draft_directions", draft_directions), ("publish", publish)]:
        g.add_node(name, fn)
    g.add_edge(START, "load_job")
    g.add_edge("load_job", "sync_drive")
    g.add_edge("sync_drive", "index")
    g.add_edge("index", "run_rules")
    g.add_conditional_edges("run_rules", route_after_rules, ["draft_directions", "key_documents"])
    g.add_conditional_edges("key_documents", route_after_key, ["publish", "precheck"])
    g.add_edge("precheck", "publish")
    g.add_edge("draft_directions", END)
    g.add_edge("publish", END)
    return g.compile(checkpointer=checkpointer, cache=StoreCache(get_store()))
