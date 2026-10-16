"""Starting a pre-check, receiving its events, and shaping what the job card shows."""
import json
import re
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.live.broadcast import notify

from . import review as review_record
from .models import CARD_PATH_ROLES, PRECHECK_TYPES, AIEvidence, AIFeedback, AIFinding, AIPrecheck, DirectionItem, ModelRun

MAX_PROGRESS_EVENTS = 60


def can_open_job(user, issue) -> bool:
    """Who may run or see a job's pre-check: exactly who may open the job. In AFIT Connect
    today every signed-in member can open every job; if job access is ever restricted, change
    it here and the pre-check follows."""
    return bool(user and user.is_authenticated)


def client_scope(issue) -> str:
    """The boundary the agent keeps documents inside. A job in a client's workspace belongs to
    that client; an internal workspace is its own boundary."""
    project = issue.project
    return f"client-{project.client_id}" if project.client_id else f"workspace-{project.id}"


SETTING_KEYS = ("year_start", "year_end", "xero_complete", "ird_access", "related_records")


def previous_requests(issue) -> list[dict]:
    """The requests of the last finished pre-check: the next one checks whether each has arrived."""
    latest = issue.prechecks.filter(kind=AIPrecheck.Kind.PRECHECK, status__in=["complete", "partial"]).order_by("-created_at").first()
    rows = ((latest.precheck or {}).get("requests") or []) if latest else []
    return [{"group": r.get("group", ""), "item": r.get("item", "")} for r in rows if r.get("item")][:60]


def answer_dict(a) -> dict:
    return {"id": a.id, "question": a.question, "answer": a.answer, "answered_by": a.answered_by.display_name if a.answered_by else "",
            "answered_at": a.answered_at}


def team_scope(issue) -> str:
    """The Workspace (team) a task sits in: its client's team, else its project's main team."""
    project = issue.project
    team_id = (project.client.team_id if project.client_id else None) or project.primary_team_id
    return f"team-{team_id}" if team_id else ""


def setup_for(issue) -> dict:
    folder = getattr(issue, "drive_folder", None)
    items = list(issue.direction_items.all())
    missing = []
    if not folder:
        missing.append("drive_folder")
    if not items:
        missing.append("direction_note")
    return {
        "drive_folder_url": folder.folder_url if folder else "",
        "drive_folder_id": folder.folder_id if folder else "",
        "precheck_type": folder.precheck_type if folder else "auto",
        "key_paths": {role: (folder.key_paths or {}).get(role, "") if folder else "" for role in CARD_PATH_ROLES},
        "settings": {k: (folder.accountant_settings or {}).get(k, "") if folder else "" for k in SETTING_KEYS},
        "precheck_types": [{"value": v, "label": label} for v, label in PRECHECK_TYPES],
        "direction_items": [{"id": i.ref, "text": i.text, "origin": i.origin, "reason": i.reason, "basis": i.basis} for i in items],
        "missing": missing,
        # Only the folder is needed to run: with no Direction Note the AI drafts one first.
        "ready": "drive_folder" not in missing,
    }


HISTORY_LIMIT = 25
_DECISION_ORDER = {"accepted": 0, "needs_clarification": 1, "none": 2, "rejected": 3, "not_applicable": 3}


