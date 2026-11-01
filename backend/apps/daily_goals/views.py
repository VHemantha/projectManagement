from datetime import date as date_cls, timedelta

from django.db.models import Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.teams.leads import leads, led_people
from apps.teams.models import Team, TeamMembership

from .models import DailyGoal
from .serializers import DailyGoalSerializer


GOAL_RELATED = ("user", "checked_by", "linked_issue__status", "linked_issue__issue_type", "linked_issue__assignee",
                "linked_issue__project__client")


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
        qs = DailyGoal.objects.select_related(*GOAL_RELATED)
        user_id = self.request.query_params.get("user")
        if user_id and int(user_id) != self.request.user.id:
            person = get_object_or_404(DailyGoal.user.field.related_model, pk=user_id)
            if not leads(self.request.user, person):
                raise PermissionDenied("You can only view your own goals unless you lead one of this person's workspaces.")
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
        planned_hours=goal.planned_hours, complete_by=goal.complete_by,
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
            raise PermissionDenied("Only a lead of this workspace (or an admin) can view its goals rollup.")

        member_ids = TeamMembership.objects.filter(team=team).values_list("user_id", flat=True)
        qs = DailyGoal.objects.filter(user_id__in=member_ids).select_related(*GOAL_RELATED)
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


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def check_goal(request, pk=None):
    """POST {"result": "confirmed" | "not_done" | ""}: the team lead's check of a plan's result.
    Only someone who leads the person (or an admin) may; nobody checks their own plan."""
    goal = get_object_or_404(DailyGoal.objects.select_related(*GOAL_RELATED), pk=pk)
    if not leads(request.user, goal.user):
        raise PermissionDenied("Only the person's team lead (or an admin) can check their plan.")
    result = request.data.get("result", "")
    if result not in DailyGoal.LeadCheck.values:
        raise ValidationError({"result": "Send confirmed, not_done, or an empty value to clear the check."})
    goal.lead_check = result
    goal.checked_by = request.user if result else None
    goal.checked_at = timezone.now() if result else None
    goal.save(update_fields=["lead_check", "checked_by", "checked_at", "updated_at"])
    return Response(DailyGoalSerializer(goal).data)


class TeamPlansView(APIView):
    """GET /api/daily-goals/team/?date= : the morning plans of everyone the user leads (everyone,
    for an admin or the CEO), each with the hours planned, the hours their timesheet shows for the
    day, and what is done and not (AFIT, 1 Nov 2026)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        from apps.timesheets.models import TimeEntry

        try:
            day = date_cls.fromisoformat(request.query_params.get("date") or timezone.localdate().isoformat())
        except ValueError:
            raise ValidationError({"date": "Use YYYY-MM-DD."})
        people = list(led_people(request.user))
        goals = DailyGoal.objects.filter(user__in=people, date=day).select_related(*GOAL_RELATED)
        by_person: dict[int, list] = {}
        for g in goals:
            by_person.setdefault(g.user_id, []).append(g)
        logged = {
            r["user_id"]: r["t"].total_seconds() / 3600
            for r in TimeEntry.objects.filter(user__in=people, work_date=day, duration__isnull=False)
            .values("user_id").annotate(t=Sum("duration"))
        }
        rows = []
        for p in people:
            mine = by_person.get(p.id, [])
            rows.append({
                "person": UserSerializer(p).data,
                "goals": DailyGoalSerializer(mine, many=True).data,
                "planned_hours": round(sum(g.planned_hours or 0 for g in mine), 2),
                "logged_hours": round(logged.get(p.id, 0), 2),
                "achieved": sum(1 for g in mine if g.status == DailyGoal.Status.ACHIEVED and g.lead_check != DailyGoal.LeadCheck.NOT_DONE),
                "not_achieved": sum(1 for g in mine if g.status in (DailyGoal.Status.NOT_ACHIEVED, DailyGoal.Status.CARRIED_OVER)
                                    or g.lead_check == DailyGoal.LeadCheck.NOT_DONE),
                "unchecked": sum(1 for g in mine if g.status == DailyGoal.Status.ACHIEVED and not g.lead_check),
            })
        rows.sort(key=lambda r: (not r["goals"], r["person"]["display_name"]))
        return Response({"date": day, "people": rows})
