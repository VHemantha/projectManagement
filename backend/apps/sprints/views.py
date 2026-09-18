from datetime import timedelta

from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.issues.models import Issue
from apps.projects.models import Project

from .models import Sprint
from .serializers import SprintCompleteSerializer, SprintSerializer, SprintStartSerializer


class SprintListCreateView(generics.ListCreateAPIView):
    serializer_class = SprintSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_project(self):
        return get_object_or_404(Project, key__iexact=self.kwargs["project_key"])

    def get_queryset(self):
        return (
            Sprint.objects.filter(project=self.get_project())
            .annotate(issue_count=Count("issues"))
            .order_by("order")
        )

    def perform_create(self, serializer):
        project = self.get_project()
        last_order = Sprint.objects.filter(project=project).count()
        serializer.save(project=project, order=last_order)


class SprintDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = SprintSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = Sprint.objects.annotate(issue_count=Count("issues"))


class SprintStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        sprint = get_object_or_404(Sprint, pk=pk)
        if sprint.state != Sprint.State.FUTURE:
            return Response({"detail": "Only a future sprint can be started."}, status=400)
        if Sprint.objects.filter(project=sprint.project, state=Sprint.State.ACTIVE).exists():
            return Response({"detail": "This project already has an active sprint."}, status=400)

        serializer = SprintStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        sprint.start_date = serializer.validated_data["start_date"]
        sprint.end_date = serializer.validated_data["end_date"]
        sprint.goal = serializer.validated_data.get("goal", sprint.goal)
        sprint.state = Sprint.State.ACTIVE
        sprint.save()
        return Response(SprintSerializer(sprint).data)


class SprintCompleteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk=None):
        sprint = get_object_or_404(Sprint, pk=pk)
        if sprint.state != Sprint.State.ACTIVE:
            return Response({"detail": "Only an active sprint can be completed."}, status=400)

        serializer = SprintCompleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        move_to = serializer.validated_data.get("move_to", "backlog")

        incomplete = Issue.objects.filter(sprint=sprint).exclude(status__category="done")
        if move_to == "backlog":
            incomplete.update(sprint=None)
        else:
            target = get_object_or_404(Sprint, pk=move_to, project=sprint.project)
            incomplete.update(sprint=target)

        sprint.state = Sprint.State.CLOSED
        sprint.completed_at = timezone.now()
        sprint.save()
        return Response(SprintSerializer(sprint).data)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def sprint_burndown(request, pk=None):
    """Simplified burndown: total scope is this sprint's current story-point sum
    (issues moved out after the fact aren't retroactively tracked — there's no
    daily snapshot table), remaining is scope minus points resolved by each day."""
    sprint = get_object_or_404(Sprint, pk=pk)
    if not sprint.start_date or not sprint.end_date:
        return Response({"detail": "Sprint has no start/end date yet."}, status=400)

    issues = list(Issue.objects.filter(sprint=sprint))
    total_points = sum(i.story_points or 0 for i in issues)

    end = sprint.end_date
    if sprint.state == Sprint.State.ACTIVE:
        end = min(end, timezone.now().date())

    num_days = (sprint.end_date - sprint.start_date).days + 1
    dates, ideal, remaining = [], [], []
    for day_offset in range(num_days):
        day = sprint.start_date + timedelta(days=day_offset)
        dates.append(day.isoformat())
        ideal.append(round(total_points * (1 - day_offset / max(num_days - 1, 1)), 1))
        if day <= end:
            resolved_by_day = sum(
                i.story_points or 0
                for i in issues
                if i.resolved_at and i.resolved_at.date() <= day
            )
            remaining.append(round(total_points - resolved_by_day, 1))
        else:
            remaining.append(None)

    return Response({"dates": dates, "ideal": ideal, "remaining": remaining, "total_points": total_points})


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def velocity(request, project_key=None):
    project = get_object_or_404(Project, key__iexact=project_key)
    closed_sprints = Sprint.objects.filter(project=project, state=Sprint.State.CLOSED).order_by("-completed_at")[:6]

    rows = []
    for sprint in reversed(closed_sprints):
        issues = list(Issue.objects.filter(sprint=sprint))
        committed = sum(i.story_points or 0 for i in issues)
        completed = sum(i.story_points or 0 for i in issues if i.status.category == "done")
        rows.append({"sprint": sprint.name, "committed": committed, "completed": completed})

    return Response(rows)


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def reorder_sprints(request, project_key=None):
    """Persist a new backlog-section order after drag-reordering sprint groups."""
    order = request.data.get("order", [])
    project = get_object_or_404(Project, key__iexact=project_key)
    sprints = {s.id: s for s in Sprint.objects.filter(project=project)}
    updated = []
    for index, sprint_id in enumerate(order):
        sprint = sprints.get(sprint_id)
        if sprint:
            sprint.order = index
            updated.append(sprint)
    Sprint.objects.bulk_update(updated, ["order"])
    return Response(status=status.HTTP_204_NO_CONTENT)
