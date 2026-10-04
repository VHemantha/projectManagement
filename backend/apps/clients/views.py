from rest_framework import generics, permissions

from .models import Client
from .serializers import ClientSerializer


class ClientListCreateView(generics.ListCreateAPIView):
    """Sub-workspaces. ?team=<id> lists one workspace's; ?team=none those not in a workspace."""

    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        qs = Client.objects.select_related("team")
        team = self.request.query_params.get("team")
        if team == "none":
            qs = qs.filter(team__isnull=True)
        elif team:
            qs = qs.filter(team_id=team)
        return qs

    def perform_create(self, serializer):
        from apps.orgs.models import Organization

        serializer.save(organization=Organization.get_solo())


class ClientDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = ClientSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Client.objects.all()
