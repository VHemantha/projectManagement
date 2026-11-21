"""AFIT, 20 Nov 2026: pre-check policies, written by the accountants for a client, a client group, a
location or every task; sent with each task to the agent, which checks every point against them; and
revised by the AI from people's feedback. Also: the agent's memory of a task is freed three days after
the task's final review."""
from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.precheck import policies as PL
from apps.precheck import services
from apps.precheck.models import JobFolder, PolicyFeedback, PrecheckPolicy, ReviewSession

from .test_direction_drafting import finished_run, make_job
from .test_guide_milestones import TOKEN, api, person

pytestmark = pytest.mark.django_db
URL = "/api/precheck/policies/"


@pytest.fixture
def calls(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    made = []
    monkeypatch.setattr(services, "_call_agent", lambda path, body, **kw: made.append((path, body)) or {})
    return made


@pytest.fixture
def job():
    rita = person("rita")
    issue = make_job(rita, "RWCA", "RWCA")
    issue.group = "Lummis group"
    issue.save(update_fields=["group"])
    folder = issue.drive_folder
    folder.accountant_settings = {"location": "Auckland"}
    folder.save(update_fields=["accountant_settings"])
    return issue, rita


def policy(user, **fields):
    data = {"scope": "all", "title": "A policy", "text": "Do this.", **fields}
    r = api(user).post(URL, data, format="json")
    assert r.status_code == 201, r.data
    return r.data


def payload(issue):
    return APIClient().get(f"/api/precheck/internal/jobs/{issue.id}/", **TOKEN).json()


def test_policies_are_written_for_a_client_a_group_a_location_or_every_task_and_sent_with_the_tasks_they_apply_to(job, calls):
    issue, rita = job
    client = issue.project.client
    mine = [
        policy(rita, scope="client", client_id=client.id, title="RWCA: no rates", text="Do not ask RWCA clients for council rates."),
        policy(rita, scope="group", group="lummis group", title="Lummis: one email", text="Ask the Lummis group for everything in one email."),
        policy(rita, scope="location", location="Auckland", title="Auckland rates", text="Auckland Council rates come from the council website."),
        policy(rita, scope="all", title="Bank statements", text="Always ask for the bank statements of every account."),
    ]
    policy(rita, scope="group", group="Jordan group", title="Not this group", text="Not for this task.")
    policy(rita, scope="location", location="Wellington", title="Not this place", text="Not for this task.")
    other = make_job(rita, "EpsomTax", "EPSOM")
    policy(rita, scope="client", client_id=other.project.client_id, title="Not this client", text="Not for this task.")
    policy(rita, scope="all", precheck_type="investment", title="Investment only", text="For investment checks only.")
    sent = payload(issue)
    assert sent["group"] == "Lummis group"
    titles = [p["title"] for p in sent["policies"]]
    # The narrowest first; with the type of check left to the AI, a policy for one type comes too, saying so.
    assert titles == ["RWCA: no rates", "Lummis: one email", "Auckland rates", "Bank statements", "Investment only"]
    assert sent["policies"][0]["scope_label"] == "Client: RWCA"
    assert sent["policies"][4]["text"].startswith("(For Investment checks.)")
    folder = issue.drive_folder
    folder.precheck_type = "residential_rental"
    folder.save(update_fields=["precheck_type"])
    assert "Investment only" not in [p["title"] for p in payload(issue)["policies"]]
    listed = api(rita).get(URL, {"task": issue.key}).data
    assert {p["id"] for p in listed["policies"]} == {p["id"] for p in mine}
    assert "Lummis group" in listed["groups"] and "Auckland" in listed["locations"]


def test_a_policy_needs_who_it_is_for_a_title_and_what_to_do(job, calls):
    _, rita = job
    for bad, field in (({"scope": "client"}, "client_id"), ({"scope": "group"}, "group"), ({"scope": "location"}, "location"),
                       ({"scope": "nowhere"}, "scope"), ({"scope": "all", "title": ""}, "title"), ({"scope": "all", "text": " "}, "text")):
        r = api(rita).post(URL, {"title": "T", "text": "Do.", **bad}, format="json")
        assert r.status_code == 400 and field in r.data, bad


def test_only_its_author_a_lead_or_an_admin_changes_a_policy_and_each_wording_is_kept(job, calls):
    _, rita = job
    p = policy(rita, title="Rates", text="Ask for the rates notice.")
    pat = person("pat")
    assert api(pat).patch(f"{URL}{p['id']}/", {"text": "Never."}, format="json").status_code == 403
    changed = api(rita).patch(f"{URL}{p['id']}/", {"text": "Ask for the rates notice, or the council's statement."}, format="json").data
    assert changed["version"] == 2 and changed["history"][0]["text"] == "Ask for the rates notice." and changed["history"][0]["changed_by"] == "Rita"
    off = api(rita).patch(f"{URL}{p['id']}/", {"active": False}, format="json").data
    assert off["active"] is False and off["version"] == 2
    assert api(pat).delete(f"{URL}{p['id']}/").status_code == 403
    assert api(rita).delete(f"{URL}{p['id']}/").status_code == 204


def test_switched_off_policies_are_not_sent(job, calls):
    issue, rita = job
    p = policy(rita, title="Rates", text="Ask for the rates notice.")
    api(rita).patch(f"{URL}{p['id']}/", {"active": False}, format="json")
    assert payload(issue)["policies"] == []


def test_feedback_on_a_policy_has_the_ai_revise_it_keeping_the_old_wording(job, calls):
    issue, rita = job
    p = policy(rita, title="Rates", text="Ask for the full year's rates notice.")
    pat = person("pat")
    from apps.projects.models import ProjectMembership

    ProjectMembership.objects.create(project=issue.project, user=pat, role=ProjectMembership.Role.MEMBER)
    fb = api(pat).post(f"{URL}{p['id']}/feedback/", {"text": "Sold properties only need the settlement statement.", "task": issue.key,
                                                     "context": "Council rates for 12 Kauri Street"}, format="json")
    assert fb.status_code == 201 and fb.data["status"] == "revising" and fb.data["task"] == issue.key
    path, body = calls[-1]
    assert path == "/precheck/policies/revise" and body["feedback"].startswith("Sold properties") and body["context"].startswith("Council rates")
    event = {"run_id": f"policy-{fb.data['id']}", "type": "ai_policy.revised",
             "result": {"title": "Rates", "text": "Ask for the full year's rates notice; for a sold property, the settlement statement.",
                        "summary": "Added sold properties."}}
    assert APIClient().post("/api/precheck/internal/events/", event, format="json", **TOKEN).status_code == 200
    revised = api(rita).get(f"{URL}{p['id']}/").data
    assert revised["version"] == 2 and revised["text"].endswith("the settlement statement.")
    assert revised["history"][0]["text"] == "Ask for the full year's rates notice." and "Pat's feedback" in revised["history"][0]["why"]
    assert revised["feedback"][0]["status"] == "revised" and revised["feedback"][0]["summary"] == "Added sold properties."
    # A late or repeated event changes nothing.
    APIClient().post("/api/precheck/internal/events/", event, format="json", **TOKEN)
    assert PrecheckPolicy.objects.get(pk=p["id"]).version == 2


def test_feedback_when_the_agent_is_away_says_so_and_leaves_the_policy(job, monkeypatch):
    _, rita = job
    p = policy(rita)

    def away(*a, **kw):
        raise services.AgentUnavailable("down")

    monkeypatch.setattr(services, "_call_agent", away)
    fb = api(rita).post(f"{URL}{p['id']}/feedback/", {"text": "Shorter please."}, format="json").data
    assert fb["status"] == "failed" and "could not be reached" in fb["summary"]
    assert PolicyFeedback.objects.get(pk=fb["id"]).policy.version == 1


def test_the_location_is_a_precheck_setting_on_the_task(job, calls):
    issue, rita = job
    r = api(rita).put(f"/api/precheck/jobs/{issue.key}/setup/", {"settings": {"location": "  Christchurch "}}, format="json")
    assert r.status_code == 200 and r.data["settings"]["location"] == "Christchurch"
    assert payload(issue)["settings"]["location"] == "Christchurch"


def test_a_tasks_memory_is_freed_three_days_after_its_final_review(job, calls):
    issue, rita = job
    run = finished_run(issue, rita)
    now = timezone.now()
    assert PL.due_for_flush(now) == []  # still being worked on
    session = ReviewSession.objects.create(issue=issue, status="complete", completed_at=now - timedelta(days=2))
    run.created_at = now - timedelta(days=5)
    run.save(update_fields=["created_at"])
    type(run).objects.filter(pk=run.pk).update(created_at=now - timedelta(days=5))
    assert PL.due_for_flush(now) == []  # only two days since the final review
    session.completed_at = now - timedelta(days=3, minutes=1)
    session.save(update_fields=["completed_at"])
    assert [f.issue_id for f in PL.due_for_flush(now)] == [issue.id]
    assert PL.flush_due(now) == {"flushed": 1, "failed": 0}
    assert calls[-1] == ("/precheck/jobs/flush", {"job_id": str(issue.id), "client_id": services.client_scope(issue)})
    assert JobFolder.objects.get(issue=issue).memory_flushed_at is not None
    assert PL.due_for_flush(now + timedelta(days=1)) == []  # freed, and not run since


def test_a_task_moved_to_a_done_stage_counts_as_its_final_review(job, calls):
    issue, rita = job
    run = finished_run(issue, rita)
    long_ago = timezone.now() - timedelta(days=10)
    type(run).objects.filter(pk=run.pk).update(created_at=long_ago)
    done = issue.project.workflow.statuses.filter(category="done").first()
    type(issue).objects.filter(pk=issue.pk).update(status=done, resolved_at=long_ago)
    from django.core.management import call_command
    from io import StringIO

    out = StringIO()
    call_command("flush_job_memory", stdout=out)
    assert "Freed the memory of 1 task(s)" in out.getvalue()
