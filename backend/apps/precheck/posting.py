"""Results posted on the task: when the AI's pre-check, guide or review finishes, a summary is added
to the task's comments and the stage is stamped on the task's milestones. Posted by the system on
behalf of the person who ran it; no notification is sent (the person is watching the run)."""
from django.utils import timezone

from apps.issues.models import Comment

from .models import AIPrecheck, TaskMilestone

MAX_LINES = 25
TITLES = {AIPrecheck.Kind.PRECHECK: "AI pre-check", AIPrecheck.Kind.GUIDE: "AI preparation guide",
          AIPrecheck.Kind.REVIEW: "AI review"}


def _text(text: str, bold: bool = False) -> dict:
    node = {"type": "text", "text": text}
    return {**node, "marks": [{"type": "bold"}]} if bold else node


def _para(*parts: dict) -> dict:
    return {"type": "paragraph", "content": [p for p in parts if p.get("text")]}


def _bullets(lines: list[str]) -> dict:
    return {"type": "bulletList", "content": [{"type": "listItem", "content": [_para(_text(line))]} for line in lines]}


def _lines(run: AIPrecheck) -> tuple[str, list[tuple[str, list[str]]]]:
    """(the headline, [(section, lines)]) of a finished run."""
    if run.kind == AIPrecheck.Kind.PRECHECK:
        p = run.precheck or {}
        decision = p.get("decision") or {}
        sections = [("Information required from the client",
                     [f"{r.get('group', '')}: {r.get('item', '')}" + (" (blocks preparation)" if r.get("priority") == "blocking" else "")
                      for r in p.get("requests") or []]),
                    ("Questions for the accountant", [f"{q.get('item', '')}" for q in p.get("accountant_questions") or []])]
        return f"{decision.get('label', run.readiness)} — {decision.get('reason', run.summary)}", sections
    if run.kind == AIPrecheck.Kind.GUIDE:
        g = run.guide or {}
        steps = [f"{s.get('area', '')}: {s.get('step', '')}" + (" (waits on the client)" if s.get("waits_on_client") else "")
                 for s in g.get("steps") or []]
        return (g.get("summary") or (g.get("decision") or {}).get("reason", "")), [("Steps", steps)]
    r = run.review or {}
    findings = [f"{f.get('ref', '')} [{f.get('severity', '')}] {f.get('fs_line', '')}: {f.get('issue', '')}".strip() for f in r.get("findings") or []]
    resolved = [f"{x.get('ref', '')}: {x.get('reason', '')}" for x in r.get("resolved") or []]
    return (r.get("summary") or (r.get("decision") or {}).get("reason", "")), [("Open findings", findings), ("Resolved", resolved)]


def post_result(run: AIPrecheck) -> None:
    """Add the run's summary to the task's comments and stamp its milestone. Only for a finished
    pre-check, guide or review with someone to post on behalf of; never twice for one run."""
    if run.kind not in TITLES or run.status not in (AIPrecheck.Status.COMPLETE, AIPrecheck.Status.PARTIAL):
        return
    if TaskMilestone.objects.filter(run=run).exists():
        return
    TaskMilestone.objects.create(issue=run.issue, kind=run.kind, on=timezone.localdate(), auto=True, run=run, by=run.requested_by)
    if run.requested_by is None:
        return
    headline, sections = _lines(run)
    content = [_para(_text(f"{TITLES[run.kind]} — posted automatically on {timezone.localtime():%d %b %Y, %H:%M}", bold=True)),
               _para(_text(headline or "Finished."))]
    for title, lines in sections:
        if not lines:
            continue
        shown = lines[:MAX_LINES]
        content.append(_para(_text(f"{title} ({len(lines)})", bold=True)))
        content.append(_bullets(shown))
        if len(lines) > len(shown):
            content.append(_para(_text(f"... and {len(lines) - len(shown)} more: open the AI assistant on this task for the full list.")))
    Comment.objects.create(issue=run.issue, author=run.requested_by, body={"type": "doc", "content": content})


def milestone_dict(m: TaskMilestone) -> dict:
    return {"id": m.id, "kind": m.kind, "label": m.get_kind_display(), "on": m.on, "note": m.note, "auto": m.auto,
            "by": m.by.display_name if m.by else "", "created_at": m.created_at}
