"""The pre-check's request list is kept with the run, and corrections become lessons the next
pre-check applies: at once for that client, firm-wide after a lead or admin approves."""
import copy
import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.precheck import services
from apps.precheck.models import AIPrecheck, PrecheckLesson
from apps.teams.models import Team, TeamMembership

from .test_direction_drafting import make_job

pytestmark = pytest.mark.django_db

SAMPLE = json.loads((Path(__file__).parent / "sample_result.json").read_text(encoding="utf-8"))
TOKEN = {"HTTP_X_PRECHECK_TOKEN": "test-token"}


@pytest.fixture(autouse=True)
def service(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    monkeypatch.setattr(services, "_call_agent", lambda path, body: {})


def person(name, staff=False):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title(), is_staff=staff)


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def finished(issue, user) -> AIPrecheck:
    run = services.start_run(issue, user)
    result = copy.deepcopy(SAMPLE)
    result["run_id"] = run.run_id
    assert APIClient().post("/api/precheck/internal/events/", {"run_id": run.run_id, "type": "ai_precheck.completed", "result": result},
                            format="json", **TOKEN).status_code == 200
    return AIPrecheck.objects.get(run_id=run.run_id)


def test_the_request_list_and_email_are_kept_with_the_run():
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    finished(issue, pat)
    latest = api(pat).get(f"/api/precheck/jobs/{issue.key}/").data["latest"]
    p = latest["precheck"]
    assert latest["readiness"] == "Requests to send" and latest["findings"] == []
    assert p["decision"]["state"] == "requests" and p["business_nature"]["type"] == "residential_rental"
    assert p["requests"] and all(r["reason"] and r["sources"] for r in p["requests"])
    assert p["email"]["subject"] and p["requests"][0]["item"] in p["email"]["body"]
    assert {k["role"] for k in p["key_documents"]} == {"questionnaire", "last_year_fs", "last_year_workpapers"}


def test_a_correction_applies_to_that_client_at_once_and_firm_wide_after_approval():
    owner, pat, lead, other = person("owen"), person("pat"), person("lena"), person("olga")  # owner leads the projects
    smith = make_job(owner, "Smith", "SmithRent")
    jones = make_job(owner, "Jones", "JonesRent")
    team = Team.objects.create(organization=smith.project.organization, name="Rentals")
    TeamMembership.objects.create(team=team, user=lead, role="lead")
    for project in (smith.project, jones.project):
        project.primary_team = team
        project.save()
    finished(smith, pat)

    # Pat: "home office was not needed" — for this client, and suggested for all rental clients.
    resp = api(pat).post(f"/api/precheck/jobs/{smith.key}/lessons/", {
        "kind": "not_needed", "item": "Home office details", "note": "Barfoot manages the property, so no home office is claimed.", "firm_wide": True,
    }, format="json")
    assert resp.status_code == 201 and resp.data["scope"] == "firm" and resp.data["status"] == "pending"
    lesson_id = resp.data["id"]
    assert PrecheckLesson.objects.get(pk=lesson_id).precheck_type == "residential_rental"  # the business nature of that run
    client_only = api(pat).post(f"/api/precheck/jobs/{smith.key}/lessons/", {
        "kind": "missed", "item": "Bond lodgement", "note": "Always ask Smith for the bond lodgement receipt."}, format="json").data

    # The next pre-check for Smith gets both at once; Jones gets neither yet.
    smith_payload = APIClient().get(f"/api/precheck/internal/jobs/{smith.id}/", **TOKEN).json()
    assert {lesson["id"] for lesson in smith_payload["lessons"]} == {lesson_id, client_only["id"]}
    assert APIClient().get(f"/api/precheck/internal/jobs/{jones.id}/", **TOKEN).json()["lessons"] == []

    # Only a lead or admin approves it for everyone; then Jones gets it too (not Smith's own lesson).
    assert api(pat).get(f"/api/precheck/jobs/{smith.key}/lessons/").data["can_approve"] is False
    assert api(pat).patch(f"/api/precheck/lessons/{lesson_id}/", {"status": "active"}, format="json").status_code == 403
    lead_view = api(lead).get(f"/api/precheck/jobs/{jones.key}/lessons/").data
    assert lead_view["can_approve"] and [lesson["id"] for lesson in lead_view["pending_firm_wide"]] == [lesson_id]
    assert api(lead).patch(f"/api/precheck/lessons/{lesson_id}/", {"status": "active"}, format="json").data["status"] == "active"
    jones_lessons = APIClient().get(f"/api/precheck/internal/jobs/{jones.id}/", **TOKEN).json()["lessons"]
    assert [lesson["id"] for lesson in jones_lessons] == [lesson_id]

    # A lesson can be switched off by its author or a lead, not by someone else.
    assert api(other).patch(f"/api/precheck/lessons/{client_only['id']}/", {"status": "disabled"}, format="json").status_code == 403
    assert api(pat).patch(f"/api/precheck/lessons/{client_only['id']}/", {"status": "disabled"}, format="json").status_code == 200
    assert {lesson["id"] for lesson in APIClient().get(f"/api/precheck/internal/jobs/{smith.id}/", **TOKEN).json()["lessons"]} == {lesson_id}


def test_a_lead_teaching_firm_wide_needs_no_second_approval_and_bad_input_is_refused():
    admin = person("ada", staff=True)
    issue = make_job(admin, "Smith", "SmithRent")
    resp = api(admin).post(f"/api/precheck/jobs/{issue.key}/lessons/", {
        "kind": "wrong_reason", "item": "Rates", "note": "Rates are paid by the property manager here.", "firm_wide": True}, format="json")
    assert resp.data["status"] == "active"
    assert api(admin).post(f"/api/precheck/jobs/{issue.key}/lessons/", {"kind": "nonsense", "note": "something useful"}, format="json").status_code == 400
    assert api(admin).post(f"/api/precheck/jobs/{issue.key}/lessons/", {"kind": "other", "note": "no"}, format="json").status_code == 400


def test_a_person_says_where_the_key_documents_are_and_the_agent_is_told():
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    url = f"/api/precheck/jobs/{issue.key}/setup/"
    r = api(pat).put(url, {"key_paths": {"questionnaire": " 2026/Client  Questionnaire.pdf ", "last_year_fs": "",
                                          "last_year_workpapers": "Archive.zip/2025/Workpapers; https://drive.google.com/file/d/abc/view"}}, format="json")
    assert r.status_code == 200
    assert r.data["key_paths"] == {"questionnaire": "2026/Client Questionnaire.pdf", "last_year_fs": "",
                                   "last_year_workpapers": "Archive.zip/2025/Workpapers; https://drive.google.com/file/d/abc/view"}
    payload = services.job_payload(Issue.objects.get(pk=issue.pk))
    assert payload["key_paths"] == {"questionnaire": "2026/Client Questionnaire.pdf",
                                    "last_year_workpapers": "Archive.zip/2025/Workpapers; https://drive.google.com/file/d/abc/view"}
    assert api(pat).put(url, {"key_paths": {"tax_return": "x"}}, format="json").status_code == 400
    # Cleared: the pre-check searches the folder again.
    api(pat).put(url, {"key_paths": {"questionnaire": ""}}, format="json")
    assert services.job_payload(Issue.objects.get(pk=issue.pk))["key_paths"] == {}
