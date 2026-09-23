from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.clients.models import Client
from apps.issues.models import Issue
from apps.projects.models import Project
from apps.teams.models import Team
from apps.timesheets.budget import issue_actual_hours, project_actual_hours, project_effective_cost

NO_TEAM_LABEL = "No Team"
NO_CLIENT_LABEL = "Internal / No Client"
NO_GROUP_LABEL = "Ungrouped"


def _project_node(project: Project) -> dict:
    board = project.boards.first()
    children = []
    if board:
        children.append(
            {
                "id": f"board-{board.id}",
                "type": "board",
                "label": board.name,
                "board_id": board.id,
                "project_key": project.key,
            }
        )
    return {
        "id": f"project-{project.key}",
        "type": "project",
        "label": project.name,
        "key": project.key,
        "children": children,
    }


def _group_projects_by_client(projects, id_prefix: str) -> list[dict]:
    """Client-group a project list into child tree nodes — shared by every team branch (and
    the "No Team" catch-all) so Team -> Client -> Project -> Board stays consistent everywhere
    in the "By Team" tree, not just for teams that happen to have client-tagged projects."""
    by_client: dict[int, list[Project]] = {}
    no_client: list[Project] = []
    for p in projects:
        if p.client_id:
            by_client.setdefault(p.client_id, []).append(p)
        else:
            no_client.append(p)

    clients_by_id = {c.id: c for c in Client.objects.filter(id__in=by_client.keys())}
    children = []
    for client_id, client_projects in sorted(by_client.items(), key=lambda kv: clients_by_id[kv[0]].name):
        client = clients_by_id[client_id]
        children.append(
            {
                "id": f"{id_prefix}-client-{client.id}",
                "type": "client",
                "label": client.name,
                "children": [_project_node(p) for p in client_projects],
            }
        )
    if no_client:
        children.append(
            {
                "id": f"{id_prefix}-client-none",
                "type": "client",
                "label": NO_CLIENT_LABEL,
                "children": [_project_node(p) for p in no_client],
            }
        )
    return children


def _projects_for_teams(teams) -> list[Project]:
    """Every project any of the given teams is the primary team for, or contributes to,
    deduped. Used both per-team (a single-team list) and per-group (a top-level team plus its
    direct sub_teams), so a Group's project set is exactly the union of its teams' own sets."""
    qs = Project.objects.none()
    for team in teams:
        qs = qs | Project.objects.filter(primary_team=team) | Project.objects.filter(contributing_teams=team)
    return list(qs.distinct().order_by("key"))


def _tree_by_team():
    nodes = []
    teams = Team.objects.all().order_by("name")
    seen_project_ids = set()
    for team in teams:
        projects = _projects_for_teams([team])
        seen_project_ids.update(p.id for p in projects)
        nodes.append(
            {
                "id": f"team-{team.id}",
                "type": "team",
                "label": team.name,
                "team_id": team.id,
                "children": _group_projects_by_client(projects, f"team-{team.id}"),
            }
        )

    orphans = list(Project.objects.exclude(id__in=seen_project_ids).order_by("key"))
    if orphans:
        nodes.append(
            {
                "id": "team-none",
                "type": "team",
                "label": NO_TEAM_LABEL,
                "children": _group_projects_by_client(orphans, "team-none"),
            }
        )
    return nodes


def _tree_by_group():
    """A "Group" is just a top-level Team (parent is null); its node's projects are the union
    of its own projects plus every direct sub_team's projects (one level, matching the org
    chart's exact 2-level depth) — reuses the same _group_projects_by_client() client-grouping
    every other tree mode uses, so Group -> Client -> Project -> Board stays consistent."""
    nodes = []
    top_level_teams = Team.objects.filter(parent__isnull=True).prefetch_related("sub_teams").order_by("name")
    seen_project_ids = set()
    for group_team in top_level_teams:
        team_and_children = [group_team, *group_team.sub_teams.all()]
        projects = _projects_for_teams(team_and_children)
        seen_project_ids.update(p.id for p in projects)
        nodes.append(
            {
                "id": f"group-{group_team.id}",
                "type": "group",
                "label": group_team.name,
                "team_id": group_team.id,
                "children": _group_projects_by_client(projects, f"group-{group_team.id}"),
            }
        )

    orphans = list(Project.objects.exclude(id__in=seen_project_ids).order_by("key"))
    if orphans:
        nodes.append(
            {
                "id": "group-none",
                "type": "group",
                "label": NO_GROUP_LABEL,
                "children": _group_projects_by_client(orphans, "group-none"),
            }
        )
    return nodes


