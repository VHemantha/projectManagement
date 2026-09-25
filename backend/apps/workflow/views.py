from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.models import ProjectMembership

from .models import Board, IssueType, Workflow, WorkflowStatus, WorkflowTransition
from .serializers import (
    BoardConfigSerializer,
    IssueTypeSerializer,
    WorkflowTransitionSerializer,
    status_issue_counts,
)


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


class BoardStatusDetailView(APIView):
    """DELETE /api/boards/<id>/statuses/<status_id>/ — remove a workflow status that nothing
    uses any more (no issues in it, not on any of the project's board columns). Board settings
    list such statuses as "unused" after a column is removed."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, status_id):
        board = get_object_or_404(Board.objects.select_related("project__workflow"), pk=pk)
        if not _can_configure_board(request.user, board):
            raise PermissionDenied("Only a project admin/lead or workspace admin can configure this board.")
        workflow = board.project.workflow
        wf_status = get_object_or_404(WorkflowStatus, pk=status_id, workflow=workflow)

        issue_count = status_issue_counts(workflow).get(wf_status.id, 0)
        if issue_count:
            return Response(
                {"detail": f"{issue_count} job(s) are in '{wf_status.name}'. Move them to another status first."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        for project_board in board.project.boards.all():
            for col in project_board.column_config:
                if wf_status.id in (col.get("status_ids") or []):
                    return Response(
                        {"detail": f"'{wf_status.name}' is still on the '{col['name']}' column. Remove it there first."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
        if workflow.statuses.count() <= 1:
            return Response({"detail": "A workflow needs at least one status."}, status=status.HTTP_400_BAD_REQUEST)
        wf_status.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


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
