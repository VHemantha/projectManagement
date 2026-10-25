"""Phase 1 of the coordination agent: the CEO role, the agent's identity and conversations in the
Messages section, its versioned policies (CEO only, refusals logged), and the work calendars."""
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.chat.models import Channel, Message
from apps.coordinator import calendar, policies, services
from apps.coordinator.models import AgentPolicy, AuditEntry, LeaveRecord, PublicHoliday, WorkSchedule
from apps.precheck.tests.test_direction_drafting import make_job

pytestmark = pytest.mark.django_db


def person(name, **extra):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw-12345678", display_name=name.title(), **extra)


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def ceo():
    u = person("dushan")
    call_command("set_ceo", "dushan@example.com")
    u.refresh_from_db()
    return u


# --- the CEO role ------------------------------------------------------------------------------------

def test_the_ceo_has_full_access_and_there_is_one_ceo(ceo):
    assert ceo.is_ceo and ceo.is_staff and ceo.is_superuser
    assert api(ceo).get("/api/auth/me/").data["role"] == "ceo"
    other = person("pat")
    call_command("set_ceo", "pat@example.com")
    ceo.refresh_from_db()
    assert not ceo.is_ceo and ceo.is_staff  # the previous CEO keeps their admin rights
    assert User.objects.filter(role="ceo").get() == other
    assert AuditEntry.objects.filter(action="set CEO", target="pat@example.com").exists()


def test_only_the_ceo_controls_the_agent_and_refusals_are_logged(ceo):
    pat = person("pat", is_staff=True)  # even an admin who is not the CEO
    r = api(pat).patch("/api/coordinator/settings/", {"paused": True}, format="json")
    assert r.status_code == 403
    assert api(pat).post("/api/coordinator/policies/", {"key": "hours_tolerance_pct", "value": 150}, format="json").status_code == 403
    refused = AuditEntry.objects.filter(actor=pat, allowed=False)
    assert {e.action for e in refused} == {"change settings", "change policy"}
    assert policies.resolve("hours_tolerance_pct") == 125  # nothing changed

    r = api(ceo).patch("/api/coordinator/settings/", {"paused": True, "shadow_mode": False}, format="json")
    assert r.status_code == 200 and r.data["paused"] and not r.data["shadow_mode"]
    entry = AuditEntry.objects.get(actor=ceo, action="change settings")
    assert entry.allowed and entry.detail["before"]["paused"] is False and entry.detail["after"]["paused"] is True


# --- the agent in the Messages section ------------------------------------------------------------------

def test_everyone_has_one_private_conversation_with_the_agent():
    pat, sam = person("pat"), person("sam")
    first = api(pat).get("/api/coordinator/me/").data
    again = api(pat).get("/api/coordinator/me/").data
    assert first["conversation_id"] == again["conversation_id"] and not first["is_ceo"]
    channel = Channel.objects.get(pk=first["conversation_id"])
    agent = services.agent_user()
    assert channel.channel_type == "direct_message" and set(channel.memberships.values_list("user_id", flat=True)) == {pat.id, agent.id}
    (welcome,) = Message.objects.filter(channel=channel)  # one welcome, not one per visit
    assert welcome.author == agent and "Loca Coordinator" in str(welcome.body)
    assert any(c["id"] == channel.id for c in api(pat).get("/api/chat/channels/").data["results"])
    assert not any(c["id"] == channel.id for c in api(sam).get("/api/chat/channels/").data["results"])  # private
    assert api(sam).get(f"/api/chat/channels/{channel.id}/messages/").status_code == 403


def test_the_agent_cannot_sign_in_and_is_not_listed_among_people():
    agent = services.agent_user()
    assert agent.is_agent and not agent.has_usable_password()
    r = APIClient().post("/api/auth/login/", {"email": services.AGENT_EMAIL, "password": ""}, format="json")
    assert r.status_code in (400, 401)
    pat = person("pat")
    assert services.AGENT_NAME not in [u["display_name"] for u in api(pat).get("/api/users/").data]


# --- policies -------------------------------------------------------------------------------------------

def test_policies_start_from_the_specification_and_every_change_is_a_new_version(ceo):
    assert policies.resolve("precheck_due_days") == 3 and policies.resolve("timesheet_min_hours") == 7.5
    assert policies.resolve("timesheet_check_time") == "09:30" and policies.resolve("hours_tolerance_pct") == 125
    r = api(ceo).post("/api/coordinator/policies/", {"key": "precheck_due_days", "value": 4, "note": "Busy season"}, format="json")
    assert r.status_code == 201 and r.data["version"] == 1
    api(ceo).post("/api/coordinator/policies/", {"key": "precheck_due_days", "value": 5}, format="json")
    rows = list(AgentPolicy.objects.filter(key="precheck_due_days").order_by("version"))
    assert [(p.version, p.value, p.active) for p in rows] == [(1, 4, False), (2, 5, True)]  # the old one is kept
    assert policies.resolve("precheck_due_days") == 5
    bad = api(ceo).post("/api/coordinator/policies/", {"key": "timesheet_check_time", "value": "9.30"}, format="json")
    assert bad.status_code == 400 and "HH:MM" in bad.data["value"][0]
    listed = api(ceo).get("/api/coordinator/policies/").data
    assert next(x for x in listed["rules"] if x["key"] == "precheck_due_days")["current"] == 5


