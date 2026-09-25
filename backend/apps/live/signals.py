"""Turn model changes into live update notices (see broadcast.py).

Bulk queryset operations (`.update()`, `bulk_update`) skip these signals; code that uses them
calls broadcast.notify() itself (e.g. sprints' complete/reorder views)."""

from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver

from apps.clients.models import Client
from apps.issues.models import Attachment, Comment, Issue, IssueLink
from apps.projects.models import Label, Project
from apps.sprints.models import Sprint
from apps.teams.models import Team, TeamMembership
from apps.timesheets.models import TimeEntry
from apps.workflow.models import Board, WorkflowStatus, WorkflowTransition

from .broadcast import notify


def _project_key(obj, attr="project"):
    """The related project's key, or None if it's already gone (e.g. mid cascade-delete)."""
    try:
        project = getattr(obj, attr)
    except Project.DoesNotExist:
        return None
    return project.key if project else None


@receiver(post_save, sender=Issue)
@receiver(post_delete, sender=Issue)
def issue_changed(sender, instance, **kwargs):
    notify("issues", project=_project_key(instance), key=instance.key)


@receiver(m2m_changed, sender=Issue.labels.through)
def issue_labels_changed(sender, instance, action, **kwargs):
    if action in ("post_add", "post_remove", "post_clear") and isinstance(instance, Issue):
        notify("issues", project=_project_key(instance), key=instance.key)


@receiver(post_save, sender=Comment)
@receiver(post_delete, sender=Comment)
@receiver(post_save, sender=Attachment)
@receiver(post_delete, sender=Attachment)
def issue_detail_changed(sender, instance, **kwargs):
    issue = getattr(instance, "issue", None)
    if issue is not None:
        notify("issue", project=_project_key(issue), key=issue.key)


@receiver(post_save, sender=IssueLink)
@receiver(post_delete, sender=IssueLink)
def issue_link_changed(sender, instance, **kwargs):
    for issue in (instance.source_issue, instance.target_issue):
        notify("issue", project=_project_key(issue), key=issue.key)


@receiver(post_save, sender=TimeEntry)
@receiver(post_delete, sender=TimeEntry)
def time_logged(sender, instance, **kwargs):
    # A job's actual hours come from its time entries.
    issue = getattr(instance, "issue", None)
    if issue is not None:
        notify("issues", project=_project_key(issue), key=issue.key)


@receiver(post_save, sender=Board)
def board_changed(sender, instance, **kwargs):
    notify("board", project=_project_key(instance))


@receiver(post_save, sender=WorkflowStatus)
@receiver(post_delete, sender=WorkflowStatus)
@receiver(post_save, sender=WorkflowTransition)
@receiver(post_delete, sender=WorkflowTransition)
def workflow_changed(sender, instance, **kwargs):
    try:
        project = instance.workflow.project
    except Exception:  # workflow/project already deleted in a cascade
        return
    notify("board", project=project.key)


@receiver(post_save, sender=Project)
@receiver(post_delete, sender=Project)
def project_changed(sender, instance, **kwargs):
    notify("project", project=instance.key)


@receiver(post_save, sender=Label)
@receiver(post_delete, sender=Label)
def label_changed(sender, instance, **kwargs):
    notify("project", project=_project_key(instance))


@receiver(post_save, sender=Sprint)
@receiver(post_delete, sender=Sprint)
def sprint_changed(sender, instance, **kwargs):
    notify("sprints", project=_project_key(instance))


@receiver(post_save, sender=Team)
@receiver(post_delete, sender=Team)
@receiver(post_save, sender=TeamMembership)
@receiver(post_delete, sender=TeamMembership)
def team_changed(sender, instance, **kwargs):
    notify("teams")


@receiver(post_save, sender=Client)
@receiver(post_delete, sender=Client)
def client_changed(sender, instance, **kwargs):
    notify("clients")
