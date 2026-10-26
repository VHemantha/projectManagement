"""Shared helpers for provisioning a project's default workflow + board.

Used both by the `seed_demo` management command and by the Project create API,
so a workspace made through the UI ends up with the same pipeline as the demo data — AFIT's
stages (26 Oct 2026): To Start / In Progress / Waiting for Info / Sent to Client / Internal
Adjustments / Client Adjustments / Complete / To be Archived.
"""

from .models import Board, Workflow, WorkflowStatus, WorkflowTransition

# (name, category, column WIP limit), in board order.
STATUS_DEFS = [
    ("To Start", "todo", None),
    ("In Progress", "in_progress", 5),
    ("Waiting for Info", "in_progress", None),
    ("Sent to Client", "in_progress", None),
    ("Internal Adjustments", "in_progress", None),
    ("Client Adjustments", "in_progress", None),
    ("Complete", "done", None),
    ("To be Archived", "done", None),
]

# The automatic "who has it now" moves for the default stages: adjustments go back to the
# preparer (after the internal review, or the client's comments); a reopened job to its assignee.
TRANSITION_DEFS = [
    ("Start", "To Start", "In Progress", "no_change"),
    ("Internal adjustments", None, "Internal Adjustments", "preparer"),
    ("Client adjustments", None, "Client Adjustments", "preparer"),
    ("Reopen", "Complete", "In Progress", "assignee"),
]


def create_default_workflow(project) -> dict[str, WorkflowStatus]:
    workflow, _ = Workflow.objects.get_or_create(project=project)
    statuses = {}
    for order, (name, category, _wip) in enumerate(STATUS_DEFS):
        status, _ = WorkflowStatus.objects.get_or_create(
            workflow=workflow, name=name, defaults=dict(category=category, order=order)
        )
        statuses[name] = status
    return statuses


def create_default_board(project, statuses: dict[str, WorkflowStatus]) -> Board:
    column_config = [
        {"name": name, "status_ids": [statuses[name].id], "wip_limit": wip} for name, _cat, wip in STATUS_DEFS
    ]
    board, _ = Board.objects.get_or_create(
        project=project,
        name=f"{project.name} Board",
        defaults=dict(
            board_type=Board.BoardType.SCRUM if project.project_type == "scrum" else Board.BoardType.KANBAN,
            column_config=column_config,
        ),
    )
    return board


def create_default_transitions(project, statuses: dict[str, WorkflowStatus]) -> None:
    """Seeds the default stages' automatic reassignment rules (transitions are not enforced:
    any stage can move to any other; a matching rule only sets who has the job now)."""
    workflow = statuses["To Start"].workflow
    for name, from_name, to_name, rule in TRANSITION_DEFS:
        WorkflowTransition.objects.get_or_create(
            workflow=workflow,
            from_status=statuses[from_name] if from_name else None,
            to_status=statuses[to_name],
            defaults={"name": name, "set_current_responsible_to": rule},
        )


def sync_status_order(board: Board) -> None:
    """Number the workflow's statuses in the board's column order, so every status list
    (filters, job table grouping, status pickers) reads like the board. Statuses on no column
    keep their relative order after the mapped ones."""
    workflow = board.project.workflow
    position = {}
    for col in board.column_config or []:
        for sid in col.get("status_ids") or []:
            position.setdefault(sid, len(position))
    statuses = list(workflow.statuses.all())
    statuses.sort(key=lambda s: (position.get(s.id, len(position)), s.order, s.id))
    changed = []
    for order, status in enumerate(statuses):
        if status.order != order:
            status.order = order
            changed.append(status)
    if changed:
        WorkflowStatus.objects.bulk_update(changed, ["order"])


def provision_project_defaults(project) -> Board:
    statuses = create_default_workflow(project)
    create_default_transitions(project, statuses)
    return create_default_board(project, statuses)
