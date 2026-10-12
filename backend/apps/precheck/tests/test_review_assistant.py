"""The review on the PM side: assumptions with their history, review rounds whose findings keep
one ref across rounds, the reviewer's responses (each kept), something the AI missed, and a
review only a person completes."""
import copy
import json
from pathlib import Path

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Issue
from apps.precheck import services
from apps.precheck.models import AIPrecheck, ReviewFinding, ReviewResponse

from .test_direction_drafting import make_job

pytestmark = pytest.mark.django_db

SAMPLE = json.loads((Path(__file__).parent / "sample_result.json").read_text(encoding="utf-8"))
TOKEN = {"HTTP_X_PRECHECK_TOKEN": "test-token"}


@pytest.fixture
def agent(settings, monkeypatch):
    settings.PRECHECK_SERVICE_TOKEN = "test-token"
    calls = []
    monkeypatch.setattr(services, "_call_agent", lambda path, body: calls.append((path, body)) or {})
    return calls


def person(name, staff=False):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title(), is_staff=staff)


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def finding(ref, issue, severity="medium", fs_line="Repairs and maintenance"):
    return {"ref": ref, "area": "Repairs", "fs_line": fs_line, "issue": issue, "why": "Because.", "action": "Fix it.", "severity": severity,
            "sources": [{"id": "S3", "label": "Draft: Repairs 9,850", "evidence_id": "E-1"}], "assumptions": ["A1"], "flags": []}


def finish_round(run_id, findings, resolved=()):
    result = copy.deepcopy(SAMPLE)
    result.update(run_id=run_id, mode="review", review={
        "summary": "Round done.", "findings": findings, "resolved": [{"ref": r, "reason": "Shown fixed.", "sources": []} for r in resolved],
        "assumption_reviews": [], "decision": {"state": "findings" if findings else "clear", "label": "x", "reason": "x"},
        "counts": {"high": 0, "medium": len(findings), "low": 0}, "evidence": {}, "draft_fs": [], "checks": []})
    r = APIClient().post("/api/precheck/internal/events/", {"run_id": run_id, "type": "ai_precheck.completed", "result": result}, format="json", **TOKEN)
    assert r.status_code == 200


