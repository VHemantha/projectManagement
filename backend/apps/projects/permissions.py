from .models import Project, ProjectMembership


def can_manage_project(user, project: Project) -> bool:
    """Who may change a workspace's board, budget, deadline and notes: an organisation admin
    (staff), the workspace lead, or one of the workspace's admins. Everyone else can view."""
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or project.lead_id == user.id:
        return True
    return ProjectMembership.objects.filter(
        project=project, user=user, role=ProjectMembership.Role.ADMIN
    ).exists()


def can_set_budget(user, project: Project) -> bool:
    """Team lead and above (AFIT, 18 Oct 2026): budgeted time on a task feeds the KPI of the person it
    is assigned to, so only an organisation admin, the project's lead or admins, or a lead of the
    project's workspace (team) may set it."""
    if can_manage_project(user, project):
        return True
    from apps.teams.models import TeamMembership

    teams = [t for t in (project.primary_team_id, getattr(project.client, "team_id", None) if project.client_id else None) if t]
    return bool(teams) and TeamMembership.objects.filter(team_id__in=teams, user=user, role=TeamMembership.Role.LEAD).exists()


def can_delete_task(user, project: Project) -> bool:
    """Deleting a task is permanent (its sub-tasks, comments, history, AI pre-check runs and
    follow-ups go with it), so it's for team lead and above (AFIT, 28 Oct 2026): the same people
    who may set budgeted time."""
    return can_set_budget(user, project)
