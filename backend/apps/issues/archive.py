"""Auto-archive (AFIT, 1 Nov 2026): a task that has been completed for 7 days, that is, in a done
stage (Complete, To be Archived) or in its board's last column, is archived with its sub-tasks.
Archived tasks are kept (reports, history, time) and can be restored from the task list's
"Show archived"."""
from datetime import timedelta

from django.db.models import Max, Q
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Issue
from .serializers import set_archived

AFTER_DAYS = 7


def completed_statuses() -> set[int]:
    """Every done stage, and the stages in the last column of each project's board."""
    from apps.workflow.models import Board, WorkflowStatus

    ids = set(WorkflowStatus.objects.filter(category="done").values_list("id", flat=True))
    last_board = {}
    for board in Board.objects.order_by("id"):
        last_board.setdefault(board.project_id, board)
    for board in last_board.values():
        columns = [c for c in (board.column_config or []) if isinstance(c, dict)]
        if columns:
            ids.update(int(s) for s in columns[-1].get("status_ids") or [])
    return ids


def due_for_archive(now=None):
    """Top-level tasks, not archived, completed at least AFTER_DAYS ago: since they were finished
    (moving between done stages keeps that date), else their latest stage change, else creation."""
    now = now or timezone.now()
    return (Issue.objects.filter(is_archived=False, parent__isnull=True, status_id__in=completed_statuses())
            .annotate(moved=Max("history__timestamp", filter=Q(history__field_changed="status")))
            .annotate(completed=Coalesce("resolved_at", "moved", "created_at"))
            .filter(completed__lte=now - timedelta(days=AFTER_DAYS)))


def auto_archive(now=None) -> int:
    ids = list(due_for_archive(now).values_list("id", flat=True))
    if not ids:
        return 0
    return set_archived(Issue.objects.filter(Q(id__in=ids) | Q(parent_id__in=ids)), True)
