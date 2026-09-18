from rest_framework import generics, permissions

from .models import IssueType
from .serializers import IssueTypeSerializer


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
