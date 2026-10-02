from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.workflow.serializers import BoardSerializer
from apps.workflow.services import provision_project_defaults

from .keys import get_project_or_404
from .models import Component, Label, Project, ProjectMembership, Version
from .permissions import can_manage_project
from .serializers import (
    ComponentSerializer,
    LabelSerializer,
    ProjectDetailSerializer,
    ProjectListSerializer,
    ProjectMembershipSerializer,
    VersionSerializer,
)


class ProjectViewSet(viewsets.ModelViewSet):
    queryset = Project.objects.select_related("lead").annotate(issue_count=Count("issues")).order_by("key")
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "key"
    lookup_value_regex = "[A-Za-z0-9]+"
    filterset_fields = ["project_type", "is_archived"]
    search_fields = ["key", "name"]
    ordering_fields = ["key", "name", "created_at", "updated_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return ProjectListSerializer
        return ProjectDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("memberships__user", "labels", "components", "versions")
        return qs

    def get_object(self):
        # Keys match ignoring case, and an old key (after a rename) still finds the project;
        # the response carries the current key so the client can update its URL.
        project = get_project_or_404(self.kwargs["key"])
        obj = get_object_or_404(self.get_queryset(), pk=project.pk)
        self.check_object_permissions(self.request, obj)
        return obj

    def perform_create(self, serializer):
        project = serializer.save()
        provision_project_defaults(project)

    @action(detail=True, methods=["get"])
    def board(self, request, key=None):
        project = self.get_object()
        board = project.boards.first()
        if not board:
            return Response({"detail": "No board configured for this workspace."}, status=404)
        return Response(BoardSerializer(board).data)


class ProjectMembershipListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_project_or_404(self.kwargs["project_key"])

    def get_queryset(self):
        return ProjectMembership.objects.filter(project=self.get_project()).select_related("user")

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())


class ProjectMembershipDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ProjectMembership.objects.filter(project=get_project_or_404(self.kwargs["project_key"]))


class ProjectLookupListMixin:
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_project_or_404(self.kwargs["project_key"])


class LabelListCreateView(ProjectLookupListMixin, generics.ListCreateAPIView):
    serializer_class = LabelSerializer

    def get_queryset(self):
        return Label.objects.filter(project=self.get_project())

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "project": self.get_project()}

    def perform_create(self, serializer):
        project = self.get_project()
        if not can_manage_project(self.request.user, project):
            raise PermissionDenied("Only the workspace lead, a workspace admin or an organisation admin can add labels.")
        serializer.save(project=project)


class LabelDetailView(ProjectLookupListMixin, generics.RetrieveUpdateAPIView):
    """PATCH /api/projects/<key>/labels/<id>/ — rename or recolour a label. It changes the label
    on every job that has it, so only workspace managers may do it."""

    serializer_class = LabelSerializer

    def get_queryset(self):
        return Label.objects.filter(project=self.get_project())

    def perform_update(self, serializer):
        if not can_manage_project(self.request.user, serializer.instance.project):
            raise PermissionDenied("Only the workspace lead, a workspace admin or an organisation admin can change labels.")
        serializer.save()


class ComponentListCreateView(ProjectLookupListMixin, generics.ListCreateAPIView):
    serializer_class = ComponentSerializer

    def get_queryset(self):
        return Component.objects.filter(project=self.get_project())

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())


class VersionListCreateView(ProjectLookupListMixin, generics.ListCreateAPIView):
    serializer_class = VersionSerializer

    def get_queryset(self):
        return Version.objects.filter(project=self.get_project())

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())
