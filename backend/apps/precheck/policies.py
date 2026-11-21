"""Pre-check policies (AFIT, 20 Nov 2026): the accountants' written standards for what a pre-check asks
for, for one client (a sub-workspace), one client group (the task's group), one location (set on the
task's pre-check settings) or every task. The agent is sent the policies that apply to a task and checks
every point of its pre-check against them; feedback on a policy has the AI revise it.

Also here: freeing a task's memory in the agent three days after its final review.
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import AIPrecheck, JobFolder, PolicyFeedback, PrecheckPolicy

MAX_POLICIES = 60  # sent with one task
FLUSH_AFTER = timedelta(days=3)


def _norm(value: str) -> str:
    return " ".join(str(value or "").split())


def task_location(issue) -> str:
    folder = getattr(issue, "drive_folder", None)
    return _norm((folder.accountant_settings or {}).get("location", "")) if folder else ""


def scope_label(policy: PrecheckPolicy) -> str:
    if policy.scope == PrecheckPolicy.Scope.CLIENT:
        return f"Client: {policy.client.name if policy.client_id else 'removed'}"
    if policy.scope == PrecheckPolicy.Scope.GROUP:
        return f"Group: {policy.group}"
    if policy.scope == PrecheckPolicy.Scope.LOCATION:
        return f"Location: {policy.location}"
    return "Every task"


def policy_dict(policy: PrecheckPolicy, with_feedback: bool = False) -> dict:
    from .services import PRECHECK_TYPES

    out = {
        "id": policy.id, "scope": policy.scope, "scope_label": scope_label(policy),
        "client": {"id": policy.client_id, "name": policy.client.name} if policy.client_id else None,
        "group": policy.group, "location": policy.location,
        "precheck_type": policy.precheck_type, "precheck_type_label": dict(PRECHECK_TYPES).get(policy.precheck_type, "Every type of check"),
        "title": policy.title, "text": policy.text, "active": policy.active, "version": policy.version, "history": policy.history,
        "created_by": policy.created_by.display_name if policy.created_by_id else "", "created_at": policy.created_at,
        "updated_by": policy.updated_by.display_name if policy.updated_by_id else "", "updated_at": policy.updated_at,
    }
    if with_feedback:
        out["feedback"] = [feedback_dict(f) for f in policy.feedback.select_related("created_by", "issue")[:20]]
    return out


def feedback_dict(f: PolicyFeedback) -> dict:
    return {"id": f.id, "text": f.text, "context": f.context, "status": f.status, "summary": f.summary,
            "task": f.issue.key if f.issue_id else "", "by": f.created_by.display_name if f.created_by_id else "", "created_at": f.created_at}


def policies_for(issue) -> list[dict]:
    """The active policies that apply to this task: its client's, its group's, its location's and every
    task's, for its type of check (or every type)."""
    from .services import setup_for

    project = issue.project
    group, location = _norm(issue.group), task_location(issue)
    nature = setup_for(issue)["precheck_type"]
    applies = Q(scope=PrecheckPolicy.Scope.ALL)
    if project.client_id:
        applies |= Q(scope=PrecheckPolicy.Scope.CLIENT, client_id=project.client_id)
    if group:
        applies |= Q(scope=PrecheckPolicy.Scope.GROUP, group__iexact=group)
    if location:
        applies |= Q(scope=PrecheckPolicy.Scope.LOCATION, location__iexact=location)
    fits = Q(precheck_type="")
    if nature and nature != "auto":
        fits |= Q(precheck_type=nature)
    else:
        fits = Q()  # the AI decides the type: every policy, each saying which type it is for
    qs = PrecheckPolicy.objects.filter(applies, fits, active=True).select_related("client", "created_by", "updated_by")
    order = {"client": 0, "group": 1, "location": 2, "all": 3}  # the narrowest first
    rows = sorted(qs[:MAX_POLICIES * 2], key=lambda p: (order[p.scope], p.title.lower()))[:MAX_POLICIES]
    out = []
    for p in rows:
        d = {k: v for k, v in policy_dict(p).items() if k in ("id", "scope", "scope_label", "title", "text", "precheck_type")}
        if p.precheck_type:
            d["text"] = f"(For {policy_dict(p)['precheck_type_label']} checks.) {d['text']}"
        out.append(d)
    return out


