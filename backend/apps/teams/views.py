from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, viewsets
from rest_framework.exceptions import PermissionDenied

from .models import Team, TeamMembership
from .serializers import TeamDetailSerializer, TeamListSerializer, TeamMembershipSerializer


class TeamViewSet(viewsets.ModelViewSet):
    queryset = Team.objects.annotate(member_count=Count("memberships")).select_related("parent").order_by("name")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "list":
            return TeamListSerializer
        return TeamDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("memberships__user", "sub_teams")
        return qs

    def perform_destroy(self, instance):
        # Deleting a team also deletes its memberships and its team chat channel (with all of
        # its messages); projects and sub-teams survive with their team link cleared. That is
        # too destructive for any member, so only staff and the team's own leads may do it.
        user = self.request.user
        is_lead = instance.memberships.filter(user=user, role=TeamMembership.Role.LEAD).exists()
        if not (user.is_staff or is_lead):
            raise PermissionDenied("Only a team lead or an admin can delete this team.")
        instance.delete()


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