def test_the_most_specific_rule_applies_and_an_expired_one_falls_away(ceo):
    pat = person("pat")
    job = make_job(pat, "Smith", "SmithRent")
    policies.set_rule("communication", "quiet", user=ceo)
    policies.set_rule("communication", "close", scope="client", scope_id=str(job.project.client_id), user=ceo)
    assert policies.resolve("communication", job=job, person=pat) == "close"  # the client's rule beats the company's
    policies.set_rule("communication", "normal", scope="person", scope_id=str(pat.pk), user=ceo,
                      expires_at=timezone.now() - timedelta(minutes=1))
    assert policies.resolve("communication", job=job, person=pat) == "close"  # the person's rule has expired
    policies.set_rule("communication", "normal", scope="job", scope_id=str(job.pk), user=ceo)
    assert policies.resolve("communication", job=job, person=pat) == "normal"  # the job's rule is the most specific
    assert policies.resolve("communication") == "quiet"


def test_exactly_the_tolerance_is_within_it():
    """Spec: for a 10-hour job, 12.5 hours is tolerated; 14 hours is over."""
    assert not policies.over_tolerance(12.5, 10, 125)
    assert policies.over_tolerance(12.6, 10, 125) and policies.over_tolerance(14, 10, 125)
    assert not policies.over_tolerance(5, 0, 125)  # no budget: nothing to compare


# --- work calendars and leave ----------------------------------------------------------------------------

def test_expected_hours_follow_the_schedule_holidays_and_approved_leave():
    pat = person("pat")
    monday = date(2026, 11, 2)
    assert calendar.expected_hours(pat, monday) == 8 and calendar.expected_hours(pat, monday + timedelta(days=5)) == 0  # Saturday
    assert PublicHoliday.objects.filter(date=date(2026, 10, 26), name="Labour Day").exists()
    assert calendar.expected_hours(pat, date(2026, 10, 26)) == 0
    WorkSchedule.objects.create(user=pat, hours=[8, 8, 4, 0, 0, 0, 0], note="Part-time")
    assert calendar.expected_hours(pat, monday + timedelta(days=2)) == 4 and calendar.expected_hours(pat, monday + timedelta(days=3)) == 0
    LeaveRecord.objects.create(user=pat, start_date=monday, end_date=monday, status="pending")
    assert calendar.expected_hours(pat, monday) == 8  # waiting for approval: still expected
    LeaveRecord.objects.create(user=pat, start_date=monday, end_date=monday, hours_per_day=3, status="approved")
    assert calendar.expected_hours(pat, monday) == 5


def test_working_days_skip_weekends_holidays_and_leave():
    friday = date(2026, 10, 23)  # Labour Day is Monday 26 October 2026
    assert calendar.add_days(friday, 3) == date(2026, 10, 29)  # Tue, Wed, Thu
    assert calendar.add_days(friday, 3, basis="calendar") == date(2026, 10, 26)
    assert calendar.previous_working_day(date(2026, 10, 27)) == friday  # over the weekend and the holiday
    pat = person("pat")
    LeaveRecord.objects.create(user=pat, start_date=date(2026, 10, 27), end_date=date(2026, 10, 27), status="approved")
    assert calendar.add_days(friday, 3, user=pat) == date(2026, 10, 30)


def test_people_request_leave_and_the_ceo_decides(ceo):
    pat = person("pat")
    r = api(pat).post("/api/coordinator/leave/", {"start_date": "2026-11-09", "end_date": "2026-11-10", "kind": "annual"}, format="json")
    assert r.status_code == 201 and r.data["status"] == "pending"
    leave_id = r.data["id"]
    assert api(pat).post(f"/api/coordinator/leave/{leave_id}/decide/", {"status": "approved"}, format="json").status_code == 403
    assert [x["id"] for x in api(ceo).get("/api/coordinator/leave/?status=pending").data["leave"]] == [leave_id]
    assert api(ceo).post(f"/api/coordinator/leave/{leave_id}/decide/", {"status": "approved"}, format="json").data["status"] == "approved"
    assert api(pat).delete(f"/api/coordinator/leave/{leave_id}/").status_code == 409  # decided: cannot be withdrawn
    sam = person("sam")
    assert api(sam).get("/api/coordinator/leave/").data["leave"] == []  # only your own
    bad = api(pat).post("/api/coordinator/leave/", {"start_date": "2026-11-10", "end_date": "2026-11-09"}, format="json")
    assert bad.status_code == 400
    own = api(ceo).post("/api/coordinator/leave/", {"start_date": "2026-12-01", "end_date": "2026-12-01"}, format="json")
    assert own.data["status"] == "approved"  # the CEO's own leave


def test_the_ceo_sets_part_time_hours_and_holidays(ceo):
    pat = person("pat")
    assert api(pat).put(f"/api/coordinator/schedules/{pat.id}/", {"hours": [4] * 5 + [0, 0]}, format="json").status_code == 403
    r = api(ceo).put(f"/api/coordinator/schedules/{pat.id}/", {"hours": [4, 4, 4, 4, 4, 0, 0], "note": "Mornings"}, format="json")
    assert r.status_code == 200 and calendar.week_of(pat)[0] == 4
    assert api(ceo).put(f"/api/coordinator/schedules/{pat.id}/", {"hours": [8] * 6}, format="json").status_code == 400
    assert api(ceo).post("/api/coordinator/holidays/", {"date": "2027-01-25", "name": "Wellington Anniversary"}, format="json").status_code == 201
    assert calendar.is_holiday(date(2027, 1, 25))
    assert api(pat).delete("/api/coordinator/holidays/?date=2027-01-25").status_code == 403