def _tree_by_client():
    nodes = []
    clients = Client.objects.all().order_by("name")
    for client in clients:
        projects = Project.objects.filter(client=client).order_by("key")
        nodes.append(
            {
                "id": f"client-{client.id}",
                "type": "client",
                "label": client.name,
                "children": [_project_node(p) for p in projects],
            }
        )

    orphans = Project.objects.filter(client__isnull=True).order_by("key")
    if orphans.exists():
        nodes.append(
            {"id": "client-none", "type": "client", "label": NO_CLIENT_LABEL, "children": [_project_node(p) for p in orphans]}
        )
    return nodes


class NavTreeView(APIView):
    """GET /api/reports/nav-tree/?group_by=team|client|group — returns the nested
    Team/Client/Group -> Project -> Board structure for the Projects page's tree-nav view in
    one call, rather than making the frontend stitch together separate project/team/client
    list endpoints itself. A project with multiple contributing teams appears once under each
    relevant team (or group) branch. "group" mode collapses to top-level Teams (Team.parent is
    null) each expanded straight to Client, skipping the sub-team level entirely — this is a
    navigation/view concept, not a schema change — nothing here restructures where boards
    actually live)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        group_by = request.query_params.get("group_by", "team")
        if group_by == "client":
            nodes = _tree_by_client()
        elif group_by == "group":
            nodes = _tree_by_group()
        else:
            nodes = _tree_by_team()
        return Response({"group_by": group_by, "nodes": nodes})


def _project_budget_row(project: Project) -> dict:
    actual_hours = project_actual_hours(project.id)
    budgeted = project.budgeted_hours
    variance = (actual_hours - budgeted) if budgeted is not None else None
    pct_complete = round((actual_hours / budgeted) * 100, 1) if budgeted else None
    effective_cost = project_effective_cost(project.id)
    job_value = project.job_value
    margin = (job_value - effective_cost) if job_value is not None else None
    return {
        "project_key": project.key,
        "project_name": project.name,
        "budgeted_hours": budgeted,
        "actual_hours": actual_hours,
        "variance_hours": variance,
        "pct_complete": pct_complete,
        "job_value": job_value,
        "job_value_currency": project.job_value_currency,
        "effective_cost": effective_cost,
        "margin": margin,
    }


class BudgetVsActualView(APIView):
    """GET /api/reports/budget-vs-actual/ — budgeted vs. actual hours (+ job value / effective
    cost / margin) for every project, or for one project (?project=<key>) plus an issue-level
    breakdown for drill-down. Reporting/visibility only, per the Timesheets addendum's existing
    no-invoicing scope boundary — this never writes anything."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        project_key = request.query_params.get("project")
        if project_key:
            project = get_object_or_404(Project, key__iexact=project_key)
            row = _project_budget_row(project)
            issue_rows = []
            for issue in Issue.objects.filter(project=project):
                actual = issue_actual_hours(issue.id)
                if issue.budgeted_hours is None and actual == 0:
                    continue
                issue_variance = (actual - issue.budgeted_hours) if issue.budgeted_hours is not None else None
                issue_rows.append(
                    {
                        "issue_key": issue.key,
                        "summary": issue.summary,
                        "budgeted_hours": issue.budgeted_hours,
                        "actual_hours": actual,
                        "variance_hours": issue_variance,
                        "allocated_value": issue.allocated_value,
                    }
                )
            return Response({"project": row, "issues": issue_rows})

        rows = [_project_budget_row(p) for p in Project.objects.filter(is_archived=False).order_by("key")]
        return Response({"projects": rows})
