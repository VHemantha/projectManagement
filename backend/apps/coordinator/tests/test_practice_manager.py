"""AFIT, 21 Nov 2026: the Practice Manager AI (renamed from the TASKO Coordinator) creates jobs when asked in a
typed or spoken message, makes the CEO a PDF report with charts when asked (CEO only), and tells the CEO and
the team leads who logged under 7.5 hours."""
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from apps.coordinator import engine, llm, services, voice
from apps.coordinator.models import CeoReport
from apps.issues.models import Attachment, Issue
from apps.timesheets.models import TimeEntry

from .test_coordination import MON, at, texts_to, world  # noqa: F401  (the shared fixture)
from .test_direct_followups import say

pytestmark = pytest.mark.django_db


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def test_the_agent_is_the_practice_manager_ai(world):
    agent = services.agent_user()
    assert agent.display_name == "Practice Manager AI" and agent.job_title == "AI practice manager"
    agent.display_name = "TASKO Coordinator"
    agent.save()
    assert services.agent_user().display_name == "Practice Manager AI"  # an older install is renamed


def test_a_job_is_created_when_someone_asks_and_the_reply_says_exactly_what_was_created(world, monkeypatch, django_capture_on_commit_callbacks):
    seen = {}
    client = world.job.project.client

    def model(system, messages, schema, **kw):
        seen.update(system=system, context=messages[0]["content"], schema=schema)
        return {"reply": "Creating it now.", "updates": [], "create_jobs": [
            {"title": "Jones Family Trust - FY26 accounts", "sub_workspace_id": client.pk, "group": "Jones group", "assignee_id": world.lee.pk,
             "preparer_id": world.pat.pk, "due_date": "2026-12-18", "budgeted_hours": -1, "standard_stages": True},
            {"title": "Unknown place job", "sub_workspace_id": 999999, "group": "", "assignee_id": -1, "preparer_id": -1, "due_date": "",
             "budgeted_hours": -1, "standard_stages": True}]}, 0.0

    monkeypatch.setattr(llm, "structured", model)
    say(world.pat, "Create a year-end job for Jones Family Trust in Smith, Lee as team lead, me to prepare, due 18 December.",
        django_capture_on_commit_callbacks)
    assert "create_jobs" in seen["schema"]["required"] and "Creating jobs (tasks)" in seen["system"]
    assert f"{client.pk}: {client.name}" in seen["context"] and f"{world.lee.pk}: Lee" in seen["context"]
    job = Issue.objects.get(summary="Jones Family Trust - FY26 accounts")
    assert (job.project.client, job.assignee, job.preparer, job.group, f"{job.due_date}") == (client, world.lee, world.pat, "Jones group", "2026-12-18")
    assert job.subtasks.exists()  # the standard stages, as the Create task form adds them
    (reply,) = texts_to(world.pat)
    assert reply.startswith("Creating it now.") and f"Created {job.key} “Jones Family Trust - FY26 accounts” in {client.name}" in reply
    assert "team lead Lee, accountant Pat, due Fri 18 Dec 2026" in reply
    assert "I couldn't create “Unknown place job”: tell me which sub-workspace it is for." in reply


