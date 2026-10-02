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
