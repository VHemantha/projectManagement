from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.exceptions import PermissionDenied

from apps.projects.models import ProjectMembership

from .models import Board, IssueType, Workflow, WorkflowTransition
from .serializers import BoardConfigSerializer, IssueTypeSerializer, WorkflowTransitionSerializer


class IssueTypeListView(generics.ListAPIView):
    serializer_class = IssueTypeSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = IssueType.objects.filter(project__isnull=True)
        project_key = self.request.query_params.get("project")
        if project_key:
            qs = IssueType.objects.filter(project__isnull=True) | IssueType.objects.filter(
                project__key__iexact=project_key
            )
        include_subtasks = self.request.query_params.get("include_subtasks", "true")
        if include_subtasks.lower() == "false":
            qs = qs.filter(is_subtask=False)
        return qs.order_by("order", "id")


def _can_configure_board(user, board: Board) -> bool:
    """Same ad-hoc helper-function style as timesheets' _can_approve: no dedicated
    BoardMembership model exists (or is worth adding for v1) — a project admin/lead, or a
    workspace admin, can edit board configuration."""
    if user.is_staff:
        return True
    project = board.project
    if project.lead_id == user.id:
        return True
    return ProjectMembership.objects.filter(
        project=project, user=user, role=ProjectMembership.Role.ADMIN
    ).exists()


class BoardConfigView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/boards/<id>/config/ — columns, swimlane mode, card fields, color rule."""

    serializer_class = BoardConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Board.objects.select_related("project", "project__workflow")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS and not _can_configure_board(request.user, obj):
            raise PermissionDenied("Only a project admin/lead or workspace admin can configure this board.")


class WorkflowTransitionListView(generics.ListAPIView):
    """GET /api/projects/<key>/workflow/transitions/ — read-only list backing the "Transition
    rules" table in Project Settings; used to configure set_current_responsible_to per
    transition without a SQL console."""

    serializer_class = WorkflowTransitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        project_key = self.kwargs["project_key"]
        workflow = get_object_or_404(Workflow, project__key__iexact=project_key)
        return WorkflowTransition.objects.filter(workflow=workflow).select_related("from_status", "to_status")


class WorkflowTransitionDetailView(generics.UpdateAPIView):
    """PATCH /api/workflow-transitions/<id>/ — only set_current_responsible_to is meant to be
    edited here; from/to status and name stay fixed (they're structural to the workflow)."""

    serializer_class = WorkflowTransitionSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = WorkflowTransition.objects.select_related("workflow__project")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        project = obj.workflow.project
        allowed = (
            request.user.is_staff
            or project.lead_id == request.user.id
            or ProjectMembership.objects.filter(
                project=project, user=request.user, role=ProjectMembership.Role.ADMIN
            ).exists()
        )
        if not allowed:
            raise PermissionDenied("Only a project admin/lead or workspace admin can edit transition rules.")