def history_for(issue) -> dict:
    """What the AI may learn from when it drafts this job's Direction Note: the same client's
    other jobs (their Direction Note items, the open findings of their latest pre-check, and
    what people decided about those findings), plus this job's own last run. Never another
    client: the scope is the job's client, or its workspace when it has no client."""
    from apps.issues.models import Issue

    project = issue.project
    scope = Issue.objects.filter(project__client_id=project.client_id) if project.client_id else Issue.objects.filter(project=project)
    others = scope.exclude(pk=issue.pk)

    items: dict[str, dict] = {}
    for item in DirectionItem.objects.filter(issue__in=others):
        row = items.setdefault(item.text.lower(), {"text": item.text, "used": 0, "not_addressed": 0})
        row["used"] += 1

    findings, jobs_seen = [], set(DirectionItem.objects.filter(issue__in=others).values_list("issue_id", flat=True))
    finished = [AIPrecheck.Status.COMPLETE, AIPrecheck.Status.PARTIAL]
    runs = (
        AIPrecheck.objects.filter(issue__in=scope, kind=AIPrecheck.Kind.PRECHECK, status__in=finished)
        .order_by("issue_id", "-created_at")
        .prefetch_related("findings__feedback")
    )
    latest: dict[int, AIPrecheck] = {}
    for run in runs:
        latest.setdefault(run.issue_id, run)
    for issue_id, run in latest.items():
        own = issue_id == issue.pk
        if not own:
            jobs_seen.add(issue_id)
            for d in run.direction_items:
                if not d.get("addressed") and d.get("text", "").lower() in items:
                    items[d["text"].lower()]["not_addressed"] += 1
        for f in run.findings.all():
            if f.status == "addressed":
                continue
            decision = current_disposition(f)
            findings.append({
                "title": f.title, "area": f.area, "severity": f.severity,
                "decision": decision["disposition"] if decision else "none",
                "where": "this job, last run" if own else "an earlier job",
            })
    findings.sort(key=lambda f: (_DECISION_ORDER[f["decision"]], f["title"]))
    return {
        "past_items": sorted(items.values(), key=lambda r: (-r["used"], r["text"]))[:HISTORY_LIMIT],
        "past_findings": findings[:HISTORY_LIMIT],
        "jobs_seen": len(jobs_seen),
    }


MAX_LESSONS = 40


def lesson_dict(lesson) -> dict:
    return {"id": lesson.id, "scope": lesson.scope, "scope_label": lesson.get_scope_display(), "status": lesson.status, "kind": lesson.kind,
            "precheck_type": lesson.precheck_type, "item": lesson.item, "note": lesson.note, "source": lesson.source,
            "rule": {"title": lesson.rule_title, "when": lesson.rule_when, "do": lesson.rule_do, "why": lesson.rule_why} if lesson.rule_do else None,
            "drafting": lesson.drafting, "client_scope": lesson.client_scope, "project_scope": lesson.project_scope, "team_scope": lesson.team_scope,
            "created_by": lesson.created_by.display_name if lesson.created_by else "",
            "created_at": lesson.created_at, "task": lesson.issue.key if lesson.issue_id else ""}


def lessons_for(issue) -> list[dict]:
    """The lessons a pre-check of this task applies: this client's own, firm-wide ones a lead or
    admin approved, and firm-wide ones from this client still waiting (they apply here at once)."""
    from django.db.models import Q

    from .models import PrecheckLesson

    mine, team = client_scope(issue), team_scope(issue)
    wider = Q(scope="project", project_scope=f"project-{issue.project_id}", status="active") | Q(scope="firm", status="active")
    if team:
        wider |= Q(scope="team", team_scope=team, status="active")
    qs = PrecheckLesson.objects.filter(
        Q(client_scope=mine, status__in=["active", "pending"]) | wider
    ).exclude(status="disabled").select_related("created_by", "issue").order_by("-created_at")[:MAX_LESSONS]
    return [lesson_dict(lesson) for lesson in qs]


def can_approve_lessons(user, issue) -> bool:
    """A lead or an admin: staff, the project's lead or admin, or a lead of its workspace."""
    from apps.projects.permissions import can_manage_project
    from apps.teams.models import TeamMembership

    project = issue.project
    if user.is_staff or can_manage_project(user, project):
        return True
    return bool(project.primary_team_id) and TeamMembership.objects.filter(team_id=project.primary_team_id, user=user, role="lead").exists()


def job_payload(issue) -> dict:
    """What the agent's load_job node reads: the job card, its Direction Note items, the Drive
    folder and the client boundary. Approved knowledge is not built yet, so none is in scope."""
    setup = setup_for(issue)
    project = issue.project
    return {
        "job_id": str(issue.id),
        "key": issue.key,
        "title": issue.summary,
        "status": issue.status.name,
        "workspace": project.name,
        "client_id": client_scope(issue),
        # The card's place, for the knowledge store's tags: Workspace (team) > Sub-workspace
        # (client_id, the vendor) > Project > Task.
        "team_id": team_scope(issue),
        "project_id": f"project-{project.id}",
        "client_name": project.client.name if project.client_id else project.name,
        "drive_folder_id": setup["drive_folder_id"],
        "precheck_type": setup["precheck_type"],
        "key_paths": {role: path for role, path in setup["key_paths"].items() if path},
        "settings": {k: v for k, v in setup["settings"].items() if v},
        # Continuity: what the last pre-check asked for, and what the accountant has answered.
        "previous_requests": previous_requests(issue),
        "accountant_answers": [{"question": a.question, "answer": a.answer} for a in issue.accountant_answers.all()[:60]],
        "lessons": lessons_for(issue),
        # For a review round: the preparer's assumptions and every finding with the reviewer's response.
        "review": review_record.payload(issue),
        "direction_items": setup["direction_items"],
        "history": history_for(issue),
        "knowledge_ids": [],
    }


