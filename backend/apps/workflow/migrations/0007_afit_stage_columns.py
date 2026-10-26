"""AFIT's stages as every board's columns (26 Oct 2026):

    To Start, In Progress, Waiting for Info, Sent to Client, Internal Adjustments,
    Client Adjustments, Complete, To be Archived

For every project, each existing status is mapped to one of these (below; anything else by its
category). For each new stage one status is kept and renamed; tasks in the others mapped to it move
there, and those statuses are removed. Missing stages are added. Every board gets exactly the eight
columns, in order (a column's WIP limit and colour are kept when it carries over). The default
reassignment rules of the old pipeline are replaced by the new defaults; any other rule follows its
statuses. Complete and To be Archived count as finished work.

Safe to run more than once. Not reversible (merged stages cannot be told apart again).
"""
from django.db import migrations
from django.utils import timezone

STAGES = [
    ("To Start", "todo"),
    ("In Progress", "in_progress"),
    ("Waiting for Info", "in_progress"),
    ("Sent to Client", "in_progress"),
    ("Internal Adjustments", "in_progress"),
    ("Client Adjustments", "in_progress"),
    ("Complete", "done"),
    ("To be Archived", "done"),
]
# Existing names (lower case) to the stage they become.
MAP = {
    "backlog": "To Start", "to do": "To Start", "todo": "To Start", "not scheduled": "To Start", "to start": "To Start",
    "in progress": "In Progress", "prep in progress": "In Progress",
    "blocked": "Waiting for Info", "waiting for info": "Waiting for Info",
    "sent to client": "Sent to Client",
    "in review": "Internal Adjustments", "second review": "Internal Adjustments", "finalising - internal review": "Internal Adjustments",
    "adjustments in progress": "Internal Adjustments", "internal adjustments": "Internal Adjustments",
    "client adjustments": "Client Adjustments",
    "done": "Complete", "complete": "Complete",
    "to be archived": "To be Archived",
}
BY_CATEGORY = {"todo": "To Start", "in_progress": "In Progress", "done": "Complete"}
WIP = {"In Progress": 5}
# The old pipeline's seeded rules (name, from, to): replaced by the new defaults.
OLD_DEFAULT_RULES = {"Plan", "Start progress", "Send for review", "Request changes", "Approve", "Reopen", "Block", "Unblock"}
NEW_RULES = [
    ("Start", "To Start", "In Progress", "no_change"),
    ("Internal adjustments", None, "Internal Adjustments", "preparer"),
    ("Client adjustments", None, "Client Adjustments", "preparer"),
    ("Reopen", "Complete", "In Progress", "assignee"),
]


def stage_of(status) -> str:
    return MAP.get(status.name.strip().lower()) or BY_CATEGORY.get(status.category, "In Progress")


def convert(apps, schema_editor):
    Workflow = apps.get_model("workflow", "Workflow")
    WorkflowStatus = apps.get_model("workflow", "WorkflowStatus")
    WorkflowTransition = apps.get_model("workflow", "WorkflowTransition")
    Board = apps.get_model("workflow", "Board")
    Issue = apps.get_model("issues", "Issue")
    now = timezone.now()

    for workflow in Workflow.objects.all():
        statuses = list(WorkflowStatus.objects.filter(workflow=workflow).order_by("order", "id"))
        groups: dict[str, list] = {}
        for s in statuses:
            groups.setdefault(stage_of(s), []).append(s)

        keeper: dict[str, object] = {}
        for order, (name, category) in enumerate(STAGES):
            members = groups.get(name, [])
            # Keep the one already called by the stage's name, else the one with the most tasks.
            exact = [s for s in members if s.name.strip().lower() == name.lower()]
            keep = exact[0] if exact else (max(members, key=lambda s: Issue.objects.filter(status=s).count()) if members else None)
            if keep is None:
                keep = WorkflowStatus.objects.create(workflow=workflow, name=name, category=category, order=order)
            else:
                keep.name, keep.category, keep.order = name, category, order
                keep.save(update_fields=["name", "category", "order"])
            keeper[name] = keep
            for other in members:
                if other.pk == keep.pk:
                    continue
                Issue.objects.filter(status=other).update(status=keep)
                WorkflowTransition.objects.filter(from_status=other).update(from_status=keep)
                WorkflowTransition.objects.filter(to_status=other).update(to_status=keep)
                other.delete()

        # Finished work has a completion date (reports and the KPI read it).
        done_ids = [keeper["Complete"].pk, keeper["To be Archived"].pk]
        for issue in Issue.objects.filter(status_id__in=done_ids, resolved_at__isnull=True):
            issue.resolved_at = issue.updated_at or now
            issue.save(update_fields=["resolved_at"])

        # Reassignment rules: the old seeded ones go, the new defaults come, others stay.
        rules = WorkflowTransition.objects.filter(workflow=workflow)
        rules.filter(name__in=OLD_DEFAULT_RULES).delete()
        seen = set()
        for rule in WorkflowTransition.objects.filter(workflow=workflow).order_by("id"):
            key = (rule.from_status_id, rule.to_status_id)
            if rule.from_status_id == rule.to_status_id or key in seen:
                rule.delete()  # merged into a move from a stage to itself, or a duplicate
            else:
                seen.add(key)
        for name, from_name, to_name, rule in NEW_RULES:
            from_status = keeper[from_name] if from_name else None
            if (getattr(from_status, "pk", None), keeper[to_name].pk) in seen:
                continue
            WorkflowTransition.objects.create(workflow=workflow, name=name, from_status=from_status, to_status=keeper[to_name],
                                              set_current_responsible_to=rule)

        # Every board: exactly the eight columns, in order.
        for board in Board.objects.filter(project_id=workflow.project_id):
            old = {str(c.get("name", "")).strip().lower(): c for c in (board.column_config or []) if isinstance(c, dict)}
            columns = []
            for name, _category in STAGES:
                previous = old.get(name.lower(), {})
                columns.append({"name": name, "status_ids": [keeper[name].pk], "wip_limit": previous.get("wip_limit", WIP.get(name)),
                                **({"color": previous["color"]} if previous.get("color") else {})})
            board.column_config = columns
            board.save(update_fields=["column_config"])


class Migration(migrations.Migration):
    dependencies = [
        ("workflow", "0006_kanban_default_columns"),
        ("issues", "0009_issue_group"),
    ]
    operations = [migrations.RunPython(convert, migrations.RunPython.noop)]
