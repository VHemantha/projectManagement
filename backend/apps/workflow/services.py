"""Shared helpers for provisioning a project's default workflow + board.

Used both by the `seed_demo` management command and by the Project create API,
so a project made through the UI ends up with the same Jira-standard
To Do / In Progress / In Review / Done pipeline as the demo data.
"""

from .models import Board, Workflow, WorkflowStatus

STATUS_DEFS = [
    ("To Do", "todo"),
    ("In Progress", "in_progress"),
    ("In Review", "in_progress"),
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
        {"name": "To Do", "status_ids": [statuses["To Do"].id], "wip_limit": None},
        {"name": "In Progress", "status_ids": [statuses["In Progress"].id], "wip_limit": 5},
        {"name": "In Review", "status_ids": [statuses["In Review"].id], "wip_limit": 3},
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


def provision_project_defaults(project) -> Board:
    statuses = create_default_workflow(project)
    return create_default_board(project, statuses)
