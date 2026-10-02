from django.db.models import Count, Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.issues.models import Issue
from apps.issues.serializers import IssueMiniSerializer
from apps.projects.models import Project
from apps.projects.serializers import ProjectListSerializer

from .models import Filter
from .serializers import FilterSerializer


class FilterViewSet(viewsets.ModelViewSet):
    serializer_class = FilterSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return Filter.objects.filter(Q(owner=user) | Q(is_public=True)).distinct().order_by("name")

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # Public filters are visible to everyone but only their owner may change or delete them.
    def perform_update(self, serializer):
        if serializer.instance.owner_id != self.request.user.id:
            raise PermissionDenied("Only the filter's owner can change it.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied("Only the filter's owner can delete it.")
        instance.delete()


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def quick_search(request):
    q = request.query_params.get("q", "").strip()
    if not q:
        return Response({"issues": [], "projects": []})

    issues = Issue.objects.filter(Q(key__iexact=q) | Q(summary__icontains=q)).select_related(
        "issue_type", "status", "assignee", "project"
    )[:8]
    projects = Project.objects.filter(Q(key__icontains=q) | Q(name__icontains=q)).annotate(
        issue_count=Count("issues")
    )[:5]

    return Response(
        {
            "issues": IssueMiniSerializer(issues, many=True).data,
            "projects": ProjectListSerializer(projects, many=True).data,
        }
    )
