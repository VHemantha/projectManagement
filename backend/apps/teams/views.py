from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, viewsets

from .models import Team, TeamMembership
from .serializers import TeamDetailSerializer, TeamListSerializer, TeamMembershipSerializer


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.annotate(member_count=Count("memberships")).order_by("name")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return TeamListSerializer
        return TeamDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("memberships__user")
        return qs


class TeamMembershipListCreateView(generics.ListCreateAPIView):
    serializer_class = TeamMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_team(self):
        return get_object_or_404(Team, pk=self.kwargs["team_id"])

    def get_queryset(self):
        return TeamMembership.objects.filter(team=self.get_team()).select_related("user")

    def perform_create(self, serializer):
        serializer.save(team=self.get_team())


class TeamMembershipDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = TeamMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TeamMembership.objects.filter(team_id=self.kwargs["team_id"])
