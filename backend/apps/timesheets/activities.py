"""Time that is not on a job (AFIT, 21 Nov 2026): idle time, administration and training. Each is a card
(a task) people log time to, kept in a project of its own - "Non-job time" - that is archived, so the
cards never show on a Kanban view, a task list, the projects tree or the Practice Manager AI's follow-ups.
They are created the first time they are needed.
"""
from django.db import transaction

ACTIVITY_PROJECT_KEY = "NONJOB"
ACTIVITIES = [("idle", "Idle"), ("administration", "Administration"), ("training", "Training")]
LABEL = dict(ACTIVITIES)


@transaction.atomic
def activity_tasks(by) -> list:
    """The three cards, in order, creating them (and their project) the first time; `by` is recorded as
    the cards' reporter."""
    from apps.issues.models import Issue
    from apps.orgs.models import Organization
    from apps.projects.models import Project
    from apps.workflow.models import IssueType
    from apps.workflow.services import provision_project_defaults

    project = Project.objects.filter(key=ACTIVITY_PROJECT_KEY).first()
    if project is None:
        project = Project.objects.create(organization=Organization.get_solo(), key=ACTIVITY_PROJECT_KEY, name="Non-job time",
                                         description="Idle time, administration and training: logged to, never shown on a board.",
                                         is_archived=True)
        provision_project_defaults(project)
    elif not project.is_archived:
        project.is_archived = True
        project.save(update_fields=["is_archived"])
    task_type, _ = IssueType.objects.get_or_create(name="Task", project=None)
    status = project.workflow.statuses.order_by("order").first()
    out = []
    for key, label in ACTIVITIES:
        issue = Issue.objects.filter(project=project, activity=key).first()
        if issue is None:
            issue = Issue.objects.create(project=project, issue_type=task_type, summary=label, status=status, activity=key, is_archived=True,
                                         reporter=by)
        out.append(issue)
    return out


def is_activity(issue) -> bool:
    return bool(issue is not None and getattr(issue, "activity", ""))
