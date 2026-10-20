"""No AI run keeps a task waiting for ever: a person can stop a pre-check, guide, review, Direction
Note draft or question, and one that never reports back is marked failed after a time limit."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.issues.models import Comment
from apps.precheck import services
from apps.precheck.models import AIPrecheck, AssistantQuestion

from .test_guide_milestones import SAMPLE, TOKEN, api, finish, person
from .test_direction_drafting import make_job

pytestmark = pytest.mark.django_db


@pytest.fixture
def agent(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    calls = []
    monkeypatch.setattr(services, "_call_agent", lambda path, body: calls.append((path, body)) or {})
    return calls


@pytest.mark.parametrize("kind", [AIPrecheck.Kind.PRECHECK, AIPrecheck.Kind.GUIDE, AIPrecheck.Kind.REVIEW, AIPrecheck.Kind.DRAFT])
def test_a_person_stops_a_run_and_can_start_again(agent, kind):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    run = services.start_run(issue, pat, kind=kind)
    r = api(pat).post(f"/api/precheck/runs/{run.run_id}/stop/", {}, format="json")
    assert r.status_code == 200 and r.data["status"] == "failed" and r.data["failure_reason"] == "Stopped by Pat. Nothing was changed."
    assert agent[-1][0] == f"/precheck/runs/{run.run_id}/cancel"  # the agent is told to do no more work
    # A result that arrives after the stop is ignored: nothing is stored or posted.
    late = APIClient().post("/api/precheck/internal/events/", {"run_id": run.run_id, "type": "ai_precheck.completed",
                                                               "result": {**SAMPLE, "run_id": run.run_id}}, format="json", **TOKEN)
    assert late.status_code == 409 and AIPrecheck.objects.get(pk=run.pk).status == "failed"
    assert not Comment.objects.filter(issue=issue).exists()
    # Stopping again says it has already finished; a new run may start.
    assert api(pat).post(f"/api/precheck/runs/{run.run_id}/stop/", {}, format="json").status_code == 409
    assert api(pat).post("/api/precheck/runs/", {"job": issue.key}, format="json").status_code == 201


def test_the_agent_being_unreachable_does_not_prevent_the_stop(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    monkeypatch.setattr(services, "_call_agent", lambda path, body: {})
    run = services.start_run(issue, pat)

    def unreachable(path, body):
        raise services.AgentUnavailable("down")

    monkeypatch.setattr(services, "_call_agent", unreachable)
    assert api(pat).post(f"/api/precheck/runs/{run.run_id}/stop/", {}, format="json").status_code == 200


def test_a_run_that_never_reports_back_is_failed_after_the_limit(agent, settings):
    settings.PRECHECK_STALE_RUN_MINUTES = 50
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    lost = services.start_run(issue, pat, kind=AIPrecheck.Kind.GUIDE)
    AIPrecheck.objects.filter(pk=lost.pk).update(created_at=timezone.now() - timedelta(minutes=51))
    recent = services.start_run(issue, pat)
    AIPrecheck.objects.filter(pk=recent.pk).update(created_at=timezone.now() - timedelta(minutes=5))
    state = api(pat).get(f"/api/precheck/jobs/{issue.key}/guide/").data
    assert state["latest"]["status"] == "failed" and "did not finish within 50 minutes" in state["latest"]["failure_reason"]
    assert AIPrecheck.objects.get(pk=recent.pk).status == "running"  # still within its time
    finish(recent.run_id)  # and it can still finish normally
    assert AIPrecheck.objects.get(pk=recent.pk).status == "complete"


def test_a_question_can_be_stopped_and_one_left_waiting_is_failed(agent, settings):
    settings.PRECHECK_STALE_QUESTION_MINUTES = 10
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    url = f"/api/precheck/jobs/{issue.key}/ask/"
    q1 = api(pat).post(url, {"question": "What was the rent?"}, format="json").data
    q2 = api(pat).post(url, {"question": "Who is the tenant?"}, format="json").data
    r = api(pat).post(f"/api/precheck/questions/{q1['id']}/stop/", {}, format="json")
    assert r.status_code == 200 and r.data["status"] == "failed" and r.data["failure_reason"] == "Stopped by Pat."
    late = APIClient().post("/api/precheck/internal/events/", {"run_id": q1["id"], "type": "ai_assistant.answered",
                                                               "result": {"answer": "x", "status": "answered"}}, format="json", **TOKEN)
    assert late.status_code == 409
    AssistantQuestion.objects.filter(question_id=q2["id"]).update(created_at=timezone.now() - timedelta(minutes=11))
    shown = {q["id"]: q for q in api(pat).get(url).data["questions"]}
    assert shown[q2["id"]]["status"] == "failed" and "did not answer within 10 minutes" in shown[q2["id"]]["failure_reason"]


def test_only_people_who_can_open_the_task_can_stop_its_runs(agent, monkeypatch):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    run = services.start_run(issue, pat)
    q = services.ask_question(issue, pat, "What was the rent?")
    monkeypatch.setattr(services, "can_open_job", lambda user, issue: False)
    assert api(pat).post(f"/api/precheck/questions/{q.question_id}/stop/", {}, format="json").status_code == 403
    assert api(pat).post(f"/api/precheck/runs/{run.run_id}/stop/", {}, format="json").status_code == 403
    assert AIPrecheck.objects.get(pk=run.pk).status == "running"
