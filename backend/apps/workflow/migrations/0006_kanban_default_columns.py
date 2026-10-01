"""Default Kanban columns: Backlog, To do, In progress, In review, Blocked, Done.

For every existing workspace:
- a Backlog status/column is added as the first column (an existing "Backlog" status is reused);
- a Blocked status/column is added just before the Done column (an existing "Blocked" status is
  reused, and a Blocked column a team already placed somewhere is left where it is);
- everything else stays as it is: custom columns (e.g. QA) keep their place, and no job changes
  status;
- statuses are renumbered in column order so status lists read like the board.

Safe to run more than once. Reversing leaves the new statuses and columns in place (removing
them could strand jobs that were moved into them).
"""

from django.db import migrations

BACKLOG = ("Backlog", "todo")
BLOCKED = ("Blocked", "in_progress")


def _named(statuses, name):
    return next((s for s in statuses if s.name.strip().lower() == name.lower()), None)


def _column_of(columns, status_id):
    return next((i for i, col in enumerate(columns) if status_id in (col.get("status_ids") or [])), None)


def _done_column_index(columns, category_of):
    """The first column holding only 'done' statuses (normally "Done"), else one named Done."""
    for i, col in enumerate(columns):
        ids = col.get("status_ids") or []
        if ids and all(category_of.get(sid) == "done" for sid in ids):
            return i
    for i, col in enumerate(columns):
        if str(col.get("name", "")).strip().lower() == "done":
            return i
    return None


def add_default_columns(apps, schema_editor):
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStatus = apps.get_model("workflow", "WorkflowStatus")
    Board = apps.get_model("workflow", "Board")

    for workflow in Workflow.objects.all():
        statuses = list(WorkflowStatus.objects.filter(workflow=workflow))
        next_order = max((s.order for s in statuses), default=-1) + 1
        ensured = {}
        for name, category in (BACKLOG, BLOCKED):
            status = _named(statuses, name)
            if status is None:
                status = WorkflowStatus.objects.create(workflow=workflow, name=name, category=category, order=next_order)
                next_order += 1
                statuses.append(status)
            ensured[name] = status
        backlog, blocked = ensured["Backlog"], ensured["Blocked"]
        category_of = {s.id: s.category for s in statuses}

        boards = list(Board.objects.filter(project_id=workflow.project_id).order_by("id"))
        for board in boards:
            columns = [c for c in (board.column_config or []) if isinstance(c, dict)]
            original = [dict(c) for c in columns]

            i = _column_of(columns, backlog.id)
            if i is None:
                columns.insert(0, {"name": "Backlog", "status_ids": [backlog.id], "wip_limit": None})
            elif i != 0:
                columns.insert(0, columns.pop(i))

            if _column_of(columns, blocked.id) is None:
                done = _done_column_index(columns, category_of)
                column = {"name": "Blocked", "status_ids": [blocked.id], "wip_limit": None}
                columns.insert(done if done is not None else len(columns), column)

            if columns != original:
                board.column_config = columns
                board.save(update_fields=["column_config"])

        # Number statuses in the (first) board's column order.
        position = {}
        if boards:
            for col in boards[0].column_config or []:
                for sid in col.get("status_ids") or []:
                    position.setdefault(sid, len(position))
        statuses.sort(key=lambda s: (position.get(s.id, len(position)), s.order, s.id))
        for order, status in enumerate(statuses):
            if status.order != order:
                status.order = order
                status.save(update_fields=["order"])


class Migration(migrations.Migration):

    dependencies = [
        ("workflow", "0005_job_value_card_field"),
    ]

    operations = [
        migrations.RunPython(add_default_columns, migrations.RunPython.noop),
    ]
