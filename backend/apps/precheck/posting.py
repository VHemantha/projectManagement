"""Results posted on the task: when the AI's pre-check, guide, review or WP Agent reconciliation
finishes, a summary is added to the task's comments and the stage is stamped on the task's milestones.
Posted by the system on behalf of the person who ran it; no notification is sent (the person is
watching the run).

Each posted result carries the stage it belongs to (AFIT, 12 Nov 2026), so the task view's milestone
bar shows it in that stage's history: the pre-check under Pre-check, the guide and the WP Agent's
workpapers under Preparation, the review under Internal review."""
from django.utils import timezone

from apps.issues.models import Comment

from .models import AIPrecheck, TaskMilestone

MAX_LINES = 25
TITLES = {AIPrecheck.Kind.PRECHECK: "AI pre-check", AIPrecheck.Kind.GUIDE: "AI preparation guide",
          AIPrecheck.Kind.REVIEW: "AI review", AIPrecheck.Kind.GST: "WP Agent: GST reconciliation",
          AIPrecheck.Kind.WAGES: "WP Agent: wages (PAYE) reconciliation",
          AIPrecheck.Kind.ICA: "WP Agent: imputation (ICA) reconciliation"}
# The stage of the task each kind of result belongs to (Comment.Stage values).
STAGES = {AIPrecheck.Kind.PRECHECK: "precheck", AIPrecheck.Kind.GUIDE: "preparation", AIPrecheck.Kind.REVIEW: "internal_review",
          AIPrecheck.Kind.GST: "preparation", AIPrecheck.Kind.WAGES: "preparation", AIPrecheck.Kind.ICA: "preparation"}
# Milestones are kept for the pre-check, the guide and the review (the WP Agent has none of its own).
MILESTONE_KINDS = (AIPrecheck.Kind.PRECHECK, AIPrecheck.Kind.GUIDE, AIPrecheck.Kind.REVIEW)


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
        if g.get("format") == 2:
            return (g.get("decision") or {}).get("reason", ""), _guide_sections(g)
        steps = [f"{s.get('area', '')}: {s.get('step', '')}" + (" (waits on the client)" if s.get("waits_on_client") else "")
                 for s in g.get("steps") or []]
        return (g.get("summary") or (g.get("decision") or {}).get("reason", "")), [("Steps", steps)]
    if run.kind in AIPrecheck.WP_KINDS:
        return _wp_lines(run.gst or {})
    r = run.review or {}
    findings = [f"{f.get('ref', '')} [{f.get('severity', '')}] {f.get('fs_line', '')}: {f.get('issue', '')}".strip() for f in r.get("findings") or []]
    resolved = [f"{x.get('ref', '')}: {x.get('reason', '')}" for x in r.get("resolved") or []]
    return (r.get("summary") or (r.get("decision") or {}).get("reason", "")), [("Open findings", findings), ("Resolved", resolved)]


def _wp_lines(w: dict) -> tuple[str, list[tuple[str, list[str]]]]:
    """A WP Agent reconciliation: its status and summary, what still needs evidence, the proposed
    corrections and (wages, ICA) each conclusion."""
    exceptions = [f"[{e.get('severity', '')}] {e.get('text', '')}" + (f" Next: {e['next_evidence']}" if e.get("next_evidence") else "")
                  for e in w.get("exceptions") or []]
    corrections = [f"{c.get('title', '')}" + (f" ({c['status']})" if c.get("status") else "") for c in w.get("corrections") or []]
    conclusions = [f"{c.get('label', '')}: {c.get('status', '')}" for c in w.get("conclusions") or []]
    headline = _join(f"{w['status']} —" if w.get("status") else "", w.get("summary", ""))
    return headline, [("Conclusions", conclusions), ("Exceptions", exceptions), ("Proposed corrections", corrections)]


def _join(*parts: str) -> str:
    return " ".join(p for p in parts if p)


def _ev(item: dict) -> str:
    return f" [{', '.join(item['events'])}]" if item.get("events") else ""


