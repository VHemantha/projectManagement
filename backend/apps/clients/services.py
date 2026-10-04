from django.db import transaction

from apps.projects.keys import suggest_key
from apps.projects.models import Project, ProjectMembership

from .models import Client


@transaction.atomic
def get_or_create_client_workspace(client: Client, user) -> Project:
    """The client's automatic job container, created the first time a job is added for the
    client without a project. It's a normal Kanban project named after the client (key from
    the client's name, e.g. "Acme"), flagged is_client_workspace."""
    from apps.workflow.services import provision_project_defaults

    workspace = Project.objects.filter(client=client, is_client_workspace=True).first()
    if workspace:
        return workspace
    workspace = Project.objects.create(
        organization=client.organization,
        key=suggest_key(client.name),
        name=client.name,
        description=f"Tasks for {client.name} that don't belong to a project.",
        project_type=Project.ProjectType.KANBAN,
        lead=user,
        client=client,
        primary_team=client.team,  # stays in the sub-workspace's workspace
        is_client_workspace=True,
    )
    provision_project_defaults(workspace)
    ProjectMembership.objects.get_or_create(
        project=workspace, user=user, defaults={"role": ProjectMembership.Role.ADMIN}
    )
    return workspace