_BULLET = re.compile(r"^\s*(?:[-•*–·▪>]|\d{1,2}[.)]|[a-zA-Z][.)])\s+")


def clean_direction_lines(texts: list[str]) -> list[str]:
    """A Direction Note pasted from a document arrives one line per item. Put it back together:
    a line starting in lower case continues the one above, a heading ending in ":" leads each
    bullet under it, and bullet marks are dropped. (The agent applies the same rule to items
    saved before this existed.)"""
    out: list[dict] = []
    heading = ""
    for raw in texts:
        raw = " ".join(str(raw).split())
        bulleted = bool(_BULLET.match(raw))
        text = _BULLET.sub("", raw).strip()
        if not text:
            continue
        if out and not bulleted and not text.endswith(":") and text[0].islower() and not out[-1]["heading"]:
            out[-1]["text"] += " " + text
            continue
        if text.endswith(":"):
            heading = text.rstrip(":").strip()
            out.append({"text": heading, "heading": True, "used": False})
            continue
        if not bulleted:
            heading = ""
        if heading and bulleted:
            next(h for h in reversed(out) if h["heading"])["used"] = True
            text = f"{heading}: {text}"
        out.append({"text": text, "heading": False, "used": False})
    return [i["text"] for i in out if not (i["heading"] and i["used"])]


def save_direction_items(issue, texts: list[str], user) -> None:
    """Replace the job's Direction Note items, keeping the ref (and, for AI-drafted items, the
    origin and reason) of any item whose text is unchanged so earlier runs still line up. An
    item a person rewrites becomes their own."""
    texts = clean_direction_lines(texts)
    existing = {i.text: i for i in issue.direction_items.all()}
    used = {i.ref for i in existing.values()}
    next_number = max([int(r[1:]) for r in used if r[1:].isdigit()] + [0]) + 1
    keep = []
    for order, text in enumerate(texts):
        item = existing.get(text)
        if item is None:
            item = DirectionItem(issue=issue, ref=f"D{next_number}", text=text, created_by=user)
            next_number += 1
        item.order = order
        item.save()
        keep.append(item.pk)
    issue.direction_items.exclude(pk__in=keep).delete()


class AgentUnavailable(Exception):
    pass


def _call_agent(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        settings.PRECHECK_AGENT_URL.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "X-Precheck-Token": settings.PRECHECK_SERVICE_TOKEN},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310 - fixed, configured URL
            return json.loads(response.read() or b"{}")
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise AgentUnavailable(str(exc)) from exc


def start_run(issue, user, kind: str = AIPrecheck.Kind.PRECHECK) -> AIPrecheck:
    """Create the run and ask the agent to start. Returns at once; results arrive as events.
    kind "draft" only drafts the Direction Note; it does not verify anything."""
    run = AIPrecheck.objects.create(run_id=uuid.uuid4().hex, issue=issue, requested_by=user, kind=kind)
    try:
        body = {"job_id": str(issue.id), "run_id": run.run_id}
        if kind == AIPrecheck.Kind.DRAFT:
            body["mode"] = "draft"
        elif kind == AIPrecheck.Kind.REVIEW:
            body["mode"] = "review"
        _call_agent("/precheck/runs", body)
    except AgentUnavailable:
        run.status = AIPrecheck.Status.FAILED
        run.failure_reason = "The pre-check service is not reachable right now. Nothing was checked. Please try again shortly."
        run.finished_at = timezone.now()
        run.save()
    _announce(run)
    return run


def _announce(run: AIPrecheck) -> None:
    """The existing event mechanism: a live change notice, so every open job card refreshes."""
    _announce_issue(run.issue)