def options() -> dict:
    """What a policy can be set for: the clients, the groups tasks have, the locations already used."""
    from apps.clients.models import Client
    from apps.issues.models import Issue

    from .services import PRECHECK_TYPES

    groups = sorted({_norm(g) for g in Issue.objects.exclude(group="").values_list("group", flat=True)[:5000] if _norm(g)}, key=str.lower)
    locations = {_norm(s.get("location", "")) for s in JobFolder.objects.values_list("accountant_settings", flat=True) if isinstance(s, dict)}
    locations |= set(PrecheckPolicy.objects.exclude(location="").values_list("location", flat=True))
    return {
        "scopes": [{"value": v, "label": label} for v, label in PrecheckPolicy.Scope.choices],
        "clients": [{"id": c.id, "name": c.name} for c in Client.objects.order_by("name")],
        "groups": groups[:500],
        "locations": sorted((x for x in locations if x), key=str.lower),
        "precheck_types": [{"value": v, "label": label} for v, label in PRECHECK_TYPES if v != "auto"],
    }


def clean_input(data: dict, current: PrecheckPolicy | None = None) -> tuple[dict, dict]:
    """(fields, errors) from a create or edit request."""
    from apps.clients.models import Client

    from .services import PRECHECK_TYPES

    out, errors = {}, {}
    scope = data.get("scope", current.scope if current else "")
    if scope not in PrecheckPolicy.Scope.values:
        errors["scope"] = ["Choose who the policy is for: a client, a group, a location or every task."]
    out["scope"] = scope
    out["client"], out["group"], out["location"] = None, "", ""
    if scope == PrecheckPolicy.Scope.CLIENT:
        cid = data.get("client_id", current.client_id if current else None)
        client = Client.objects.filter(pk=cid).first() if str(cid or "").isdigit() else None
        if client is None:
            errors["client_id"] = ["Choose the client."]
        out["client"] = client
    elif scope == PrecheckPolicy.Scope.GROUP:
        out["group"] = _norm(data.get("group", current.group if current else ""))[:100]
        if not out["group"]:
            errors["group"] = ["Name the group."]
    elif scope == PrecheckPolicy.Scope.LOCATION:
        out["location"] = _norm(data.get("location", current.location if current else ""))[:100]
        if not out["location"]:
            errors["location"] = ["Name the location."]
    nature = str(data.get("precheck_type", current.precheck_type if current else "") or "")
    if nature not in ("", *(v for v, _ in PRECHECK_TYPES if v != "auto")):
        errors["precheck_type"] = ["Choose a type of check, or every type."]
    out["precheck_type"] = nature
    out["title"] = _norm(data.get("title", current.title if current else ""))[:150]
    out["text"] = str(data.get("text", current.text if current else "") or "").strip()[:2000]
    if not out["title"]:
        errors["title"] = ["Give the policy a short title."]
    if not out["text"]:
        errors["text"] = ["Write what the pre-check should do."]
    if "active" in data:
        out["active"] = bool(data["active"])
    return out, errors


def save_wording(policy: PrecheckPolicy, *, title: str, text: str, by, why: str) -> bool:
    """A new wording, keeping the old one in the history. False when nothing changed."""
    if title == policy.title and text == policy.text:
        return False
    policy.history = [*policy.history, {"version": policy.version, "title": policy.title, "text": policy.text,
                                        "changed_by": by.display_name if by else "AI", "changed_at": timezone.now().isoformat(), "why": why}][-30:]
    policy.title, policy.text, policy.version = title, text, policy.version + 1
    return True