def test_assumptions_are_recorded_edited_with_history_and_withdrawn(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    url = f"/api/precheck/jobs/{issue.key}/assumptions/"
    r = api(pat).post(url, {"area": "expenses", "fs_line": "Repairs and maintenance", "amount": "$9,850.00",
                            "judgement": "Hot water cylinder replacement treated as a repair.", "basis": "Like-for-like.", "evidence": "Kauri Plumbing invoice"},
                      format="json")
    assert r.status_code == 201 and r.data["ref"] == "A1" and r.data["amount"] == "9850.00"
    assert api(pat).post(url, {"area": "nonsense", "judgement": "x"}, format="json").status_code == 400
    assert api(pat).post(url, {"area": "other"}, format="json").status_code == 400  # no judgement
    a2 = api(pat).post(url, {"area": "private_use", "judgement": "Home office 20% of the house."}, format="json").data
    assert a2["ref"] == "A2"
    edited = api(pat).patch(f"/api/precheck/assumptions/{r.data['id']}/", {"judgement": "Treated as capital after all."}, format="json").data
    assert edited["judgement"] == "Treated as capital after all." and edited["history"][0]["judgement"].startswith("Hot water")
    api(pat).patch(f"/api/precheck/assumptions/{a2['id']}/", {"status": "withdrawn"}, format="json")
    payload = services.job_payload(Issue.objects.get(pk=issue.pk))["review"]
    assert [a["ref"] for a in payload["assumptions"]] == ["A1"] and payload["assumptions"][0]["area"] == "Expenses"


def test_a_review_round_keeps_refs_across_rounds_and_records_every_response(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/review/runs/", {}, format="json")
    assert r.status_code == 201 and r.data["kind"] == "review" and agent[-1][1]["mode"] == "review"
    finish_round(r.data["run_id"], [finding("", "Repairs look capital."), finding("", "Comparative wrong.", "high", "Interest")])
    rows = {f.text: f for f in ReviewFinding.objects.filter(issue=issue)}
    assert {f.ref for f in rows.values()} == {"R1", "R2"}
    run = AIPrecheck.objects.get(run_id=r.data["run_id"])
    assert [f["ref"] for f in run.review["findings"]] == ["R1", "R2"]  # the round's output carries the refs given

    r1, r2 = rows["Repairs look capital."], rows["Comparative wrong."]
    respond = lambda f, body: api(pat).post(f"/api/precheck/review-findings/{f.id}/respond/", body, format="json")  # noqa: E731
    assert respond(r1, {"response": "not_an_issue"}).status_code == 400  # needs a reason
    assert respond(r1, {"response": "not_an_issue", "note": "It is a like-for-like repair."}).data["status"] == "closed"
    assert respond(r2, {"response": "fixed", "note": ""}).data["response"] == "fixed"
    sent = services.job_payload(Issue.objects.get(pk=issue.pk))["review"]
    assert sent["round"] == 2 and {(f["ref"], f["status"], f["response"]) for f in sent["findings"]} == {("R1", "closed", "not_an_issue"), ("R2", "open", "fixed")}

    # Round 2: R2 is still wrong, a new problem appears, nothing raises R1 again (the agent drops it).
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/review/runs/", {}, format="json")
    finish_round(r.data["run_id"], [finding("R2", "Comparative still wrong.", "high", "Interest"), finding("", "Home office has no basis.")])
    r2.refresh_from_db()
    assert r2.status == "open" and r2.text == "Comparative still wrong." and r2.first_run.run_id != r2.last_run.run_id
    assert ReviewFinding.objects.get(issue=issue, ref="R3").text == "Home office has no basis."
    # Round 3: R2 shown fixed.
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/review/runs/", {}, format="json")
    finish_round(r.data["run_id"], [], resolved=["R2", "R1"])
    r2.refresh_from_db()
    r1.refresh_from_db()
    assert r2.status == "resolved" and r2.resolved_reason == "Shown fixed." and r1.status == "closed"  # a closed finding stays closed
    assert ReviewResponse.objects.filter(finding__issue=issue).count() == 2

    state = api(pat).get(f"/api/precheck/jobs/{issue.key}/review/").data
    assert state["rounds_done"] == 3 and state["latest"]["review"]["summary"] == "Round done."
    assert [f["ref"] for f in state["findings"]] == ["R1", "R2", "R3"] and state["findings"][0]["responses"][0]["note"] == "It is a like-for-like repair."
    # The pre-check panel shows pre-check runs only.
    assert api(pat).get(f"/api/precheck/jobs/{issue.key}/").data["latest"] is None


def test_something_the_ai_missed_and_a_draft_placed_on_the_card(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/review/missed/", {"area": "GST", "fs_line": "GST payable", "issue": "GST on the sale is not accounted for."},
                      format="json")
    assert r.status_code == 201 and r.data["ref"] == "R1" and r.data["origin"] == "person" and r.data["status"] == "open"
    assert services.job_payload(Issue.objects.get(pk=issue.pk))["review"]["findings"][0]["origin"] == "person"
    api(pat).put(f"/api/precheck/jobs/{issue.key}/setup/", {"key_paths": {"draft_fs": "2026/Draft FS.pdf"}}, format="json")
    assert services.job_payload(Issue.objects.get(pk=issue.pk))["key_paths"] == {"draft_fs": "2026/Draft FS.pdf"}


def test_only_the_reviewer_completes_the_review_and_open_high_findings_need_a_reason(agent):
    pat, rita, sam = person("pat"), person("rita"), person("sam")
    issue = make_job(pat, "Smith", "SmithRent")
    issue.reviewer = rita
    issue.save()
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/review/runs/", {}, format="json")
    finish_round(r.data["run_id"], [finding("", "Comparative wrong.", "high")])
    url = f"/api/precheck/jobs/{issue.key}/review/complete/"
    assert api(sam).post(url, {}, format="json").status_code == 403  # not the reviewer, not a lead
    assert api(rita).post(url, {}, format="json").status_code == 400  # a high finding is open
    done = api(rita).post(url, {"note": "Partner accepted the difference; adjusted next year."}, format="json").data
    assert done["status"] == "complete" and done["completed_by"] == "Rita"
    assert api(pat).post(f"/api/precheck/jobs/{issue.key}/review/runs/", {}, format="json").status_code == 409  # complete: no more rounds
    assert api(rita).post(url, {"reopen": True}, format="json").data["status"] == "in_progress"
    assert Issue.objects.get(pk=issue.pk).status_id == issue.status_id  # the task itself is never changed
