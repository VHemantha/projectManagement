from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.live.broadcast import notify
from apps.projects.permissions import can_manage_project
from trackflow.naming import clean_name

from .models import Board, IssueType, Workflow, WorkflowStatus, WorkflowTransition
from .serializers import (
    BoardConfigSerializer,
    IssueTypeSerializer,
    STATUS_NAME_MAX,
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
    """No dedicated BoardMembership model: whoever manages the workspace configures its board."""
    return can_manage_project(user, board.project)


class BoardConfigView(generics.RetrieveUpdateAPIView):
    """GET/PATCH /api/boards/<id>/config/ — columns, swimlane mode, card fields, color rule."""

    serializer_class = BoardConfigSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Board.objects.select_related("project", "project__workflow")

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in permissions.SAFE_METHODS and not _can_configure_board(request.user, obj):
            raise PermissionDenied("Only a project admin/lead or an organisation admin can configure this board.")


class BoardStatusDetailView(APIView):
    """DELETE /api/boards/<id>/statuses/<status_id>/ — remove a workflow status that nothing
    uses any more (no issues in it, not on any of the project's board columns). Board settings
    list such statuses as "unused" after a column is removed."""

    permission_classes = [permissions.IsAuthenticated]

    def delete(self, request, pk, status_id):
        board = get_object_or_404(Board.objects.select_related("project__workflow"), pk=pk)
        if not _can_configure_board(request.user, board):
            raise PermissionDenied("Only a project admin/lead or an organisation admin can configure this board.")
        workflow = board.project.workflow
        wf_status = get_object_or_404(WorkflowStatus, pk=status_id, workflow=workflow)

        issue_count = status_issue_counts(workflow).get(wf_status.id, 0)
        if issue_count:
            return Response(
                {"detail": f"{issue_count} task(s) are in '{wf_status.name}'. Move them to another status first."},
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


class BoardColumnView(APIView):
    """PATCH /api/boards/<id>/columns/<index>/ {"name": ...} — rename one column in place.

    Column names are unique on a board (ignoring case). When the column holds a single status
    that carries the column's old name, that status is renamed too, so cards, status pickers
    and filters show the new name."""

    permission_classes = [permissions.IsAuthenticated]

    @transaction.atomic
    def patch(self, request, pk, index):
        board = get_object_or_404(Board.objects.select_for_update().select_related("project__workflow"), pk=pk)
        if not _can_configure_board(request.user, board):
            raise PermissionDenied("Only a project admin/lead or an organisation admin can configure this board.")
        columns = list(board.column_config or [])
        if not 0 <= index < len(columns):
            return Response({"detail": "No such column."}, status=status.HTTP_404_NOT_FOUND)
        try:
            name = clean_name(request.data.get("name"), max_length=STATUS_NAME_MAX, what="Column name")
        except ValidationError as exc:
            return Response({"name": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        column = dict(columns[index])
        old_name = column.get("name", "")
        if any(i != index and str(c.get("name", "")).lower() == name.lower() for i, c in enumerate(columns)):
            return Response({"name": [f"This board already has a column called '{name}'."]}, status=status.HTTP_400_BAD_REQUEST)

        workflow = board.project.workflow
        status_ids = column.get("status_ids") or []
        renamed_status = None
        if len(status_ids) == 1:
            wf_status = WorkflowStatus.objects.filter(pk=status_ids[0], workflow=workflow).first()
            if wf_status and wf_status.name.lower() == str(old_name).lower() and wf_status.name != name:
                if workflow.statuses.exclude(pk=wf_status.pk).filter(name__iexact=name).exists():
                    return Response(
                        {"name": [f"A status called '{name}' already exists in this project."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                wf_status.name = name
                wf_status.save(update_fields=["name"])
                renamed_status = wf_status

        column["name"] = name
        columns[index] = column
        board.column_config = columns
        board.save(update_fields=["column_config"])
        if renamed_status is not None:
            notify("issues", project=board.project.key)  # cards and job lists show status names
        return Response(BoardConfigSerializer(board).data)


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
        if not can_manage_project(request.user, obj.workflow.project):
            raise PermissionDenied("Only a project admin/lead or an organisation admin can edit transition rules.")