def _announce_issue(issue) -> None:
    notify("precheck", project=issue.project.key, key=issue.key)


MAX_QUESTIONS_SHOWN = 30


def question_dict(q) -> dict:
    return {"id": q.question_id, "question": q.question, "status": q.status, "answer": q.answer, "answer_status": q.answer_status,
            "sources": q.sources, "flags": q.flags, "failure_reason": q.failure_reason,
            "asked_by": q.asked_by.display_name if q.asked_by else "", "created_at": q.created_at, "answered_at": q.answered_at}


def ask_question(issue, user, question: str):
    """A question about the task: saved, then answered by the agent in the background from the
    knowledge store. The last few questions and answers go with it, so a follow-up makes sense."""
    from .models import AssistantQuestion

    earlier = list(issue.assistant_questions.filter(status="answered").order_by("-created_at")[:4])[::-1]
    q = AssistantQuestion.objects.create(question_id=uuid.uuid4().hex, issue=issue, asked_by=user, question=question[:2000])
    try:
        _call_agent("/precheck/ask", {"job_id": str(issue.id), "question_id": q.question_id, "question": q.question,
                                      "history": [{"question": e.question, "answer": e.answer} for e in earlier]})
    except AgentUnavailable:
        q.status, q.failure_reason, q.answered_at = "failed", "The AI service is not reachable right now. Please ask again shortly.", timezone.now()
        q.save()
    _announce_issue(issue)
    return q


def _record_answer(event: dict) -> bool:
    from .models import AssistantQuestion

    q = AssistantQuestion.objects.select_for_update().select_related("issue__project").filter(question_id=event.get("run_id")).first()
    if q is None or q.status != "pending":
        return False
    if event.get("type") == "ai_assistant.answered":
        r = event.get("result") or {}
        q.status, q.answer, q.answer_status = "answered", str(r.get("answer", ""))[:5000], str(r.get("status", ""))[:12]
        q.sources, q.flags, q.cost_usd = r.get("sources") or [], r.get("flags") or [], float(r.get("cost_usd") or 0)
    else:
        q.status, q.failure_reason = "failed", str(event.get("reason", ""))[:500] or "The AI could not answer."
    q.answered_at = timezone.now()
    q.save()
    _announce_issue(q.issue)
    return True


@transaction.atomic
def record_event(event: dict) -> bool:
    """An event from the agent. A finished run is never changed again: late or repeated events
    for it are ignored."""
    if str(event.get("type", "")).startswith("ai_assistant."):
        return _record_answer(event)
    if str(event.get("type", "")).startswith("ai_learning."):
        return _record_rule(event)
    run = AIPrecheck.objects.select_for_update().select_related("issue__project").filter(run_id=event.get("run_id")).first()
    if run is None or run.status != AIPrecheck.Status.RUNNING:
        return False
    kind = event.get("type")
    if kind == "ai_precheck.progress":
        run.progress = (run.progress + [{k: event.get(k) for k in ("stage", "state", "label", "counts")}])[-MAX_PROGRESS_EVENTS:]
        run.save(update_fields=["progress"])
    elif kind == "ai_precheck.failed":
        run.status = AIPrecheck.Status.FAILED
        run.failure_reason = str(event.get("reason", ""))[:500] or "The pre-check stopped."
        run.finished_at = timezone.now()
        run.save()
    elif kind == "ai_precheck.directions_drafted":
        _store_draft(run, event)
    elif kind == "ai_precheck.completed":
        _store_result(run, event["result"])
        if run.kind == AIPrecheck.Kind.REVIEW:
            review_record.store_round(run, event["result"].get("review") or {})
    else:
        return False
    _announce(run)
    return True


