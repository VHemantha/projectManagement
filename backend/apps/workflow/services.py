"""Shared helpers for provisioning a project's default workflow + board.

Used both by the `seed_demo` management command and by the Project create API,
so a workspace made through the UI ends up with the same pipeline as the demo data:
Backlog / To do / In progress / In review / Blocked / Done.
"""

from .models import Board, Workflow, WorkflowStatus, WorkflowTransition

# (name, category, column WIP limit), in board order.
STATUS_DEFS = [
    ("Backlog", "todo", None),
    ("To do", "todo", None),
    ("In progress", "in_progress", 5),
    ("In review", "in_progress", 3),
    ("Blocked", "in_progress", None),
    ("Done", "done", None),
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
    """Seeds the standard forward/backward moves for the default pipeline, with the
    In Progress <-> In Review pair pre-wired to the addendum's current_responsible
    auto-reassignment rule — otherwise the "Transition rules" settings table would start out
    empty on every project and the feature would have nothing to demonstrate."""
    workflow = statuses["To do"].workflow
    defs = [
        ("Plan", "Backlog", "To do", WorkflowTransition.ReassignRule.NO_CHANGE),
        ("Start progress", "To do", "In progress", WorkflowTransition.ReassignRule.NO_CHANGE),
        ("Send for review", "In progress", "In review", WorkflowTransition.ReassignRule.REVIEWER),
        ("Request changes", "In review", "In progress", WorkflowTransition.ReassignRule.PREPARER),
        ("Approve", "In review", "Done", WorkflowTransition.ReassignRule.NO_CHANGE),
        ("Reopen", "Done", "In progress", WorkflowTransition.ReassignRule.ASSIGNEE),
        ("Block", "In progress", "Blocked", WorkflowTransition.ReassignRule.NO_CHANGE),
        ("Unblock", "Blocked", "In progress", WorkflowTransition.ReassignRule.NO_CHANGE),
    ]
    for name, from_name, to_name, rule in defs:
        WorkflowTransition.objects.get_or_create(
            workflow=workflow,
            from_status=statuses[from_name],
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
