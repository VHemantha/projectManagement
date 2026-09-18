from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.workflow.serializers import BoardSerializer
from apps.workflow.services import provision_project_defaults

from .models import Component, Label, Project, ProjectMembership, Version
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

    def perform_create(self, serializer):
        project = serializer.save()
        provision_project_defaults(project)

    @action(detail=True, methods=["get"])
    def board(self, request, key=None):
        project = self.get_object()
        board = project.boards.first()
        if not board:
            return Response({"detail": "No board configured for this project."}, status=404)
        return Response(BoardSerializer(board).data)


class ProjectMembershipListCreateView(generics.ListCreateAPIView):
    serializer_class = ProjectMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_object_or_404(Project, key=self.kwargs["project_key"].upper())

    def get_queryset(self):
        return ProjectMembership.objects.filter(project=self.get_project()).select_related("user")

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())


class ProjectMembershipDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ProjectMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return ProjectMembership.objects.filter(project__key=self.kwargs["project_key"].upper())


class ProjectLookupListMixin:
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_object_or_404(Project, key=self.kwargs["project_key"].upper())


class LabelListCreateView(ProjectLookupListMixin, generics.ListCreateAPIView):
    serializer_class = LabelSerializer

    def get_queryset(self):
        return Label.objects.filter(project=self.get_project())

    def perform_create(self, serializer):
        serializer.save(project=self.get_project())


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