def _store_draft(run: AIPrecheck, event: dict) -> None:
    """Direction Note items the AI drafted. They are added to the job, marked as AI-drafted with
    their reason; an item already on the job (same ref or same text) is left alone."""
    issue = run.issue
    existing = list(issue.direction_items.all())
    refs, texts = {i.ref for i in existing}, {i.text.lower() for i in existing}
    order = max([i.order for i in existing] + [-1]) + 1
    for item in event.get("items", []):
        text = " ".join(str(item.get("text", "")).split())[:500]
        ref = str(item.get("id", ""))[:10]
        if not text or not ref or ref in refs or text.lower() in texts:
            continue
        DirectionItem.objects.create(
            issue=issue, ref=ref, text=text, order=order, origin=DirectionItem.Origin.AI,
            reason=str(item.get("reason", ""))[:300], basis=str(item.get("basis", ""))[:20],
        )
        refs.add(ref)
        texts.add(text.lower())
        order += 1
    versions = event.get("versions") or {}
    for call in event.get("usage", []):
        if run.kind != AIPrecheck.Kind.DRAFT:
            break  # in a full run the completed event carries every call, including this one
        ModelRun.objects.create(
            precheck=run, node=call["node"], task_id=call.get("task_id", ""), model=call["model"], calls=call["calls"],
            input_tokens=call["input"], output_tokens=call["output"], cache_write_tokens=call["cache_write"],
            cache_read_tokens=call["cache_read"], prompt_version=versions.get("prompt", ""), skill_versions=versions.get("skills", {}),
        )
    if event.get("final"):
        run.status = AIPrecheck.Status.COMPLETE
        run.finished_at = timezone.now()
        run.save()


def _store_result(run: AIPrecheck, result: dict) -> None:
    run.status = AIPrecheck.Status.PARTIAL if result["status"] == "partial" else AIPrecheck.Status.COMPLETE
    run.verdict = result["verdict"]
    run.summary = result["summary"][:400]
    run.coverage_addressed = result["coverage"]["addressed"]
    run.coverage_total = result["coverage"]["total"]
    run.counts = result["counts"]
    run.direction_items = result["direction_items"]
    run.trail = result["trail"]
    run.skipped = result["skipped"]
    run.analysis = result.get("analysis") or {}
    run.precheck_type = result.get("precheck_type") or "auto"
    run.readiness = (result.get("readiness") or "")[:40]
    run.requests = result.get("requests") or []
    run.precheck = result.get("precheck") or {}
    usage = result["usage"]
    run.usage = {k: usage[k] for k in ("totals", "model_calls", "reader_calls", "cost_usd", "cache_share", "reused_answers", "budget")}
    run.models_used = result["models"]
    run.versions = result["versions"]
    run.knowledge_ids = result["knowledge_ids"]
    run.demo = bool(result.get("demo"))
    run.duration_s = result.get("duration_s")
    run.finished_at = timezone.now()
    run.save()

    evidence = {
        e["id"]: AIEvidence.objects.create(
            precheck=run, evidence_id=e["id"], file_id=e["file_id"], file_name=e["file_name"][:400],
            location=e["location"][:300], quote=e["quote"], drive_url=e["drive_url"][:1000],
        )
        for e in result["evidence"]
    }
    for order, f in enumerate(result["findings"]):
        finding = AIFinding.objects.create(
            precheck=run, finding_id=f["id"], order=order, direction_ref=f["direction_ref"], area=f["area"][:200],
            status=f["status"], severity=f["severity"], kind=f["kind"], title=f["title"][:300], why=f["why"][:500],
            source=f["source"], confidence=f["confidence"],
        )
        finding.evidence.set([evidence[e] for e in f["evidence_ids"] if e in evidence])
    for call in usage["calls"]:
        ModelRun.objects.create(
            precheck=run, node=call["node"], task_id=call.get("task_id", ""), model=call["model"], calls=call["calls"],
            input_tokens=call["input"], output_tokens=call["output"], cache_write_tokens=call["cache_write"],
            cache_read_tokens=call["cache_read"], prompt_version=result["versions"]["prompt"],
            skill_versions=result["versions"]["skills"], knowledge_ids=result["knowledge_ids"],
        )


def current_disposition(finding) -> dict | None:
    rows = list(finding.feedback.all())
    if not rows or rows[-1].disposition == AIFeedback.Disposition.CLEARED:
        return None
    last = rows[-1]
    return {"disposition": last.disposition, "by": last.user.display_name if last.user else "", "at": last.created_at}


