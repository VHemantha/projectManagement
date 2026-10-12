"""The review of a task's draft financial statements, on the PM side: the record of assumptions,
findings and responses, what the agent is told each round, and what it sends back.

The agent reviews; people decide. A finding keeps one ref (R1, R2, ...) across rounds; the
reviewer responds to it (agree, fixed, not an issue, wrong reason) and every response is kept.
Only a person completes the review.
"""
from django.db import transaction
from django.utils import timezone

from .models import AIPrecheck, Assumption, ReviewFinding, ReviewResponse, ReviewSession

NATURES = ("residential_rental", "general", "investment")
NOTE_REQUIRED = {ReviewFinding.Response.NOT_AN_ISSUE, ReviewFinding.Response.WRONG_REASON}


def session_for(issue) -> ReviewSession:
    session, _ = ReviewSession.objects.get_or_create(issue=issue)
    return session


def assumption_dict(a: Assumption) -> dict:
    return {
        "id": a.id, "ref": a.ref, "area": a.area, "area_label": a.get_area_display(), "fs_line": a.fs_line,
        "amount": str(a.amount) if a.amount is not None else "", "judgement": a.judgement, "basis": a.basis, "evidence": a.evidence,
        "status": a.status, "history": a.history, "created_by": a.created_by.display_name if a.created_by else "",
        "updated_by": a.updated_by.display_name if a.updated_by else "", "updated_at": a.updated_at,
    }


def finding_dict(f: ReviewFinding) -> dict:
    return {
        "id": f.id, "ref": f.ref, "origin": f.origin, "area": f.area, "fs_line": f.fs_line, "issue": f.text, "why": f.why,
        "action": f.action, "severity": f.severity, "sources": f.sources, "assumptions": f.assumptions, "flags": f.flags,
        "status": f.status, "resolved_reason": f.resolved_reason, "response": f.response, "note": f.note,
        "responded_by": f.responded_by.display_name if f.responded_by else "", "responded_at": f.responded_at,
        "responses": [{"response": r.response, "note": r.note, "by": r.user.display_name if r.user else "", "at": r.created_at}
                      for r in f.responses.all()],
        "created_by": f.created_by.display_name if f.created_by else "", "created_at": f.created_at,
    }


def payload(issue) -> dict:
    """What the agent is told for a review round: the active assumptions, every finding so far
    with the reviewer's latest response, the round number and the business nature."""
    latest = issue.prechecks.filter(kind=AIPrecheck.Kind.PRECHECK, status__in=["complete", "partial"]).order_by("-created_at").first()
    rounds = issue.prechecks.filter(kind=AIPrecheck.Kind.REVIEW, status__in=["complete", "partial"]).count()
    return {
        "round": rounds + 1,
        "nature": latest.precheck_type if latest and latest.precheck_type in NATURES else "",
        "assumptions": [
            {"ref": a.ref, "area": a.get_area_display(), "fs_line": a.fs_line, "amount": str(a.amount) if a.amount is not None else "",
             "judgement": a.judgement, "basis": a.basis, "evidence": a.evidence}
            for a in issue.assumptions.filter(status="active")
        ],
        "findings": [
            {"ref": f.ref, "status": f.status, "severity": f.severity, "area": f.area, "fs_line": f.fs_line, "issue": f.text,
             "why": f.why, "response": f.response, "note": f.note, "origin": f.origin}
            for f in issue.review_findings.all()
        ],
    }


def _next_ref(issue, model, prefix: str) -> str:
    n = 0
    for ref in model.objects.filter(issue=issue).values_list("ref", flat=True):
        if ref.startswith(prefix) and ref[len(prefix):].isdigit():
            n = max(n, int(ref[len(prefix):]))
    return f"{prefix}{n + 1}"


