from datetime import timedelta

from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import User

from apps.accounts.serializers import UserSerializer
from apps.issues.models import Issue
from apps.issues.serializers import IssueMiniSerializer

from .models import BillableRate, TimeEntry, TimeEntryTag, Timesheet


class TimeEntryTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = TimeEntryTag
        fields = ["id", "name", "color"]


class TimeEntrySerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    # Logging for someone else (a tick in the Log time form): who the time is for. Only a lead of
    # one of the person's workspaces, or an organisation admin, may (AFIT, 1 Nov 2026).
    user_id = serializers.PrimaryKeyRelatedField(
        source="for_user", queryset=User.objects.filter(is_active=True, is_agent=False), write_only=True, required=False,
    )
    logged_by = UserSerializer(read_only=True)
    issue = IssueMiniSerializer(read_only=True)
    issue_id = serializers.PrimaryKeyRelatedField(
        source="issue", queryset=Issue.objects.all(), write_only=True, required=False, allow_null=True,
    )
    project_key = serializers.CharField(source="project.key", read_only=True, default=None)
    tags = TimeEntryTagSerializer(many=True, read_only=True)
    tag_ids = serializers.PrimaryKeyRelatedField(
        source="tags", queryset=TimeEntryTag.objects.all(), many=True, write_only=True, required=False
    )
    duration_seconds = serializers.SerializerMethodField()
    # Write-only counterpart of duration_seconds: a plain DurationField can't parse a bare
    # integer of seconds from JSON, so manual entries send this instead and it's converted
    # to `duration` here.
    duration_seconds_input = serializers.IntegerField(write_only=True, required=False, min_value=0)

    class Meta:
        model = TimeEntry
        fields = [
            "id",
            "user",
            "user_id",
            "logged_by",
            "issue",
            "issue_id",
            "project",
            "project_key",
            "description",
            "started_at",
            "ended_at",
            "duration_seconds",
            "duration_seconds_input",
            "is_billable",
            "is_running",
            "tags",
            "tag_ids",
            "created_via",
            "locked",
            "work_date",
            "created_at",
        ]
        read_only_fields = ["user", "project", "is_running", "locked", "created_via", "started_at", "ended_at"]

    def get_duration_seconds(self, obj):
        if obj.is_running and obj.started_at:
            return int((timezone.now() - obj.started_at).total_seconds())
        if obj.duration:
            return int(obj.duration.total_seconds())
        return 0

    def validate(self, attrs):
        if self.instance and self.instance.locked:
            raise serializers.ValidationError("This entry is locked (part of a submitted timesheet).")
        return attrs

    def _pop_duration(self, validated_data):
        seconds = validated_data.pop("duration_seconds_input", None)
        if seconds is not None:
            validated_data["duration"] = timedelta(seconds=seconds)

    def create(self, validated_data):
        request = self.context["request"]
        self._pop_duration(validated_data)
        person = validated_data.pop("for_user", None) or request.user
        validated_data.setdefault("work_date", timezone.now().date())
        if person.id != request.user.id:
            from apps.teams.leads import leads

            if not leads(request.user, person):
                raise PermissionDenied("You can log time for someone else only if you lead one of their workspaces.")
            closed = Timesheet.objects.filter(
                user=person, period_start__lte=validated_data["work_date"], period_end__gte=validated_data["work_date"],
                status__in=[Timesheet.Status.SUBMITTED, Timesheet.Status.APPROVED],
            ).exists()
            if closed:
                raise serializers.ValidationError(
                    {"work_date": f"{person.display_name}'s timesheet for that week is already submitted."}
                )
            validated_data["logged_by"] = request.user
        validated_data["user"] = person
        validated_data.setdefault("created_via", TimeEntry.CreatedVia.MANUAL)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        validated_data.pop("for_user", None)  # an entry stays with the person it is for
        self._pop_duration(validated_data)
        return super().update(instance, validated_data)


class TimesheetSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    reviewed_by = UserSerializer(read_only=True)
    total_hours = serializers.SerializerMethodField()

    class Meta:
        model = Timesheet
        fields = [
            "id",
            "user",
            "period_start",
            "period_end",
            "status",
            "submitted_at",
            "reviewed_by",
            "reviewed_at",
            "reviewer_note",
            "total_hours",
        ]
        read_only_fields = ["status", "submitted_at", "reviewed_by", "reviewed_at"]

    def get_total_hours(self, obj):
        entries = TimeEntry.objects.filter(
            user=obj.user, work_date__gte=obj.period_start, work_date__lte=obj.period_end
        )
        total = sum((e.duration.total_seconds() if e.duration else 0) for e in entries)
        return round(total / 3600, 2)


class BillableRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillableRate
        fields = ["id", "scope", "project", "user", "hourly_rate", "currency"]
