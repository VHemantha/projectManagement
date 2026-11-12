"""The pre-check's missing-information gaps, on the PM side (12 Nov 2026).

The agent keeps each "not found" as a provisional gap and re-checks it against every document of the
task until it is found or, once the task's folder has settled, confirmed missing (see the agent's
precheck_agent/gaps.py). Here the latest report is kept on the task (JobFolder.gap_report), and what
changed is posted under the task's Pre-check stage, so its history shows it:

    "Found: Applicant annual income — Payslip summary.txt (Annual income: $50,000)"
    "Confirmed missing: ANZ statement for March 2026"

Posted by the TASKO Coordinator (the agent's account), since no person did it.
"""
from django.utils import timezone

STATUS_LABEL = {"RESOLVED": "Found", "PARTIALLY_RESOLVED": "Partly found", "CONFLICTING": "Documents disagree",
                "OPEN": "Not found yet", "CONFIRMED_MISSING": "Confirmed missing"}
MAX_LINES = 25


def _rows(report: dict) -> dict[str, dict]:
    out = {}
    for key in ("resolved", "partially_resolved", "conflicting", "open", "confirmed_missing"):
        for r in report.get(key) or []:
            out[r["gap_id"]] = r
    return out


def changes(before: dict, after: dict) -> list[dict]:
    """Gaps whose status is new or different in `after`, in the report's order."""
    old = _rows(before or {})
    return [r for gid, r in _rows(after or {}).items() if old.get(gid, {}).get("status") != r["status"] and r["status"] != "OPEN"]


def _line(r: dict) -> str:
    label = STATUS_LABEL.get(r["status"], r["status"])
    where = "; ".join(f"{e['doc_name']}" + (f" ({e['quoted_snippet'][:80]})" if e.get("quoted_snippet") and e["quoted_snippet"] != e["doc_name"] else "")
                      for e in (r.get("evidence") or [])[:3])
    extra = f" — still needed: {r['still_needed']}" if r.get("still_needed") else ""
    return f"{label}: {r['item']}" + (f" — {where}" if where else "") + extra


def store(issue, report: dict, *, post: bool = True) -> list[dict]:
    """Keep the latest report on the task, and post what changed under its Pre-check stage."""
    from apps.issues.models import Comment

    from .models import JobFolder

    folder = JobFolder.objects.filter(issue=issue).first()
    if folder is None or not isinstance(report, dict) or "case_id" not in report:
        return []
    changed = changes(folder.gap_report, report)
    newly_final = bool(report.get("finalized_at")) and not (folder.gap_report or {}).get("finalized_at")
    folder.gap_report, folder.gap_report_at = report, timezone.now()
    folder.save(update_fields=["gap_report", "gap_report_at"])
    if post and (changed or newly_final):
        from apps.coordinator.services import agent_user

        heading = ("AI pre-check — the case is settled: every document was checked" if not report.get("provisional")
                   else "AI pre-check — the documents were checked again")
        lines = [_line(r) for r in changed[:MAX_LINES]]
        if len(changed) > MAX_LINES:
            lines.append(f"… and {len(changed) - MAX_LINES} more")
        content = [{"type": "paragraph", "content": [{"type": "text", "text": heading, "marks": [{"type": "bold"}]}]}]
        if lines:
            content.append({"type": "bulletList", "content": [
                {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": ln}]}]} for ln in lines]})
        Comment.objects.create(issue=issue, author=agent_user(), stage="precheck", body={"type": "doc", "content": content})
    return changed


def summary(report: dict) -> dict:
    """What the task card shows: counts by status, provisional or final, and each gap."""
    counts = (report or {}).get("counts") or {}
    return {"provisional": (report or {}).get("provisional", True), "finalized_at": (report or {}).get("finalized_at"), "counts": counts,
            "gaps": [{"gap_id": r["gap_id"], "group": r["group"], "item": r["item"], "status": r["status"], "label": STATUS_LABEL.get(r["status"], r["status"]),
                      "still_needed": r.get("still_needed", ""), "origin": r.get("origin", ""),
                      "evidence": [{k: e.get(k) for k in ("doc_name", "location", "quoted_snippet", "extracted_value", "drive_url", "found_direction")}
                                   for e in r.get("evidence") or []]}
                     for r in _rows(report or {}).values()]}
