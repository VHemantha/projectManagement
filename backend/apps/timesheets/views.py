import csv

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.projects.models import Project

from .filters import TimeEntryFilter
from .models import BillableRate, TimeEntry, Timesheet
from .serializers import BillableRateSerializer, TimeEntrySerializer, TimesheetSerializer


def _can_approve(user, timesheet: Timesheet) -> bool:
    """A workspace admin, or the lead of at least one project the timesheet's entries
    touch, can approve/reject it — there's no reporting-line concept on User, so this
    mirrors how Jira/ClickUp fall back to project-lead approval by default."""
    if user.is_staff:
        return True
    project_ids = TimeEntry.objects.filter(
        user=timesheet.user, work_date__gte=timesheet.period_start, work_date__lte=timesheet.period_end
    ).values_list("project_id", flat=True)
    return Project.objects.filter(id__in=project_ids, lead=user).exists()


class TimeEntryViewSet(viewsets.ModelViewSet):
    serializer_class = TimeEntrySerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_class = TimeEntryFilter
    queryset = TimeEntry.objects.select_related("user", "issue", "project").prefetch_related("tags")

    def get_queryset(self):
        qs = super().get_queryset()
        # Anyone can query time entries for reporting (project summary, team hours,
        # workload pages), but write actions are restricted to the entry's own owner
        # (enforced below in perform_update/destroy and the start/stop actions).
        return qs.order_by("-work_date", "-started_at")

    def perform_create(self, serializer):
        serializer.save()

    def perform_update(self, serializer):
        if serializer.instance.user_id != self.request.user.id:
            raise PermissionDenied("You can only edit your own time entries.")
        serializer.save()

    def perform_destroy(self, instance):
        if instance.user_id != self.request.user.id:
            raise PermissionDenied("You can only delete your own time entries.")
        if instance.locked:
            raise ValidationError("This entry is locked (part of a submitted timesheet).")
        instance.delete()

    @action(detail=False, methods=["post"])
    def start(self, request):
        issue_id = request.data.get("issue_id")
        issue = None
        if issue_id:
            from apps.issues.models import Issue

            issue = get_object_or_404(Issue, id=issue_id)

        # Only one running timer per user: auto-stop/save whatever else is running.
        running = TimeEntry.objects.filter(user=request.user, is_running=True).first()
        if running:
            _stop_entry(running)

        entry = TimeEntry.objects.create(
            user=request.user,
            issue=issue,
            project=issue.project if issue else None,
            started_at=timezone.now(),
            is_running=True,
            created_via=TimeEntry.CreatedVia.TIMER,
            work_date=timezone.now().date(),
        )
        return Response(TimeEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def stop(self, request, pk=None):
        entry = get_object_or_404(TimeEntry, pk=pk)
        if entry.user_id != request.user.id:
            raise PermissionDenied("You can only stop your own timer.")
        if not entry.is_running:
            return Response(TimeEntrySerializer(entry).data)
        _stop_entry(entry)
        return Response(TimeEntrySerializer(entry).data)

    @action(detail=False, methods=["get"])
    def running(self, request):
        entry = TimeEntry.objects.filter(user=request.user, is_running=True).select_related("issue", "project").first()
        if not entry:
            return Response(None)
        return Response(TimeEntrySerializer(entry).data)


def _stop_entry(entry: TimeEntry):
    entry.ended_at = timezone.now()
    entry.duration = entry.ended_at - entry.started_at
    entry.is_running = False
    entry.save(update_fields=["ended_at", "duration", "is_running"])


class TimesheetViewSet(viewsets.ModelViewSet):
    serializer_class = TimesheetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = Timesheet.objects.select_related("user", "reviewed_by")
        if self.request.query_params.get("inbox") == "true":
            # "Timesheets to review": submitted sheets this user can approve.
            submitted = qs.filter(status=Timesheet.Status.SUBMITTED)
            return [t for t in submitted if _can_approve(self.request.user, t)]
        return qs.filter(user=self.request.user).order_by("-period_start")

    def create(self, request, *args, **kwargs):
        # Idempotent "get or create the timesheet for this week" — the frontend calls this
        # on every grid view, and period_start+user is unique, so a second call for the
        # same week should return the existing sheet rather than 400 on the constraint.
        existing = Timesheet.objects.filter(
            user=request.user, period_start=request.data.get("period_start")
        ).first()
        if existing:
            return Response(TimesheetSerializer(existing).data)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        timesheet = get_object_or_404(Timesheet, pk=pk)
        if timesheet.user_id != request.user.id:
            raise PermissionDenied("You can only submit your own timesheet.")
        if timesheet.status not in (Timesheet.Status.DRAFT, Timesheet.Status.REJECTED):
            return Response({"detail": "Only a draft or rejected timesheet can be submitted."}, status=400)

        entries = TimeEntry.objects.filter(
            user=timesheet.user, work_date__gte=timesheet.period_start, work_date__lte=timesheet.period_end
        )
        entries.update(locked=True)
        timesheet.status = Timesheet.Status.SUBMITTED
        timesheet.submitted_at = timezone.now()
        timesheet.reviewer_note = ""
        timesheet.save(update_fields=["status", "submitted_at", "reviewer_note"])

        project_ids = entries.values_list("project_id", flat=True)
        leads = {p.lead for p in Project.objects.filter(id__in=project_ids) if p.lead}
        for lead in leads:
            notify(lead, Notification.Verb.WATCHING_UPDATED, actor=request.user, target_issue=None)

        return Response(TimesheetSerializer(timesheet).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        timesheet = get_object_or_404(Timesheet, pk=pk)
        if not _can_approve(request.user, timesheet):
            raise PermissionDenied("Only a workspace admin or one of this period's project leads can approve.")
        if timesheet.status != Timesheet.Status.SUBMITTED:
            return Response({"detail": "Only a submitted timesheet can be approved."}, status=400)

        timesheet.status = Timesheet.Status.APPROVED
        timesheet.reviewed_by = request.user
        timesheet.reviewed_at = timezone.now()
        timesheet.save(update_fields=["status", "reviewed_by", "reviewed_at"])
        notify(timesheet.user, Notification.Verb.WATCHING_UPDATED, actor=request.user, target_issue=None)
        return Response(TimesheetSerializer(timesheet).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        timesheet = get_object_or_404(Timesheet, pk=pk)
        if not _can_approve(request.user, timesheet):
            raise PermissionDenied("Only a workspace admin or one of this period's project leads can reject.")
        if timesheet.status != Timesheet.Status.SUBMITTED:
            return Response({"detail": "Only a submitted timesheet can be rejected."}, status=400)
        note = request.data.get("note", "").strip()
        if not note:
            raise ValidationError("A note is required when rejecting a timesheet.")

        entries = TimeEntry.objects.filter(
            user=timesheet.user, work_date__gte=timesheet.period_start, work_date__lte=timesheet.period_end
        )
        entries.update(locked=False)
        timesheet.status = Timesheet.Status.REJECTED
        timesheet.reviewed_by = request.user
        timesheet.reviewed_at = timezone.now()
        timesheet.reviewer_note = note
        timesheet.save(update_fields=["status", "reviewed_by", "reviewed_at", "reviewer_note"])
        notify(timesheet.user, Notification.Verb.WATCHING_UPDATED, actor=request.user, target_issue=None)
        return Response(TimesheetSerializer(timesheet).data)


class BillableRateListView(generics.ListAPIView):
    serializer_class = BillableRateSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    queryset = BillableRate.objects.all()


class TimeReportCsvView(APIView):
    """Streams the same filtered time-entry set the Time Reports page shows, as CSV.
    Reuses TimeEntryFilter so the export always matches the on-screen filters exactly."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = TimeEntry.objects.select_related("user", "issue", "project").order_by("-work_date", "-started_at")
        qs = TimeEntryFilter(request.query_params, queryset=qs).qs

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="time-report.csv"'
        writer = csv.writer(response)
        writer.writerow(
            ["Date", "User", "Project", "Issue", "Description", "Hours", "Billable", "Created via"]
        )
        for entry in qs:
            writer.writerow(
                [
                    entry.work_date.isoformat(),
                    entry.user.display_name,
                    entry.project.key if entry.project else "",
                    entry.issue.key if entry.issue else "",
                    entry.description,
                    round(entry.duration.total_seconds() / 3600, 2) if entry.duration else 0,
                    "Yes" if entry.is_billable else "No",
                    entry.created_via,
                ]
            )
        return response
