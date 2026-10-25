"""Phase 2 of the coordination agent (core coordination): silent checks every round, one grouped
message per person, follow-ups and escalation to the team lead, replies read into commitments with
the figures worked out by code, shadow mode, the pause, and the CEO's daily briefing. Follows the
acceptance tests in section 16 of AFIT's specification."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import User
from apps.chat.models import Message
from apps.coordinator import conversation, engine, llm, services
from apps.coordinator.models import AgentAction, AgentCase, Commitment, CoordinatorSettings
from apps.precheck.models import TaskMilestone
from apps.precheck.tests.test_direction_drafting import make_job
from apps.teams.models import Team, TeamMembership
from apps.timesheets.models import TimeEntry

pytestmark = pytest.mark.django_db
NZ = ZoneInfo("Pacific/Auckland")
MON = date(2026, 11, 2)  # a working week with no public holiday


def at(day: date, hh: int = 10, mm: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=NZ)


def person(name, **extra):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="pw-12345678", display_name=name.title(), **extra)


def texts_to(user) -> list[str]:
    channel = services.conversation_for(user)
    return [conversation._text_of(m.body) for m in Message.objects.filter(channel=channel, author__is_agent=True).order_by("id")][1:]  # after the welcome


@pytest.fixture
def world(settings):
    settings.COORDINATOR_REPLY_ASYNC = False
    s = CoordinatorSettings.get()
    s.shadow_mode = False  # most tests look at what staff receive; shadow mode has its own test
    s.save()
    from apps.orgs.models import Organization

    pat, lee = person("pat"), person("lee")
    person("dushan")
    call_command("set_ceo", "dushan@example.com")
    job = make_job(pat, "Smith", "SmithRent", summary="Smith Rentals FY26")
    team = Team.objects.create(name="Rentals", organization=Organization.get_solo())
    job.project.client.team = team
    job.project.client.save()
    TeamMembership.objects.create(team=team, user=lee, role=TeamMembership.Role.LEAD)
    TeamMembership.objects.create(team=team, user=pat, role=TeamMembership.Role.MEMBER)
    job.preparer, job.start_date, job.budgeted_hours = pat, MON, 20
    job.save()

    class W:
        pass

    w = W()
    w.pat, w.lee, w.ceo, w.job, w.settings = pat, lee, User.objects.get(email="dushan@example.com"), job, s
    return w


def test_a_normal_job_is_watched_silently_and_asked_about_once_before_its_pre_check_is_due(world):
    """3 working days from Monday: due Thursday. Nothing on Monday or Tuesday; one message on
    Wednesday, the day before; the same round again sends nothing more."""
    for day in (MON, MON + timedelta(days=1)):
        engine.tick(at(day))
    assert texts_to(world.pat) == []
    engine.tick(at(MON + timedelta(days=2)))
    engine.tick(at(MON + timedelta(days=2), 10, 15))
    (msg,) = texts_to(world.pat)
    assert "SmithRent" in msg and "the pre-check is due Thu 05 Nov and hasn't been run yet" in msg
    case = AgentCase.objects.get(issue=world.job, kind="precheck_due")
    assert (case.asked, case.state, case.due_date) == (1, "asked", date(2026, 11, 5))
    # The pre-check is done: the case closes, nobody is asked again.
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON + timedelta(days=2), auto=True)
    engine.tick(at(MON + timedelta(days=3)))
    case.refresh_from_db()
    assert case.state == "resolved" and len(texts_to(world.pat)) == 1


def test_an_urgent_job_with_no_activity_is_raised_on_day_one(world):
    world.job.priority = "highest"
    world.job.save()
    engine.tick(at(MON + timedelta(days=1)))
    (msg,) = texts_to(world.pat)
    assert "highest priority" in msg and "can't see any activity" in msg
    assert AgentCase.objects.filter(issue=world.job, kind="urgent_inactive", asked=1).exists()


def test_preparation_due_soon_asks_what_remains_with_the_hours_from_the_record(world):
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON + timedelta(days=3)  # Thursday
    world.job.save()
    TimeEntry.objects.create(user=world.pat, issue=world.job, project=world.job.project, duration=timedelta(hours=16), work_date=MON)
    engine.tick(at(MON + timedelta(days=2)))
    (msg,) = texts_to(world.pat)
    assert "preparation is due Thu 05 Nov. 16.0 of 20.0 budgeted hours used (80%)" in msg
    assert "how many more hours do you need, and when will you finish" in msg


def test_no_reply_brings_follow_ups_then_the_team_lead(world):
    """Spec: a limited number of follow-ups, then escalation instead of an endless argument."""
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON - timedelta(days=3)  # already overdue
    world.job.save()
    day = MON
    engine.tick(at(day))
    for n in range(3):  # each round 25 hours later: two follow-ups, then the lead
        day = day + timedelta(days=1)
        engine.tick(at(day, 10, 30))
    msgs = texts_to(world.pat)
    assert len(msgs) == 3 and msgs[1].startswith("Hi Pat. Following up:")
    assert "preparation was due Fri 30 Oct and is 1 working day overdue" in msgs[0]
    (to_lead,) = texts_to(world.lee)
    assert "Pat hasn't given an update on SmithRent" in to_lead and "after 3 messages" in to_lead
    case = AgentCase.objects.get(issue=world.job, kind="prep_overdue")
    assert case.state == "escalated" and case.escalated_to == world.lee
    engine.tick(at(day + timedelta(days=1), 10, 45))
    assert len(texts_to(world.pat)) == 3 and len(texts_to(world.lee)) == 1  # nothing more after escalating


def test_missing_client_documents_are_named_not_blamed(world, monkeypatch):
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON - timedelta(days=1)
    world.job.save()
    monkeypatch.setattr("apps.coordinator.facts.outstanding_client_requests", lambda issue: ["Annual loan summary", "Rates notice"])
    engine.tick(at(MON))
    (msg,) = texts_to(world.pat)
    assert "The pre-check still lists 2 items to come from the client; if that is what's holding it up, say so" in msg
    assert "fault" not in msg.lower()


def test_a_reply_becomes_a_commitment_and_the_figures_are_worked_out_by_code(world, monkeypatch, django_capture_on_commit_callbacks):
    """Spec 5.3: "I need another eight hours because the bookkeeping had errors" on 16 of 20 hours
    → 24 hours, 120% of the estimate, within the 25% tolerance."""
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON + timedelta(days=3)
    world.job.save()
    TimeEntry.objects.create(user=world.pat, issue=world.job, project=world.job.project, duration=timedelta(hours=16), work_date=MON)
    engine.tick(at(MON + timedelta(days=2)))
    today = timezone.localtime(timezone.now(), NZ).date()
    eta = today + timedelta(days=2)
    seen = {}

    def fake(system, messages, schema, **kw):
        seen["system"], seen["context"] = system, messages[0]["content"]
        return {"reply": "Thanks Pat. Please link the bookkeeping corrections and let your team lead know.",
                "updates": [{"job_key": world.job.key, "remaining_hours": 8, "eta_date": eta.isoformat(), "percent_complete": 80,
                             "cause": "bookkeeping_errors", "blockers": "", "needs_help": False}]}, 0.004

    monkeypatch.setattr(llm, "structured", fake)
    channel = services.conversation_for(world.pat)
    with django_capture_on_commit_callbacks(execute=True):
        Message.objects.create(channel=channel, author=world.pat, body={"type": "doc", "content": [{"type": "paragraph", "content": [
            {"type": "text", "text": "I need another eight hours because the bookkeeping had errors."}]}]})
    reply = texts_to(world.pat)[-1]
    assert reply.startswith("Thanks Pat.")
    assert f"Noted for {world.job.key}: 16.0h used + 8.0h to go = 24.0h, 120% of the 20.0h budget — within the 125% tolerance." in reply
    c = Commitment.objects.get(issue=world.job)
    assert (c.remaining_hours, c.eta_date, c.cause, c.status) == (8, eta, "bookkeeping_errors", "open")
    case = AgentCase.objects.get(issue=world.job, kind="prep_due")
    assert case.state == "answered" and case.revised_due == eta
    assert "SmithRent" in seen["context"] and "THEIR OPEN JOBS" in seen["context"] and "Talk only about this person's own jobs" in seen["system"]
    assert AgentAction.objects.get(trigger="reply").cost_usd == 0.004


def test_a_forecast_above_tolerance_or_a_request_for_help_goes_to_the_team_lead(world, monkeypatch, django_capture_on_commit_callbacks):
    world.job.budgeted_hours = 10
    world.job.save()
    TimeEntry.objects.create(user=world.pat, issue=world.job, project=world.job.project, duration=timedelta(hours=9), work_date=MON)
    monkeypatch.setattr(llm, "structured", lambda *a, **k: ({"reply": "Understood.", "updates": [
        {"job_key": world.job.key, "remaining_hours": 5, "eta_date": "", "percent_complete": -1, "cause": "complexity",
         "blockers": "Unsure how to treat the subdivision", "needs_help": True}]}, 0.003))
    with django_capture_on_commit_callbacks(execute=True):
        Message.objects.create(channel=services.conversation_for(world.pat), author=world.pat, body={"type": "doc", "content": []})
    assert "14.0h, 140% of the 10.0h budget — above the 125% tolerance." in texts_to(world.pat)[-1]
    to_lead = texts_to(world.lee)
    assert any("now forecasts" in t and "above the hours tolerance" in t for t in to_lead)
    assert any("has asked for help" in t and "subdivision" in t for t in to_lead)


def test_when_the_model_is_unavailable_the_agent_still_answers(world, monkeypatch, django_capture_on_commit_callbacks):
    def down(*a, **k):
        raise llm.Unavailable("no API key")

    monkeypatch.setattr(llm, "structured", down)
    with django_capture_on_commit_callbacks(execute=True):
        Message.objects.create(channel=services.conversation_for(world.pat), author=world.pat, body={"type": "doc", "content": []})
    assert "please give me the hours you still need and the date you expect to finish" in texts_to(world.pat)[-1]


def test_a_missed_revised_date_is_followed_up_until_a_new_date_or_the_stage_is_done(world):
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON + timedelta(days=10)
    world.job.save()
    Commitment.objects.create(person=world.pat, issue=world.job, eta_date=MON + timedelta(days=1))
    engine.tick(at(MON + timedelta(days=2)))
    (msg,) = texts_to(world.pat)
    assert "you expected to finish by Tue 03 Nov, and it isn't marked done yet" in msg
    engine.tick(at(MON + timedelta(days=2), 11))
    assert AgentCase.objects.filter(kind="promise_missed").exclude(state="resolved").count() == 1  # still open, not re-asked
    assert len(texts_to(world.pat)) == 1
    TaskMilestone.objects.create(issue=world.job, kind="preparation", on=MON + timedelta(days=2))
    engine.tick(at(MON + timedelta(days=3)))
    c = Commitment.objects.get(issue=world.job)
    assert c.status == "missed" and c.verified_at  # done, after the date given
    assert not AgentCase.objects.exclude(state="resolved").exists()


def test_shadow_mode_sends_nothing_to_staff_and_shows_the_ceo_instead(world):
    world.settings.shadow_mode = True
    world.settings.save()
    world.job.priority = "highest"
    world.job.save()
    engine.tick(at(MON + timedelta(days=1)))
    assert texts_to(world.pat) == []
    digest = [t for t in texts_to(world.ceo) if t.startswith("Shadow mode")]
    assert len(digest) == 1 and "To Pat:" in digest[0] and "can't see any activity" in digest[0]
    assert AgentAction.objects.filter(trigger="urgent_inactive", shadow=True, message__isnull=True).count() == 1


def test_paused_means_nothing_at_all_and_outside_hours_means_silent_checks_only(world):
    world.job.priority = "highest"
    world.job.save()
    world.settings.paused = True
    world.settings.save()
    assert engine.tick(at(MON + timedelta(days=1))) == {"paused": True}
    assert not AgentCase.objects.exists()
    world.settings.paused = False
    world.settings.save()
    result = engine.tick(at(MON + timedelta(days=1), 19, 0))  # 7 pm
    assert result["sending"] is False and texts_to(world.pat) == []
    assert AgentCase.objects.get(kind="urgent_inactive").asked == 0  # seen, not yet asked
    engine.tick(at(MON + timedelta(days=2), 8, 45))
    assert len(texts_to(world.pat)) == 1  # first thing in the morning


def test_the_ceo_gets_one_briefing_each_working_day(world, monkeypatch):
    monkeypatch.setattr(llm, "structured", lambda *a, **k: ({"summary": "One preparation is overdue; Pat has not replied yet."}, 0.002))
    TaskMilestone.objects.create(issue=world.job, kind="precheck", on=MON, auto=True)
    world.job.due_date = MON - timedelta(days=1)
    world.job.save()
    engine.tick(at(MON, 8, 0))
    assert not [t for t in texts_to(world.ceo) if t.startswith("Good morning")]  # before 08:15
    engine.tick(at(MON, 8, 30))
    engine.tick(at(MON, 9, 0))
    briefings = [t for t in texts_to(world.ceo) if t.startswith("Good morning")]
    assert len(briefings) == 1
    b = briefings[0]
    assert "One preparation is overdue; Pat has not replied yet." in b and "Overdue (1):" in b and "SmithRent" in b and "Pat" in b
    assert AgentAction.objects.get(trigger="ceo_briefing").cost_usd == 0.002


def test_the_ceo_sees_what_is_being_followed_up(world):
    from rest_framework.test import APIClient

    world.job.priority = "highest"
    world.job.save()
    engine.tick(at(MON + timedelta(days=1)))
    client = APIClient()
    client.force_authenticate(world.ceo)
    (case,) = client.get("/api/coordinator/cases/").data["cases"]
    assert case["issue"] == world.job.key and case["person"]["display_name"] == "Pat" and case["asked"] == 1
    client.force_authenticate(world.pat)
    assert client.get("/api/coordinator/cases/").status_code == 403