@transaction.atomic
def store_round(run: AIPrecheck, review: dict) -> None:
    """A finished review round: carry each finding under its ref (new ones get the next R number),
    mark resolved ones, and keep the round's output with the refs filled in."""
    issue = run.issue
    existing = {f.ref: f for f in issue.review_findings.select_for_update()}
    for f in review.get("findings", []):
        fields = {"area": f["area"][:100], "fs_line": f["fs_line"][:200], "text": f["issue"][:1000], "why": f["why"][:1000],
                  "action": f["action"][:500], "severity": f["severity"], "sources": f["sources"], "assumptions": f["assumptions"],
                  "flags": f["flags"], "last_run": run}
        row = existing.get(f["ref"]) if f.get("ref") else None
        if row is not None:
            for k, v in fields.items():
                setattr(row, k, v)
            row.status = ReviewFinding.Status.OPEN  # still wrong, even if someone said it was fixed
            row.resolved_reason = ""
            row.save()
        else:
            row = ReviewFinding.objects.create(issue=issue, ref=_next_ref(issue, ReviewFinding, "R"), first_run=run, **fields)
            existing[row.ref] = row
        f["ref"] = row.ref
        f["id"] = row.id
    for r in review.get("resolved", []):
        row = existing.get(r["ref"])
        if row is not None and row.status == ReviewFinding.Status.OPEN:
            row.status, row.resolved_reason, row.last_run = ReviewFinding.Status.RESOLVED, r["reason"][:500], run
            row.save(update_fields=["status", "resolved_reason", "last_run", "updated_at"])
    run.review = review
    run.save(update_fields=["review"])


def respond(finding: ReviewFinding, response: str, note: str, user) -> ReviewFinding:
    """A person's response to a finding. Not an issue closes it (and the AI will not raise it
    again); fixed waits for the next round to confirm."""
    finding.response, finding.note, finding.responded_by, finding.responded_at = response, note[:1000], user, timezone.now()
    if response == ReviewFinding.Response.NOT_AN_ISSUE:
        finding.status = ReviewFinding.Status.CLOSED
    elif finding.status == ReviewFinding.Status.CLOSED:
        finding.status = ReviewFinding.Status.OPEN  # reopened by a later response
    finding.save()
    ReviewResponse.objects.create(finding=finding, response=response, note=note[:1000], user=user)
    return finding


def add_missed(issue, user, area: str, fs_line: str, text: str, note: str) -> ReviewFinding:
    """Something the AI missed: an open finding raised by a person, reviewed with the rest next round."""
    return ReviewFinding.objects.create(
        issue=issue, ref=_next_ref(issue, ReviewFinding, "R"), origin="person", area=area[:100], fs_line=fs_line[:200],
        text=text[:1000], why=note[:1000], severity="medium", created_by=user,
    )


def save_assumption(issue, user, data: dict, assumption: Assumption | None = None) -> Assumption:
    fields = {k: data[k] for k in ("area", "fs_line", "amount", "judgement", "basis", "evidence", "status") if k in data}
    if assumption is None:
        return Assumption.objects.create(issue=issue, ref=_next_ref(issue, Assumption, "A"), created_by=user, updated_by=user, **fields)
    before = {k: (str(getattr(assumption, k)) if getattr(assumption, k) is not None else "") for k in fields}
    changed = {k: v for k, v in fields.items() if before.get(k) != (str(v) if v is not None else "")}
    if changed:
        assumption.history = assumption.history + [{**before, "by": assumption.updated_by.display_name if assumption.updated_by else "",
                                                    "at": assumption.updated_at.isoformat() if assumption.updated_at else ""}]
        for k, v in changed.items():
            setattr(assumption, k, v)
        assumption.updated_by = user
        assumption.save()
    return assumption


def open_high(issue) -> int:
    return issue.review_findings.filter(status=ReviewFinding.Status.OPEN, severity="high").count()


def state(issue, user) -> dict:
    """What the task card's Review tab shows."""
    from .services import can_approve_lessons, serialize_run

    session = session_for(issue)
    runs = list(issue.prechecks.filter(kind=AIPrecheck.Kind.REVIEW).select_related("requested_by")[:20])
    latest = runs[0] if runs else None
    findings = issue.review_findings.select_related("responded_by", "created_by").prefetch_related("responses__user")
    return {
        "session": {"status": session.status, "completed_by": session.completed_by.display_name if session.completed_by else "",
                    "completed_at": session.completed_at, "note": session.completion_note},
        "assumptions": [assumption_dict(a) for a in issue.assumptions.select_related("created_by", "updated_by")],
        "findings": [finding_dict(f) for f in findings],
        "latest": ({**serialize_run(latest), "review": latest.review} if latest else None),
        "rounds": [{**serialize_run(r, full=False), "decision": (r.review or {}).get("decision")} for r in runs],
        "open_high": open_high(issue),
        "can_complete": issue.reviewer_id == user.id or can_approve_lessons(user, issue),
        "areas": [{"value": v, "label": label} for v, label in Assumption.Area.choices],
        "rounds_done": sum(1 for r in runs if r.status in ("complete", "partial")),
    }
