"""AI-drafted Direction Notes: what the AI may learn from, and how its draft lands on a job."""
import copy
import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Client
from apps.issues.models import Issue
from apps.orgs.models import Organization
from apps.precheck import services
from apps.precheck.models import AIFeedback, AIPrecheck, DirectionItem, JobFolder, ModelRun
from apps.projects.models import Project
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db

SAMPLE = json.loads((Path(__file__).parent / "sample_result.json").read_text(encoding="utf-8"))
TOKEN = {"HTTP_X_PRECHECK_TOKEN": "test-token"}


@pytest.fixture(autouse=True)
def service(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    calls = []
    monkeypatch.setattr(services, "_call_agent", lambda path, body: calls.append((path, body)) or {})
    return calls


@pytest.fixture
def user():
    return User.objects.create_user(username="pat", email="pat@example.com", password="x", display_name="Pat")


@pytest.fixture
def client_(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def make_job(user, client_name, key, summary="Year end accounts"):
    org = Organization.get_solo()
    client, _ = Client.objects.get_or_create(organization=org, name=client_name)
    project = Project.objects.filter(key=key).first()
    if project is None:
        project = Project.objects.create(organization=org, key=key, name=f"{client_name} {key}", lead=user, client=client)
        provision_project_defaults(project)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    issue = Issue.objects.create(project=project, issue_type=task, summary=summary, status=project.workflow.statuses.first(), reporter=user)
    JobFolder.objects.create(issue=issue, folder_id=f"folder-{issue.pk}", folder_url="x")
    return issue


def finished_run(issue, user, decisions=None):
    """A completed pre-check on `issue`, with a person's decision on some findings by title."""
    run = services.start_run(issue, user)
    result = copy.deepcopy(SAMPLE)
    result["run_id"] = run.run_id
    services.record_event({"run_id": run.run_id, "type": "ai_precheck.completed", "result": result})
    for title, decision in (decisions or {}).items():
        finding = run.findings.get(title=title)
        AIFeedback.objects.create(finding=finding, user=user, disposition=decision)
    return run


def open_titles():
    return [f["title"] for f in SAMPLE["findings"] if f["status"] != "addressed"]


def test_history_is_this_clients_past_jobs_and_decisions_only(user):
    last_year = make_job(user, "Acme", "AcmeFY24")
    this_year = make_job(user, "Acme", "AcmeFY25")
    other_client = make_job(user, "Zenith", "ZenFY24")
    DirectionItem.objects.create(issue=last_year, ref="D1", text="Agree the bank reconciliation to the ledger")
    DirectionItem.objects.create(issue=other_client, ref="D1", text="Zenith secret: confirm the escrow release")
    titles = open_titles()
    finished_run(last_year, user, {titles[0]: "accepted"})
    finished_run(other_client, user, {titles[0]: "rejected"})

    history = services.history_for(this_year)
    assert history["jobs_seen"] == 1
    assert [i["text"] for i in history["past_items"]] == ["Agree the bank reconciliation to the ledger"]
    assert history["past_items"][0]["used"] == 1
    decided = {f["title"]: f for f in history["past_findings"]}
    assert decided[titles[0]]["decision"] == "accepted" and decided[titles[0]]["where"] == "an earlier job"
    assert history["past_findings"][0]["decision"] == "accepted"  # what people confirmed comes first
    assert "Zenith" not in json.dumps(history) and "escrow" not in json.dumps(history)
    assert all(f["decision"] != "rejected" for f in history["past_findings"])  # that was another client's decision

    # A new job with nothing before it has an empty history; an undone decision counts as none.
    assert services.history_for(make_job(user, "Brand New", "NewFY25")) == {"past_items": [], "past_findings": [], "jobs_seen": 0}
    AIFeedback.objects.create(finding=AIPrecheck.objects.get(issue=last_year).findings.get(title=titles[0]), user=user, disposition="cleared")
    assert {f["title"]: f for f in services.history_for(this_year)["past_findings"]}[titles[0]]["decision"] == "none"

    # The job's own last run is part of what it learns from.
    finished_run(this_year, user, {titles[0]: "not_applicable"})
    mine = [f for f in services.history_for(this_year)["past_findings"] if f["where"] == "this job, last run"]
    assert any(f["decision"] == "not_applicable" for f in mine)

    # The agent receives it with the job.
    payload = APIClient().get(f"/api/precheck/internal/jobs/{this_year.id}/", **TOKEN).json()
    assert payload["history"]["jobs_seen"] == 1 and payload["direction_items"] == []


def test_a_job_without_a_direction_note_can_run_and_the_draft_lands_on_the_job(client_, user, service):
    issue = make_job(user, "Acme", "AcmeFY25")
    panel = client_.get(f"/api/precheck/jobs/{issue.key}/").data
    assert panel["setup"]["ready"] and panel["setup"]["missing"] == ["direction_note"]

    run_id = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").data["run_id"]
    assert service == [("/precheck/runs", {"job_id": str(issue.id), "run_id": run_id})]
    drafted = {
        "run_id": run_id, "type": "ai_precheck.directions_drafted", "final": False, "how": "model", "usage": [],
        "items": [
            {"id": "D1", "origin": "ai", "text": "Agree the debtors schedule to the trial balance", "reason": "Accepted on last year's job.", "basis": "history"},
            {"id": "D2", "origin": "ai", "text": "Explain the increase in trade debtors", "reason": "Moved 98% against last year.", "basis": "current"},
        ],
    }
    agent = APIClient()
    assert agent.post("/api/precheck/internal/events/", drafted, format="json", **TOKEN).status_code == 200
    items = client_.get(f"/api/precheck/jobs/{issue.key}/").data["setup"]["direction_items"]
    assert [(i["id"], i["origin"], i["basis"]) for i in items] == [("D1", "ai", "history"), ("D2", "ai", "current")]
    assert items[0]["reason"] == "Accepted on last year's job."
    assert AIPrecheck.objects.get(run_id=run_id).status == "running"  # the verification is still to come

    # A person edits one item: it becomes theirs; the untouched one stays AI-drafted with its reason.
    resp = client_.put(
        f"/api/precheck/jobs/{issue.key}/setup/",
        {"direction_items": ["Agree the debtors schedule to the trial balance", "Explain the movement in trade debtors and stock"]},
        format="json",
    )
    assert [(i["id"], i["origin"]) for i in resp.data["direction_items"]] == [("D1", "ai"), ("D3", "person")]
    assert resp.data["direction_items"][0]["reason"] == "Accepted on last year's job."


def test_draft_only_request(client_, user, service):
    issue = make_job(user, "Acme", "AcmeFY25")
    DirectionItem.objects.create(issue=issue, ref="D1", text="Agree the bank reconciliation to the ledger")
    resp = client_.post(f"/api/precheck/jobs/{issue.key}/draft/")
    assert resp.status_code == 201
    run_id = resp.data["run_id"]
    assert service == [("/precheck/runs", {"job_id": str(issue.id), "run_id": run_id, "mode": "draft"})]
    assert client_.get(f"/api/precheck/jobs/{issue.key}/").data["draft"]["status"] == "running"
    assert client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").status_code == 409  # one at a time

    usage = [{"node": "draft", "task_id": "draft", "model": "claude-sonnet-5-5", "calls": 1, "input": 2100, "output": 400, "cache_write": 0, "cache_read": 0}]
    event = {
        "run_id": run_id, "type": "ai_precheck.directions_drafted", "final": True, "how": "model", "usage": usage,
        "versions": {"prompt": "p1", "skills": {"direction-drafting": "1.0+abc"}},
        "items": [
            {"id": "D2", "text": "Confirm the accruals workpaper is signed off", "reason": "Workpapers are in the folder.", "basis": "standard"},
            {"id": "D3", "text": "agree the bank reconciliation to the ledger", "reason": "duplicate of what is there", "basis": "standard"},
            {"id": "D1", "text": "Reuses an id that is taken", "reason": "x", "basis": "standard"},
        ],
    }
    assert APIClient().post("/api/precheck/internal/events/", event, format="json", **TOKEN).status_code == 200
    panel = client_.get(f"/api/precheck/jobs/{issue.key}/").data
    assert [(i["id"], i["origin"]) for i in panel["setup"]["direction_items"]] == [("D1", "person"), ("D2", "ai")]
    # A draft is not a pre-check: it never shows as a result, but its cost is on record.
    assert panel["latest"] is None and panel["history"] == [] and panel["draft"]["status"] == "complete"
    audit = ModelRun.objects.get(precheck__run_id=run_id)
    assert (audit.node, audit.input_tokens, audit.skill_versions) == ("draft", 2100, {"direction-drafting": "1.0+abc"})
    assert client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").status_code == 201  # no longer blocked
