"""The PM side of the AI pre-check: setup, starting a run, receiving the agent's events,
decisions on findings, and the guarantees (roles, nothing overwritten, job never reviewed)."""
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
from apps.precheck.models import AIFeedback, AIFinding, AIPrecheck, ModelRun, folder_id_from
from apps.projects.models import Project
from apps.workflow.models import IssueType
from apps.workflow.services import provision_project_defaults

pytestmark = pytest.mark.django_db

SAMPLE = json.loads((Path(__file__).parent / "sample_result.json").read_text(encoding="utf-8"))
TOKEN = {"HTTP_X_PRECHECK_TOKEN": "test-token"}
FOLDER = "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUv?usp=sharing"


@pytest.fixture(autouse=True)
def service(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    calls = []
    monkeypatch.setattr(services, "_call_agent", lambda path, body: calls.append((path, body)) or {"status": "running"})
    return calls


@pytest.fixture
def user():
    return User.objects.create_user(username="pat", email="pat@example.com", password="x", display_name="Pat")


@pytest.fixture
def client_(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


@pytest.fixture
def issue(user):
    org = Organization.get_solo()
    client = Client.objects.create(organization=org, name="Acme")
    project = Project.objects.create(organization=org, key="Acme", name="Acme FY25", lead=user, client=client)
    provision_project_defaults(project)
    task, _ = IssueType.objects.get_or_create(name="Task", project=None)
    return Issue.objects.create(project=project, issue_type=task, summary="Year end accounts", status=project.workflow.statuses.first(), reporter=user)


def set_up(client_, issue):
    resp = client_.put(
        f"/api/precheck/jobs/{issue.key}/setup/",
        {"drive_folder_url": FOLDER, "direction_items": ["Agree the bank reconciliation", "  Confirm accruals   are complete ", ""]},
        format="json",
    )
    assert resp.status_code == 200, resp.data
    return resp.data


def completed(run_id, **changes):
    result = copy.deepcopy(SAMPLE)
    result.update(run_id=run_id, **changes)
    return {"run_id": run_id, "type": "ai_precheck.completed", "job_id": "1", "result": result}


def test_folder_links_are_understood():
    assert folder_id_from(FOLDER) == "1AbCdEfGhIjKlMnOpQrStUv"
    assert folder_id_from("https://drive.google.com/open?id=XYZ123abc_-9&x=1") == "XYZ123abc_-9"
    assert folder_id_from("1AbCdEfGhIjKlMnOpQrStUv") == "1AbCdEfGhIjKlMnOpQrStUv"
    assert folder_id_from("https://example.com/whatever") == ""


def test_setup_then_run(client_, issue, service):
    panel = client_.get(f"/api/precheck/jobs/{issue.key}/").data
    assert panel["setup"]["missing"] == ["drive_folder", "direction_note"] and panel["latest"] is None

    # Without a Drive folder nothing runs: the folder is never invented.
    resp = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json")
    assert resp.status_code == 400 and "Google Drive folder" in resp.data["detail"]
    assert client_.post(f"/api/precheck/jobs/{issue.key}/draft/").status_code == 400
    assert not service and not AIPrecheck.objects.exists()

    setup = set_up(client_, issue)
    assert setup["ready"] and setup["drive_folder_id"] == "1AbCdEfGhIjKlMnOpQrStUv"
    assert [(i["id"], i["text"], i["origin"]) for i in setup["direction_items"]] == [
        ("D1", "Agree the bank reconciliation", "person"), ("D2", "Confirm accruals are complete", "person")]

    resp = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json")
    assert resp.status_code == 201 and resp.data["status"] == "running"
    run_id = resp.data["run_id"]
    assert service == [("/precheck/runs", {"job_id": str(issue.id), "run_id": run_id})]
    # One at a time per job.
    assert client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").status_code == 409


def test_direction_refs_stay_stable_when_items_are_edited(client_, issue):
    set_up(client_, issue)
    resp = client_.put(
        f"/api/precheck/jobs/{issue.key}/setup/",
        {"direction_items": ["Check the tax computation", "Confirm accruals are complete"]}, format="json",
    )
    assert [(i["id"], i["text"]) for i in resp.data["direction_items"]] == [("D3", "Check the tax computation"), ("D2", "Confirm accruals are complete")]
    assert resp.data["drive_folder_id"]  # untouched
    bad = client_.put(f"/api/precheck/jobs/{issue.key}/setup/", {"drive_folder_url": "https://example.com/x"}, format="json")
    assert bad.status_code == 400


def test_agent_reads_the_job_with_the_service_token_only(client_, issue):
    set_up(client_, issue)
    url = f"/api/precheck/internal/jobs/{issue.id}/"
    assert APIClient().get(url).status_code == 403
    assert APIClient().get(url, HTTP_X_PRECHECK_TOKEN="wrong").status_code == 403
    assert client_.get(url).status_code == 403  # a signed-in user is not the service
    data = APIClient().get(url, **TOKEN).json()
    assert data["job_id"] == str(issue.id) and data["key"] == issue.key
    assert data["client_id"] == f"client-{issue.project.client_id}"
    assert data["drive_folder_id"] == "1AbCdEfGhIjKlMnOpQrStUv" and [i["id"] for i in data["direction_items"]] == ["D1", "D2"]
    assert data["knowledge_ids"] == []


def test_events_fill_the_job_card_and_never_touch_the_job(client_, issue):
    set_up(client_, issue)
    status_before = issue.status_id
    run_id = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").data["run_id"]
    agent = APIClient()
    assert agent.post("/api/precheck/internal/events/", {"run_id": run_id, "type": "ai_precheck.progress"}, format="json").status_code == 403

    progress = {"run_id": run_id, "type": "ai_precheck.progress", "stage": "read", "state": "done", "label": "5 documents, all new", "counts": {"documents": 5}}
    assert agent.post("/api/precheck/internal/events/", progress, format="json", **TOKEN).status_code == 200
    live = client_.get(f"/api/precheck/jobs/{issue.key}/").data["latest"]
    assert live["status"] == "running" and live["progress"][0]["label"] == "5 documents, all new"

    assert agent.post("/api/precheck/internal/events/", completed(run_id), format="json", **TOKEN).status_code == 200
    panel = client_.get(f"/api/precheck/jobs/{issue.key}/").data
    latest = panel["latest"]
    assert latest["status"] == "complete" and latest["verdict"] == SAMPLE["verdict"]
    assert latest["coverage"] == SAMPLE["coverage"] and len(latest["findings"]) == len(SAMPLE["findings"])
    assert set(latest["trail"]) == {"read", "checked", "compared", "judged", "verified"}
    with_proof = [f for f in latest["findings"] if f["evidence"]]
    assert with_proof and all(e["quote"] and e["file_name"] and e["location"] and e["drive_url"] for f in with_proof for e in f["evidence"])
    assert latest["usage"]["totals"] == SAMPLE["usage"]["totals"] and "cost_usd" in latest["usage"]

    # Audit: one ModelRun per model call, with versions and token usage.
    runs = ModelRun.objects.filter(precheck__run_id=run_id)
    assert runs.count() == len(SAMPLE["usage"]["calls"])
    assert sum(r.input_tokens for r in runs) == SAMPLE["usage"]["totals"]["input"]
    assert all(r.prompt_version and r.skill_versions for r in runs)

    # The service never marks the job reviewed or changes it in any way.
    issue.refresh_from_db()
    assert issue.status_id == status_before

    # A finished run is never overwritten.
    again = agent.post("/api/precheck/internal/events/", completed(run_id, verdict="ready", findings=[]), format="json", **TOKEN)
    assert again.status_code == 409
    assert AIPrecheck.objects.get(run_id=run_id).verdict == SAMPLE["verdict"]
    assert AIFinding.objects.filter(precheck__run_id=run_id).count() == len(SAMPLE["findings"])

    # A second run is a new record; the first is kept.
    second = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").data["run_id"]
    agent.post("/api/precheck/internal/events/", {"run_id": second, "type": "ai_precheck.failed", "reason": "Drive folder is not shared."}, format="json", **TOKEN)
    panel = client_.get(f"/api/precheck/jobs/{issue.key}/").data
    assert [r["status"] for r in panel["history"]] == ["failed", "complete"]
    assert panel["latest"]["failure_reason"] == "Drive folder is not shared."
    assert client_.get(f"/api/precheck/runs/{run_id}/").data["status"] == "complete"


def test_decisions_on_findings_are_one_click_and_undoable(client_, issue, user):
    set_up(client_, issue)
    run_id = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").data["run_id"]
    APIClient().post("/api/precheck/internal/events/", completed(run_id), format="json", **TOKEN)
    finding = client_.get(f"/api/precheck/jobs/{issue.key}/").data["latest"]["findings"][0]
    url = f"/api/precheck/findings/{finding['id']}/disposition/"
    assert finding["disposition"] is None
    resp = client_.post(url, {"disposition": "rejected"}, format="json")
    assert resp.status_code == 200 and resp.data["disposition"]["disposition"] == "rejected" and resp.data["disposition"]["by"] == "Pat"
    assert client_.post(url, {"disposition": "maybe"}, format="json").status_code == 400
    assert client_.post(url, {"disposition": "cleared"}, format="json").data["disposition"] is None  # undo
    assert client_.get(f"/api/precheck/jobs/{issue.key}/").data["latest"]["findings"][0]["disposition"] is None
    # Feedback is a history, not a field that gets overwritten.
    assert list(AIFeedback.objects.values_list("disposition", flat=True)) == ["rejected", "cleared"]


def test_only_people_who_can_open_the_job_can_see_or_run_its_precheck(client_, issue, monkeypatch):
    set_up(client_, issue)
    anonymous = APIClient()
    assert anonymous.get(f"/api/precheck/jobs/{issue.key}/").status_code == 401
    assert anonymous.post("/api/precheck/runs/", {"job": issue.key}, format="json").status_code == 401
    run_id = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").data["run_id"]
    # The pre-check follows the job's own access rule: if a user cannot open the job, nothing here answers.
    monkeypatch.setattr(services, "can_open_job", lambda user, issue: False)
    assert client_.get(f"/api/precheck/jobs/{issue.key}/").status_code == 403
    assert client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").status_code == 403
    assert client_.get(f"/api/precheck/runs/{run_id}/").status_code == 403
    assert client_.put(f"/api/precheck/jobs/{issue.key}/setup/", {"direction_items": []}, format="json").status_code == 403


def test_agent_down_gives_a_plain_failure(client_, issue, monkeypatch):
    set_up(client_, issue)

    def down(path, body):
        raise services.AgentUnavailable("connection refused")

    monkeypatch.setattr(services, "_call_agent", down)
    resp = client_.post("/api/precheck/runs/", {"job": issue.key}, format="json")
    assert resp.status_code == 201 and resp.data["status"] == "failed"
    assert "not reachable" in resp.data["failure_reason"]
    # It can be retried: a failed run does not block a new one.
    monkeypatch.setattr(services, "_call_agent", lambda path, body: {})
    assert client_.post("/api/precheck/runs/", {"job": issue.key}, format="json").data["status"] == "running"
