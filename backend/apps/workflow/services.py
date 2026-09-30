"""Shared helpers for provisioning a project's default workflow + board.

Used both by the `seed_demo` management command and by the Project create API,
so a project made through the UI ends up with the same Jira-standard
To do / In progress / In review / Done pipeline as the demo data.
"""

from .models import Board, Workflow, WorkflowStatus, WorkflowTransition

STATUS_DEFS = [
    ("To do", "todo"),
    ("In progress", "in_progress"),
    ("In review", "in_progress"),
    ("Done", "done"),
]


def create_default_workflow(project) -> dict[str, WorkflowStatus]:
    workflow, _ = Workflow.objects.get_or_create(project=project)
    statuses = {}
    for order, (name, category) in enumerate(STATUS_DEFS):
        status, _ = WorkflowStatus.objects.get_or_create(
            workflow=workflow, name=name, defaults=dict(category=category, order=order)
        )
        statuses[name] = status
    return statuses


def create_default_board(project, statuses: dict[str, WorkflowStatus]) -> Board:
    column_config = [
        {"name": "To do", "status_ids": [statuses["To do"].id], "wip_limit": None},
        {"name": "In progress", "status_ids": [statuses["In progress"].id], "wip_limit": 5},
        {"name": "In review", "status_ids": [statuses["In review"].id], "wip_limit": 3},
        {"name": "Done", "status_ids": [statuses["Done"].id], "wip_limit": None},
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
        ("Start progress", "To do", "In progress", WorkflowTransition.ReassignRule.NO_CHANGE),
        ("Send for review", "In progress", "In review", WorkflowTransition.ReassignRule.REVIEWER),
        ("Request changes", "In review", "In progress", WorkflowTransition.ReassignRule.PREPARER),
        ("Approve", "In review", "Done", WorkflowTransition.ReassignRule.NO_CHANGE),
        ("Reopen", "Done", "In progress", WorkflowTransition.ReassignRule.ASSIGNEE),
    ]
    for name, from_name, to_name, rule in defs:
        WorkflowTransition.objects.get_or_create(
            workflow=workflow,
            from_status=statuses[from_name],
            to_status=statuses[to_name],
            defaults={"name": name, "set_current_responsible_to": rule},
        )


def provision_project_defaults(project) -> Board:
    statuses = create_default_workflow(project)
    create_default_transitions(project, statuses)
    return create_default_board(project, statuses)
