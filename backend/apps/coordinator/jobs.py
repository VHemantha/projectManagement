"""Creating jobs by asking the Practice Manager AI (AFIT, 21 Nov 2026), in a typed or spoken message:
"create a year-end job for Smith Family Trust in RWCA, Pat to prepare, due 30 June". The model lists the
jobs asked for, with the sub-workspace and people from the lists it is given; code creates each one
exactly as the Create task form would (the same checks, defaults, numbering and standard sub-tasks),
as the person who asked, and the reply says what was really created - never the model's own claim.
"""
from datetime import date

CREATE_SCHEMA = {
    "type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "required": ["title", "sub_workspace_id", "group", "assignee_id", "preparer_id", "due_date", "budgeted_hours", "standard_stages"],
        "properties": {
            "title": {"type": "string"}, "sub_workspace_id": {"type": "integer"}, "group": {"type": "string"},
            "assignee_id": {"type": "integer"}, "preparer_id": {"type": "integer"}, "due_date": {"type": "string"},
            "budgeted_hours": {"type": "number"}, "standard_stages": {"type": "boolean"},
        }}}

RULES = """
Creating jobs (tasks):
- When they ask you to create, add, open or set up a job (a task), add one entry to "create_jobs" per job: the title (e.g. "Smith Family Trust - FY26 accounts"), the sub_workspace_id from SUB-WORKSPACES (the client firm the job is for), the group (the client group, "" if not given), the assignee_id (team lead) and preparer_id (accountant) from PEOPLE (-1 if not given), the due date as YYYY-MM-DD ("" if not given), budgeted_hours (-1 if not given) and standard_stages (true unless they say not to add the standard sub-tasks).
- Only when they clearly ask for a job to be created. If the title or the sub-workspace is unclear, leave "create_jobs" empty and ask for what is missing.
- Code creates the jobs and adds a confirmation with each new job's key, so in your reply just say briefly that you are creating it. Never say a job was created otherwise."""

MAX_JOBS = 10
MAX_LINES = 80


def context_lines(person, *, with_people: bool = True) -> list[str]:
    from apps.accounts.models import User
    from apps.clients.models import Client

    clients = Client.objects.select_related("team").order_by("name")[:MAX_LINES]
    people = User.objects.filter(is_active=True, is_agent=False).order_by("display_name")[:MAX_LINES]
    lines = (["\n== SUB-WORKSPACES (sub_workspace_id: name — workspace) =="]
             + ([f"{c.pk}: {c.name}" + (f" — {c.team.name}" if c.team_id else "") for c in clients] or ["(none)"]))
    if with_people:
        lines += (["\n== PEOPLE (person_id: name — job title) =="]
                  + ([f"{u.pk}: {u.display_name or u.username}" + (f" — {u.job_title}" if u.job_title else "") for u in people] or ["(nobody)"]))
    return lines


class _Request:
    """What the task serializer needs of a request: who is creating the task."""

    def __init__(self, user):
        self.user = user


def _due(value: str) -> str | None:
    try:
        d = date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None
    return d.isoformat()


def create(person, items: list[dict]) -> tuple[list, list[str]]:
    """Create the jobs asked for. Returns (created issues, lines for the reply)."""
    from apps.accounts.models import User
    from apps.clients.models import Client
    from apps.issues.serializers import IssueDetailSerializer
    from apps.workflow.models import IssueType

    task_type = IssueType.objects.filter(name="Task", project=None).first() or IssueType.objects.filter(is_subtask=False).first()
    people = set(User.objects.filter(is_active=True, is_agent=False).values_list("id", flat=True))
    created, lines = [], []
    for item in (items or [])[:MAX_JOBS]:
        title = " ".join(str(item.get("title", "")).split())[:500]
        client = Client.objects.filter(pk=item.get("sub_workspace_id")).first() if isinstance(item.get("sub_workspace_id"), int) else None
        if not title or client is None:
            lines.append(f"I couldn't create “{title or 'a job'}”: tell me which sub-workspace it is for.")
            continue
        data = {"summary": title, "client_id": client.pk, "issue_type_id": task_type.pk if task_type else None,
                "group": str(item.get("group", "")), "default_subtasks": bool(item.get("standard_stages", True))}
        for field in ("assignee_id", "preparer_id"):
            if item.get(field) in people:
                data[field] = item[field]
        if due := _due(item.get("due_date", "")):
            data["due_date"] = due
        hours = item.get("budgeted_hours")
        if isinstance(hours, (int, float)) and hours > 0:
            data["budgeted_hours"] = hours
        serializer = IssueDetailSerializer(data=data, context={"request": _Request(person)})
        dropped_budget = False
        if not serializer.is_valid():
            # A budget only a team lead may set: create the job without it rather than not at all.
            if "budgeted_hours" in serializer.errors:
                data.pop("budgeted_hours", None)
                dropped_budget = True
                serializer = IssueDetailSerializer(data=data, context={"request": _Request(person)})
        if not serializer.is_valid():
            problem = "; ".join(f"{k}: {' '.join(map(str, v)) if isinstance(v, list) else v}" for k, v in serializer.errors.items())
            lines.append(f"I couldn't create “{title}”: {problem}")
            continue
        issue = serializer.save()
        created.append(issue)
        who = [f"{label} {u.display_name}" for label, u in (("team lead", issue.assignee), ("accountant", issue.preparer)) if u]
        lines.append(f"Created {issue.key} “{issue.summary}” in {client.name}"
                     + (f", {', '.join(who)}" if who else "") + (f", due {issue.due_date:%a %d %b %Y}" if issue.due_date else "")
                     + (f", {issue.budgeted_hours:g}h budgeted" if issue.budgeted_hours else "") + ".")
        if dropped_budget:
            lines.append("Only a team lead or above can set the budgeted hours, so I left them for a lead to set.")
    return created, lines