def test_the_ceo_gets_a_pdf_report_with_charts_and_staff_cannot_ask_for_one(world, monkeypatch, django_capture_on_commit_callbacks):
    TimeEntry.objects.create(user=world.pat, issue=world.job, work_date=MON, duration=timedelta(hours=6))
    seen = []

    def model(system, messages, schema, **kw):
        seen.append(schema)
        if "summary" in schema["properties"] and len(schema["properties"]) == 1:  # the report's own summary
            return {"summary": "Pat logged under the hours expected."}, 0.0
        return {"reply": "Here is the report on the team's hours.", "updates": [], "contact": [], "create_jobs": [],
                "report": {"wanted": True, "title": "Team hours - last 30 days", "sections": ["hours_by_person", "jobs_by_status", "non_job_time"],
                           "period_days": 30, "person_ids": []}}, 0.0

    monkeypatch.setattr(llm, "structured", model)
    say(world.ceo, "Give me a report on the team's hours this month.", django_capture_on_commit_callbacks)
    assert "report" in seen[0]["required"]
    report = CeoReport.objects.get()
    assert report.title == "Team hours - last 30 days" and bytes(report.pdf).startswith(b"%PDF") and report.summary.startswith("Pat logged")
    assert report.spec["sections"] == ["hours_by_person", "jobs_by_status", "non_job_time"]
    (reply,) = texts_to(world.ceo)
    assert "Your report is attached: Team hours - last 30 days (PDF)." in reply
    (pdf,) = Attachment.objects.filter(message__channel=services.conversation_for(world.ceo))
    assert pdf.filename.endswith(".pdf")
    assert api(world.ceo).get("/api/coordinator/reports/").data["reports"][0]["title"] == "Team hours - last 30 days"
    got = api(world.ceo).get(f"/api/coordinator/reports/{report.pk}/pdf/")
    assert got.status_code == 200 and got["Content-Type"] == "application/pdf"
    # CEO only.
    assert api(world.pat).get("/api/coordinator/reports/").status_code == 403
    assert api(world.lee).get(f"/api/coordinator/reports/{report.pk}/pdf/").status_code == 403
    seen.clear()
    monkeypatch.setattr(llm, "structured", lambda system, messages, schema, **kw: (seen.append(schema) or
                                                                                  {"reply": "Only the CEO can have reports.", "updates": [], "create_jobs": []}, 0.0))
    say(world.pat, "Make me a report of everyone's hours.", django_capture_on_commit_callbacks)
    assert "report" not in seen[0]["properties"] and CeoReport.objects.count() == 1


def test_the_ceo_and_the_team_lead_are_told_who_logged_under_seven_and_a_half_hours(world, settings):
    settings.COORDINATOR_LOW_HOURS = True
    TimeEntry.objects.create(user=world.pat, issue=world.job, work_date=MON, duration=timedelta(hours=4, minutes=30))
    TimeEntry.objects.create(user=world.lee, issue=world.job, work_date=MON, duration=timedelta(hours=8))
    engine.tick(at(MON + timedelta(days=1), 10, 0))
    to_ceo = [t for t in texts_to(world.ceo) if t.startswith("Hours logged on")]
    assert len(to_ceo) == 1 and "Hours logged on Monday 02 November: 1 of the team logged under 7.5 hours." in to_ceo[0]
    assert "• Pat: 4.5h logged of 7.5h (3h short)" in to_ceo[0] and "Lee:" not in to_ceo[0]
    (to_lead,) = [t for t in texts_to(world.lee) if t.startswith("Hours logged on")]
    assert "1 of the people you lead logged under 7.5 hours" in to_lead and "• Pat: 4.5h" in to_lead
    engine.tick(at(MON + timedelta(days=1), 10, 15))  # once a day
    assert len([t for t in texts_to(world.ceo) if t.startswith("Hours logged on")]) == 1


def test_a_spoken_message_is_turned_into_text_by_amazon_transcribe(world, monkeypatch, settings):
    clip = lambda kind="audio/webm": SimpleUploadedFile("message.webm", b"\x1aE\xdf\xa3 fake", content_type=kind)  # noqa: E731
    settings.VOICE_TRANSCRIBE_BUCKET = ""
    off = api(world.pat).post("/api/coordinator/voice/", {"audio": clip()}, format="multipart")
    assert off.status_code == 503 and "isn't set up" in off.data["detail"]
    sent = {}

    def fake(data, fmt):
        sent.update(data=data, fmt=fmt)
        return "Create a job for Jones Family Trust in Smith."

    monkeypatch.setattr(voice, "transcribe", fake)
    ok = api(world.pat).post("/api/coordinator/voice/", {"audio": clip("audio/webm;codecs=opus")}, format="multipart")
    assert ok.status_code == 200 and ok.data["text"] == "Create a job for Jones Family Trust in Smith." and sent["fmt"] == "webm"
    bad = api(world.pat).post("/api/coordinator/voice/", {"audio": SimpleUploadedFile("x.txt", b"hi", content_type="text/plain")}, format="multipart")
    assert bad.status_code == 400