def give_feedback(policy: PrecheckPolicy, user, text: str, *, issue=None, context: str = "") -> PolicyFeedback:
    """Feedback on a policy: the AI revises the policy from it (best-effort when the agent is away)."""
    from .services import AgentUnavailable, _call_agent

    fb = PolicyFeedback.objects.create(policy=policy, issue=issue, text=text[:1000], context=context[:1000], created_by=user)
    body = {"feedback_id": fb.id, "policy_id": policy.id, "job_id": str(issue.id) if issue else "", "title": policy.title, "text": policy.text,
            "scope_label": scope_label(policy), "feedback": fb.text, "context": fb.context}
    try:
        _call_agent("/precheck/policies/revise", body)
    except AgentUnavailable:
        fb.status, fb.summary = PolicyFeedback.Status.FAILED, "The AI could not be reached. The policy was not changed; edit it yourself or try again."
        fb.save(update_fields=["status", "summary"])
    return fb


def record_revision(event: dict) -> bool:
    """The AI's revision of a policy, from the agent: applied at once, the old wording kept."""
    fid = str(event.get("run_id", "")).removeprefix("policy-")
    fb = PolicyFeedback.objects.select_for_update().select_related("policy").filter(pk=int(fid) if fid.isdigit() else 0).first()
    if fb is None or fb.status != PolicyFeedback.Status.REVISING:
        return False
    result = event.get("result") or {}
    if event.get("type") == "ai_policy.revised" and str(result.get("text", "")).strip():
        policy = fb.policy
        changed = save_wording(policy, title=_norm(result.get("title") or policy.title)[:150], text=str(result["text"]).strip()[:2000], by=None,
                               why=f"Revised by the AI from {fb.created_by.display_name if fb.created_by_id else 'a'}'s feedback: {fb.text[:200]}")
        if changed:
            policy.updated_by = fb.created_by
            policy.save()
        fb.status = PolicyFeedback.Status.REVISED
        fb.summary = str(result.get("summary", ""))[:500] or ("Revised." if changed else "The policy was left as it was.")
    else:
        fb.status = PolicyFeedback.Status.FAILED
        fb.summary = str(event.get("reason", ""))[:500] or "The policy could not be revised."
    fb.save(update_fields=["status", "summary"])
    return True


# --- freeing a task's memory after its final review -------------------------------------------------

def final_review_at(issue):
    """When the task reached its final review: its review was completed by a person, or it was moved to a
    done stage. None while it is still being worked on."""
    times = []
    session = getattr(issue, "review_session", None)
    if session is not None and session.status == "complete" and session.completed_at:
        times.append(session.completed_at)
    if issue.status.category == "done" and issue.resolved_at:
        times.append(issue.resolved_at)
    return min(times) if times else None


def due_for_flush(now=None) -> list[JobFolder]:
    """Tasks whose final review was at least three days ago (and with no run since then for three days),
    whose memory the agent still holds."""
    now = now or timezone.now()
    cutoff = now - FLUSH_AFTER
    candidates = (JobFolder.objects.select_related("issue__status", "issue__project", "issue__review_session")
                  .filter(Q(issue__review_session__status="complete", issue__review_session__completed_at__lte=cutoff)
                          | Q(issue__status__category="done", issue__resolved_at__lte=cutoff)))
    due = []
    for folder in candidates:
        final = final_review_at(folder.issue)
        if final is None or final > cutoff:
            continue
        last_run = AIPrecheck.objects.filter(issue=folder.issue).order_by("-created_at").values_list("created_at", flat=True).first()
        if last_run is None or last_run > cutoff:
            continue  # nothing in memory yet, or used again lately: wait
        if folder.memory_flushed_at and folder.memory_flushed_at >= last_run:
            continue  # freed already, and not run since
        due.append(folder)
    return due


def flush_due(now=None) -> dict:
    """Ask the agent to free the memory of every task that is due. Returns {"flushed", "failed"}."""
    from .services import AgentRefused, AgentUnavailable, _call_agent, client_scope

    flushed = failed = 0
    for folder in due_for_flush(now):
        try:
            _call_agent("/precheck/jobs/flush", {"job_id": str(folder.issue_id), "client_id": client_scope(folder.issue)}, timeout=120)
        except (AgentUnavailable, AgentRefused):
            failed += 1  # tried again on the next run of the command
            continue
        with transaction.atomic():
            JobFolder.objects.filter(pk=folder.pk).update(memory_flushed_at=timezone.now())
        flushed += 1
    return {"flushed": flushed, "failed": failed}