def serialize_run(run: AIPrecheck, full: bool = True) -> dict:
    head = {
        "run_id": run.run_id,
        "kind": run.kind,
        "status": run.status,
        "verdict": run.verdict,
        "summary": run.summary,
        "coverage": {"addressed": run.coverage_addressed, "total": run.coverage_total},
        "counts": run.counts,
        "created_at": run.created_at,
        "finished_at": run.finished_at,
        "requested_by": run.requested_by.display_name if run.requested_by else "",
        "demo": run.demo,
    }
    if not full:
        return head
    findings = []
    for f in run.findings.all():
        findings.append({
            "id": f.id, "finding_id": f.finding_id, "direction_ref": f.direction_ref, "area": f.area, "status": f.status,
            "severity": f.severity, "kind": f.kind, "title": f.title, "why": f.why, "source": f.source, "confidence": f.confidence,
            "evidence": [
                {"id": e.evidence_id, "file_name": e.file_name, "location": e.location, "quote": e.quote, "drive_url": e.drive_url}
                for e in f.evidence.all()
            ],
            "disposition": current_disposition(f),
        })
    return {
        **head,
        "direction_items": run.direction_items,
        "trail": run.trail,
        "progress": run.progress,
        "skipped": run.skipped,
        "analysis": run.analysis,
        "precheck_type": run.precheck_type,
        "readiness": run.readiness,
        "requests": run.requests,
        "precheck": run.precheck,
        "failure_reason": run.failure_reason,
        "usage": run.usage,
        "models": run.models_used,
        "duration_s": run.duration_s,
        "findings": findings,
    }


LESSON_SCOPES = ("client", "project", "team", "firm")


def teach(issue, user, *, kind: str, item: str, note: str, scope: str = "client", source: str = "precheck", finding=None, run=None):
    """A correction becomes a lesson: active at once for this client; for the project, the team or
    the firm it waits for a lead or an admin (unless one is teaching it). The AI then drafts it as
    a rule in the background; until then the note itself applies."""
    from .models import PrecheckLesson

    scope = scope if scope in LESSON_SCOPES else "client"
    approver = can_approve_lessons(user, issue)
    wide = scope != "client"
    latest = run or issue.prechecks.filter(status__in=["complete", "partial"]).order_by("-created_at").first()
    lesson = PrecheckLesson.objects.create(
        client_scope=client_scope(issue), project_scope=f"project-{issue.project_id}", team_scope=team_scope(issue),
        scope=scope, status="active" if (not wide or approver) else "pending", kind=kind, item=item[:300], note=note[:1000],
        precheck_type=(latest.precheck_type if latest else "") or "", issue=issue, run=latest, created_by=user, source=source,
        finding=finding, decided_by=user if wide and approver else None, decided_at=timezone.now() if wide and approver else None,
    )
    draft_rule(lesson)
    return lesson


def draft_rule(lesson) -> None:
    """Ask the agent to draft the lesson as a rule (when / do / why). Best-effort: if the agent is
    not reachable, the lesson's own note applies and the rule can be drafted later."""
    finding = lesson.finding
    body = {"lesson_id": lesson.id, "job_id": str(lesson.issue_id), "kind": lesson.kind, "item": lesson.item, "note": lesson.note,
            "source": lesson.source, "scope": lesson.scope, "nature": lesson.precheck_type,
            "context": {"fs_line": finding.fs_line, "issue": finding.text, "why": finding.why} if finding else {}}
    try:
        _call_agent("/precheck/learn", body)
        lesson.drafting = "drafting"
    except AgentUnavailable:
        lesson.drafting = "failed"
    lesson.save(update_fields=["drafting"])


def _record_rule(event: dict) -> bool:
    from .models import PrecheckLesson

    lesson_id = str(event.get("run_id", "")).removeprefix("lesson-")
    lesson = PrecheckLesson.objects.select_for_update().filter(pk=int(lesson_id) if lesson_id.isdigit() else 0).first()
    if lesson is None or lesson.drafting != "drafting":
        return False
    rule = event.get("result") or {}
    if event.get("type") == "ai_learning.drafted" and rule.get("do"):
        lesson.rule_title, lesson.rule_when = str(rule.get("title", ""))[:200], str(rule.get("when", ""))[:600]
        lesson.rule_do, lesson.rule_why, lesson.drafting = str(rule["do"])[:800], str(rule.get("why", ""))[:600], "drafted"
    else:
        lesson.drafting = "failed"
    lesson.save()
    return True