def _guide_sections(g: dict) -> list[tuple[str, list[str]]]:
    """The preparation guide's eight sections (AFIT's agreed structure, 21 Oct 2026). An event is
    referred to by its id (E1, E2, ...) wherever it is followed through."""
    snap = g.get("snapshot") or {}
    snapshot = [f"{label}: {snap[k]}" for k, label in (("activities", "Business"), ("assets_and_funding", "Assets and funding"),
                ("records", "Records available"), ("bookkeeping", "Bookkeeping"), ("period", "FS preparation period")) if snap.get(k)]
    events = [_join(f"{e.get('id', '')} [{'Confirmed' if e.get('status') == 'confirmed' else 'Suspected — to confirm'}]",
                    f"{e.get('event', '')} → {e.get('why_it_matters', '')} → {e.get('action', '')}",
                    f"Effect: {e['effect']}" if e.get("effect") else "") for e in g.get("events") or []]
    prior = [_join(f"{p.get('item', '')} —", p.get("follow_through", "")) for p in g.get("prior_year") or []]
    risks = [_join(f"{r.get('area', '')}: {r.get('what_could_be_wrong', '')}", f"Examine: {r.get('examine', '')}",
                   f"Evidence: {r.get('evidence', '')}") + _ev(r) for r in g.get("risks") or []]
    sequence = [_join(f"{n}. {s.get('step', '')}", "" if s.get("can_start_now") else f"(waits on: {s.get('depends_on', '')})",
                      f"Escalate: {s['escalate']}" if s.get("escalate") else "") + _ev(s) for n, s in enumerate(g.get("sequence") or [], start=1)]
    judgments = [_join(j.get("judgment", ""), f"Evidence: {j.get('evidence', '')}", f"Reference: {j['reference']}" if j.get("reference") else "",
                       "(manager approval)" if j.get("manager_approval") else "") + _ev(j) for j in g.get("judgments") or []]
    q = g.get("queries") or {}
    checklist = [f"[{ {'done': 'Done', 'na': 'N/A'}.get(c.get('status'), 'Open') }] {c.get('check', '')}" + _ev(c) for c in g.get("checklist") or []]
    roll = [_join(r.get("item", ""), f"— {r['why']}" if r.get("why") else "") for r in g.get("roll_forward") or []]
    return [("1. Job snapshot", snapshot), ("2. Significant events and possible risk areas", events), ("3. Prior-year findings and continuity", prior),
            ("4. Priority risks", risks), ("5. Starting sequence", sequence), ("6. Judgments, assumptions and references", judgments),
            ("7. Queries to be asked — for the manager", [x.get("question", "") + _ev(x) for x in q.get("manager") or []]),
            ("7. Queries to be asked — for the client", [x.get("question", "") + _ev(x) for x in q.get("client") or []]),
            ("7. Queries to be asked — outstanding requests", [x.get("item", "") + _ev(x) for x in q.get("outstanding") or []]),
            ("8. Completion and handover checklist", checklist), ("8. To roll forward to next year", roll)]


def result_comment(run: AIPrecheck) -> dict:
    """The run's result as a comment body (rich-text JSON)."""
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
    return {"type": "doc", "content": content}


def post_result(run: AIPrecheck) -> None:
    """Add the run's summary to the task's comments, under its stage, and stamp its milestone. Only
    for a finished run with someone to post on behalf of; never twice for one run."""
    if run.kind not in TITLES or run.status not in (AIPrecheck.Status.COMPLETE, AIPrecheck.Status.PARTIAL):
        return
    if run.kind in MILESTONE_KINDS:
        if TaskMilestone.objects.filter(run=run).exists():
            return
        TaskMilestone.objects.create(issue=run.issue, kind=run.kind, on=timezone.localdate(), auto=True, run=run, by=run.requested_by)
    if run.requested_by is None:
        return
    Comment.objects.create(issue=run.issue, author=run.requested_by, body=result_comment(run), stage=STAGES[run.kind])


def milestone_dict(m: TaskMilestone) -> dict:
    return {"id": m.id, "kind": m.kind, "label": m.get_kind_display(), "on": m.on, "note": m.note, "auto": m.auto,
            "by": m.by.display_name if m.by else "", "created_at": m.created_at}
