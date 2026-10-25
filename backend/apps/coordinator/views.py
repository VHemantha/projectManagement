"""The coordination agent's API. Anyone may open their own conversation with the agent and manage
their own leave; everything that controls the agent is the CEO's alone (refusals are logged)."""
from datetime import date

from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from . import policies, services
from .models import AgentAction, AgentPolicy, AuditEntry, CoordinatorSettings, LeaveRecord, PublicHoliday, WorkSchedule

SETTINGS_FIELDS = ("paused", "shadow_mode", "timezone", "daily_cost_cap_usd")


def _person(u) -> dict | None:
    return {"id": u.id, "display_name": u.display_name} if u else None


def settings_dict(s: CoordinatorSettings) -> dict:
    return {**{f: getattr(s, f) for f in SETTINGS_FIELDS}, "updated_by": _person(s.updated_by), "updated_at": s.updated_at}


def policy_dict(p: AgentPolicy) -> dict:
    return {"id": p.id, "key": p.key, "scope": p.scope, "scope_id": p.scope_id, "value": p.value, "version": p.version, "active": p.active,
            "note": p.note, "effective_from": p.effective_from, "expires_at": p.expires_at, "approved_by": _person(p.approved_by),
            "created_at": p.created_at}


def leave_dict(r: LeaveRecord) -> dict:
    return {"id": r.id, "user": _person(r.user), "start_date": r.start_date, "end_date": r.end_date, "kind": r.kind, "kind_label": r.get_kind_display(),
            "hours_per_day": r.hours_per_day, "note": r.note, "status": r.status, "status_label": r.get_status_display(),
            "decided_by": _person(r.decided_by), "decided_at": r.decided_at, "created_at": r.created_at}


