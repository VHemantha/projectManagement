from datetime import timedelta

from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.teams.models import Team, TeamMembership

from .models import DailyGoal
from .serializers import DailyGoalSerializer


def _can_view_team_goals(user, team: Team) -> bool:
    """Same reasoning as timesheets' _can_approve, applied to the team-lead concept used
    elsewhere (TeamMembership.role == 'lead') rather than Project.lead — there's no single
    canonical org-wide 'manager' field, so each addendum's rollup reuses whichever lead
    concept already exists for the resource it's rolling up."""
    if user.is_staff:
        return True
    return TeamMembership.objects.filter(team=team, user=user, role=TeamMembership.Role.LEAD).exists()


class DailyGoalListCreateView(generics.ListCreateAPIView):
    serializer_class = DailyGoalSerializer
    permission_classes = [permissions.IsAuthenticated]
    # Goal lists are always small (one day, or one team-day at most) — no pagination needed,
    # matching the same call made for ChannelMembersView/BillableRateListView/etc.
    pagination_class = None

    def get_queryset(self):
        qs = DailyGoal.objects.select_related("user", "linked_issue")
        user_id = self.request.query_params.get("user")
        if user_id and int(user_id) != self.request.user.id:
            target_user_teams = TeamMembership.objects.filter(user_id=user_id).values_list("team_id", flat=True)
            allowed = self.request.user.is_staff or TeamMembership.objects.filter(
                team_id__in=target_user_teams, user=self.request.user, role=TeamMembership.Role.LEAD
            ).exists()
            if not allowed:
                raise PermissionDenied("You can only view your own goals unless you lead one of this person's teams.")
            qs = qs.filter(user_id=user_id)
        else:
            qs = qs.filter(user=self.request.user)
        date = self.request.query_params.get("date")
        if date:
            qs = qs.filter(date=date)
        date_from = self.request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        date_to = self.request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return qs

    def perform_create(self, serializer):
        max_order = DailyGoal.objects.filter(
            user=self.request.user, date=serializer.validated_data.get("date")
        ).count()
        serializer.save(user=self.request.user, order=max_order)


class DailyGoalDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = DailyGoalSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = DailyGoal.objects.all()

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if obj.user_id != request.user.id:
            raise PermissionDenied("You can only edit your own goals.")


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def carry_over_goal(request, pk=None):
    goal = get_object_or_404(DailyGoal, pk=pk)
    if goal.user_id != request.user.id:
        raise PermissionDenied("You can only carry over your own goals.")
    if goal.status not in (DailyGoal.Status.NOT_ACHIEVED, DailyGoal.Status.PLANNED, DailyGoal.Status.IN_PROGRESS):
        raise ValidationError("Only a not-yet-achieved goal can be carried over.")

    next_date = goal.date + timedelta(days=1)
    max_order = DailyGoal.objects.filter(user=goal.user, date=next_date).count()
    carried = DailyGoal.objects.create(
        user=goal.user, date=next_date, text=goal.text, linked_issue=goal.linked_issue,
        status=DailyGoal.Status.PLANNED, order=max_order, carried_over_from=goal,
    )
    if goal.status != DailyGoal.Status.NOT_ACHIEVED:
        goal.status = DailyGoal.Status.CARRIED_OVER
        goal.save(update_fields=["status"])
    return Response(DailyGoalSerializer(carried).data, status=201)


class TeamDailyGoalsView(APIView):
    """GET /api/teams/<id>/daily-goals/?date= — the team-leader rollup: every member's goals
    for a date, permission-checked server-side (not just hidden in the UI) via
    _can_view_team_goals."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, team_id=None):
        team = get_object_or_404(Team, pk=team_id)
        if not _can_view_team_goals(request.user, team):
            raise PermissionDenied("Only a lead of this team (or a workspace admin) can view its goals rollup.")

        member_ids = TeamMembership.objects.filter(team=team).values_list("user_id", flat=True)
        qs = DailyGoal.objects.filter(user_id__in=member_ids).select_related("user", "linked_issue")
        date = request.query_params.get("date")
        if date:
            qs = qs.filter(date=date)
        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return Response(DailyGoalSerializer(qs, many=True).data)
