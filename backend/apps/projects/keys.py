"""Project keys: suggesting them, resolving them (including old keys after a rename) and
renaming a project's key together with all of its jobs."""

import re

from django.db import transaction
from django.http import Http404

from apps.live.broadcast import notify

from .models import KEY_PATTERN, Project, ProjectKeyAlias

ISSUE_KEY = re.compile(r"^(?P<prefix>[A-Za-z][A-Za-z0-9]*)-(?P<number>\d+)$")


def key_in_use(key: str, exclude_project: Project | None = None) -> bool:
    """True if `key` (ignoring case) is another project's key or old key."""
    projects = Project.objects.filter(key__iexact=key)
    aliases = ProjectKeyAlias.objects.filter(key__iexact=key)
    if exclude_project is not None:
        projects = projects.exclude(pk=exclude_project.pk)
        aliases = aliases.exclude(project=exclude_project)
    return projects.exists() or aliases.exists()


def suggest_key(name: str) -> str:
    """The full first word of a name, as typed: "Pochin Group" -> "Pochin". Falls back to
    joining words when the first is too short, and adds a number if the key is taken."""
    # Same rules as the frontend's suggestKey: letters/digits only, leading digits dropped,
    # a too-short first word joined with the next.
    words = [w for w in (re.sub(r"[^A-Za-z0-9]", "", w) for w in name.split()) if w]
    base = ""
    for word in words:
        base = (base + word).lstrip("0123456789")
        if len(base) >= 2:
            break
    if len(base) < 2:
        base = (base + "Project")[:2] if base else "Project"
    base = base[:90]
    candidate, n = base, 2
    while key_in_use(candidate):
        candidate, n = f"{base}{n}", n + 1
    return candidate


def resolve_project(key: str) -> Project | None:
    """A project by its key or any of its old keys, ignoring case."""
    project = Project.objects.filter(key__iexact=key).first()
    if project:
        return project
    alias = ProjectKeyAlias.objects.select_related("project").filter(key__iexact=key).first()
    return alias.project if alias else None


def get_project_or_404(key: str) -> Project:
    project = resolve_project(key)
    if project is None:
        raise Http404("No project with that key.")
    return project


def resolve_issue(key: str, queryset=None):
    """A job by its key, ignoring case — or by an old key (PG-12) after its project was
    renamed, matched through the project's alias and the job number."""
    from apps.issues.models import Issue

    qs = queryset if queryset is not None else Issue.objects.all()
    issue = qs.filter(key__iexact=key).first()
    if issue or not (m := ISSUE_KEY.match(key)):
        return issue
    alias = ProjectKeyAlias.objects.select_related("project").filter(key__iexact=m["prefix"]).first()
    if not alias:
        return None
    return qs.filter(key__iexact=f"{alias.project.key}-{m['number']}").first()


def get_issue_or_404(key: str, queryset=None):
    issue = resolve_issue(key, queryset)
    if issue is None:
        raise Http404("No task with that key.")
    return issue


@transaction.atomic
def rename_project_key(project: Project, new_key: str) -> None:
    """Change a project's key and re-key all its jobs (PG-12 -> Pochin-12). The old key is kept
    as an alias so existing links keep working."""
    from apps.issues.models import Issue

    old_key = project.key
    if new_key == old_key:
        return
    if not re.match(KEY_PATTERN, new_key):
        raise ValueError(f"Invalid project key: {new_key}")
    # Renaming back to an old key: it's the live key again, not an alias.
    ProjectKeyAlias.objects.filter(project=project, key__iexact=new_key).delete()
    if old_key.lower() != new_key.lower():
        ProjectKeyAlias.objects.create(project=project, key=old_key)

    prefix = len(old_key) + 1
    issues = list(Issue.objects.filter(project=project).only("id", "key"))
    for issue in issues:
        issue.key = f"{new_key}-{issue.key[prefix:]}"
    Issue.objects.bulk_update(issues, ["key"], batch_size=500)

    project.key = new_key
    project.save(update_fields=["key", "updated_at"])
    # bulk_update skips signals: tell open views the jobs were re-keyed.
    notify("issues", project=new_key)