class MeView(APIView):
    """GET /api/coordinator/me/ — the signed-in person's conversation with the agent (created on
    first use, with a welcome), and whether they are the CEO."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        channel = services.conversation_for(request.user)
        return Response({"conversation_id": channel.id, "is_ceo": services.is_ceo(request.user),
                         "agent": {"id": services.agent_user().id, "display_name": services.AGENT_NAME}})


class SettingsView(APIView):
    """GET/PATCH /api/coordinator/settings/ — pause, shadow mode, time zone, daily cost cap (CEO)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        services.require_ceo(request.user, "view settings")
        return Response(settings_dict(CoordinatorSettings.get()))

    def patch(self, request):
        services.require_ceo(request.user, "change settings")
        s = CoordinatorSettings.get()
        before = settings_dict(s)
        errors = {}
        for f in ("paused", "shadow_mode"):
            if f in request.data:
                if not isinstance(request.data[f], bool):
                    errors[f] = ["true or false"]
                else:
                    setattr(s, f, request.data[f])
        if "timezone" in request.data:
            from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

            try:
                ZoneInfo(str(request.data["timezone"]))
                s.timezone = str(request.data["timezone"])
            except (ZoneInfoNotFoundError, ValueError):
                errors["timezone"] = ["Give a time zone such as Pacific/Auckland."]
        if "daily_cost_cap_usd" in request.data:
            try:
                cap = float(request.data["daily_cost_cap_usd"])
                if not 0 <= cap <= 500:
                    raise ValueError
                s.daily_cost_cap_usd = cap
            except (TypeError, ValueError):
                errors["daily_cost_cap_usd"] = ["A number of dollars between 0 and 500."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        s.updated_by = request.user
        s.save()
        after = settings_dict(s)
        services.audit(request.user, "change settings", "settings", before={k: before[k] for k in SETTINGS_FIELDS},
                       after={k: after[k] for k in SETTINGS_FIELDS})
        return Response(after)


class PolicyListView(APIView):
    """GET /api/coordinator/policies/ — every rule: its default, the active versions by scope and
    the history. POST {key, value, scope?, scope_id?, note?, expires_at?} — a new version (CEO)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        services.require_ceo(request.user, "view policies")
        rows = list(AgentPolicy.objects.select_related("approved_by"))
        return Response({"rules": [{"key": r.key, "label": r.label, "default": r.default, "kind": r.kind, "help": r.help,
                                    "minimum": r.minimum, "maximum": r.maximum, "choices": list(r.choices),
                                    "current": policies.resolve(r.key)} for r in policies.RULES],
                         "policies": [policy_dict(p) for p in rows]})

    def post(self, request):
        key = str(request.data.get("key", ""))
        services.require_ceo(request.user, "change policy", key)
        expires = request.data.get("expires_at")
        expires_at = parse_datetime(expires) if expires else None
        if expires and expires_at is None:
            return Response({"expires_at": ["Give a date and time."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            p = policies.set_rule(key, request.data.get("value"), scope=str(request.data.get("scope") or "company"),
                                  scope_id=str(request.data.get("scope_id") or ""), user=request.user,
                                  note=str(request.data.get("note") or ""), expires_at=expires_at)
        except policies.PolicyError as exc:
            return Response({"value": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)
        services.audit(request.user, "change policy", key, scope=p.scope, scope_id=p.scope_id, value=p.value, version=p.version)
        return Response(policy_dict(p), status=status.HTTP_201_CREATED)


class AuditView(APIView):
    """GET /api/coordinator/audit/ — who changed or tried to change the agent's controls (CEO)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        services.require_ceo(request.user, "view audit log")
        rows = AuditEntry.objects.select_related("actor")[:200]
        return Response({"entries": [{"id": e.id, "actor": _person(e.actor), "action": e.action, "target": e.target, "allowed": e.allowed,
                                      "detail": e.detail, "created_at": e.created_at} for e in rows]})


class ActionsView(APIView):
    """GET /api/coordinator/actions/ — what the agent has done, or would have done in shadow mode (CEO)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        services.require_ceo(request.user, "view agent actions")
        rows = AgentAction.objects.select_related("target", "issue")[:200]
        return Response({"actions": [{"id": a.id, "trigger": a.trigger, "target": _person(a.target), "issue": a.issue.key if a.issue else "",
                                      "reason": a.reason, "shadow": a.shadow, "created_at": a.created_at} for a in rows]})


# --- leave, holidays and schedules ---------------------------------------------------------------

class LeaveListView(APIView):
    """GET /api/coordinator/leave/ — your leave (the CEO: everyone's, ?status=pending for the queue).
    POST {start_date, end_date, kind, hours_per_day?, note?} — request leave for yourself."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = LeaveRecord.objects.select_related("user", "decided_by")
        if not services.is_ceo(request.user):
            qs = qs.filter(user=request.user)
        if request.query_params.get("status") in LeaveRecord.Status.values:
            qs = qs.filter(status=request.query_params["status"])
        return Response({"leave": [leave_dict(r) for r in qs[:300]]})

    def post(self, request):
        start, end = parse_date(str(request.data.get("start_date") or "")), parse_date(str(request.data.get("end_date") or ""))
        errors = {}
        if not start:
            errors["start_date"] = ["Give the first day."]
        if not end:
            errors["end_date"] = ["Give the last day."]
        if start and end and end < start:
            errors["end_date"] = ["The last day cannot be before the first."]
        kind = request.data.get("kind") or LeaveRecord.Kind.ANNUAL
        if kind not in LeaveRecord.Kind.values:
            errors["kind"] = ["Choose annual, sick, training or other."]
        hours = request.data.get("hours_per_day")
        if hours not in (None, ""):
            try:
                hours = float(hours)
                if not 0 < hours <= 24:
                    raise ValueError
            except (TypeError, ValueError):
                errors["hours_per_day"] = ["Hours between 0 and 24, or leave empty for whole days."]
        else:
            hours = None
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        record = LeaveRecord.objects.create(user=request.user, start_date=start, end_date=end, kind=kind, hours_per_day=hours,
                                            note=str(request.data.get("note") or "")[:300])
        if services.is_ceo(request.user):  # the CEO's own leave needs no one else's approval
            record.status, record.decided_by, record.decided_at = LeaveRecord.Status.APPROVED, request.user, timezone.now()
            record.save()
        return Response(leave_dict(record), status=status.HTTP_201_CREATED)


class LeaveDetailView(APIView):
    """POST /api/coordinator/leave/<id>/decide/ {status: approved|rejected} (CEO).
    DELETE /api/coordinator/leave/<id>/ — withdraw your own request while it is still waiting."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        record = get_object_or_404(LeaveRecord, pk=pk)
        services.require_ceo(request.user, "decide leave", f"leave {pk}")
        decision = request.data.get("status")
        if decision not in (LeaveRecord.Status.APPROVED, LeaveRecord.Status.REJECTED):
            return Response({"status": ["approved or rejected"]}, status=status.HTTP_400_BAD_REQUEST)
        record.status, record.decided_by, record.decided_at = decision, request.user, timezone.now()
        record.save()
        services.audit(request.user, "decide leave", f"{record.user.display_name} {record.start_date}–{record.end_date}", status=decision)
        return Response(leave_dict(record))

    def delete(self, request, pk):
        record = get_object_or_404(LeaveRecord, pk=pk, user=request.user)
        if record.status != LeaveRecord.Status.PENDING:
            return Response({"detail": "Only a request still waiting for approval can be withdrawn."}, status=status.HTTP_409_CONFLICT)
        record.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HolidayListView(APIView):
    """GET /api/coordinator/holidays/ — public holidays. POST {date, name} / DELETE ?date= (CEO)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({"holidays": [{"date": h.date, "name": h.name} for h in PublicHoliday.objects.filter(date__gte=date(date.today().year - 1, 1, 1))]})

    def post(self, request):
        services.require_ceo(request.user, "add holiday")
        day, name = parse_date(str(request.data.get("date") or "")), str(request.data.get("name") or "").strip()[:100]
        if not day or not name:
            return Response({"date": ["Give the date and the holiday's name."]}, status=status.HTTP_400_BAD_REQUEST)
        PublicHoliday.objects.update_or_create(date=day, defaults={"name": name})
        services.audit(request.user, "add holiday", f"{day} {name}")
        return Response({"date": day, "name": name}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        services.require_ceo(request.user, "remove holiday")
        day = parse_date(str(request.query_params.get("date") or ""))
        deleted, _ = PublicHoliday.objects.filter(date=day).delete() if day else (0, None)
        if deleted:
            services.audit(request.user, "remove holiday", str(day))
        return Response(status=status.HTTP_204_NO_CONTENT if deleted else status.HTTP_404_NOT_FOUND)


class ScheduleView(APIView):
    """GET /api/coordinator/schedules/ — everyone's weekly hours (CEO). PUT /schedules/<user_id>/
    {hours: [Mon..Sun], note?} — set someone's hours, e.g. part-time (CEO)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        services.require_ceo(request.user, "view schedules")
        from .calendar import week_of

        users = User.objects.filter(is_active=True, is_agent=False).order_by("display_name")
        notes = {s.user_id: s.note for s in WorkSchedule.objects.all()}
        return Response({"schedules": [{"user": _person(u), "hours": week_of(u), "note": notes.get(u.id, "")} for u in users]})

    def put(self, request, user_id):
        services.require_ceo(request.user, "change schedule", f"user {user_id}")
        person = get_object_or_404(User, pk=user_id, is_agent=False)
        hours = request.data.get("hours")
        try:
            hours = [float(h) for h in hours]
            if len(hours) != 7 or not all(0 <= h <= 24 for h in hours):
                raise ValueError
        except (TypeError, ValueError):
            return Response({"hours": ["Seven numbers, Monday to Sunday, each 0 to 24."]}, status=status.HTTP_400_BAD_REQUEST)
        WorkSchedule.objects.update_or_create(user=person, defaults={"hours": hours, "note": str(request.data.get("note") or "")[:200],
                                                                     "updated_by": request.user})
        services.audit(request.user, "change schedule", person.display_name, hours=hours)
        return Response({"user": _person(person), "hours": hours, "note": str(request.data.get("note") or "")[:200]})
