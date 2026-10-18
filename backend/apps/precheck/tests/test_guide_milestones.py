"""After the pre-check: the preparation guide, results posted on the task's comments, the dates of
each stage (milestones), and Ask's answers labelled by where each point comes from."""
import copy
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.issues.models import Comment, Issue
from apps.precheck import services
from apps.precheck.models import AIPrecheck, TaskMilestone

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


def person(name):
    return User.objects.create_user(username=name, email=f"{name}@example.com", password="x", display_name=name.title())


def api(user):
    c = APIClient()
    c.force_authenticate(user=user)
    return c


def finish(run_id, **extra):
    result = copy.deepcopy(SAMPLE)
    result.update(run_id=run_id, **extra)
    r = APIClient().post("/api/precheck/internal/events/", {"run_id": run_id, "type": "ai_precheck.completed", "result": result}, format="json", **TOKEN)
    assert r.status_code == 200
    return result


def comment_text(c: Comment) -> str:
    def walk(node):
        return node.get("text", "") + " ".join(walk(n) for n in node.get("content", []))
    return walk(c.body)


GUIDE = {"summary": "Bank and rates first.", "decision": {"state": "guide", "label": "Preparation guide", "reason": "2 steps; 1 waits on information from the client."},
         "steps": [{"area": "Rates", "step": "Account for rates of 2,610.00 paid from ANZ to Auckland Council.", "check": "Agree to the rates statement.",
                    "waits_on_client": False, "sources": [], "flags": []},
                   {"area": "Loans", "step": "Record ASB interest once the annual summary arrives.", "check": "Agree to the loan summary.",
                    "waits_on_client": True, "sources": [], "flags": []}], "evidence": {}}


def test_a_guide_follows_the_precheck_and_is_posted_on_the_task(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    pre = services.start_run(issue, pat)
    finish(pre.run_id)
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/guide/", {}, format="json")
    assert r.status_code == 201 and r.data["kind"] == "guide" and agent[-1][1]["mode"] == "guide"
    sent = services.job_payload(Issue.objects.get(pk=issue.pk))["last_precheck"]
    assert sent["requests"] and sent["business_nature"]["label"]  # the guide is given the pre-check's result
    finish(r.data["run_id"], mode="guide", guide=GUIDE)
    run = AIPrecheck.objects.get(run_id=r.data["run_id"])
    assert run.guide["steps"][0]["area"] == "Rates"
    state = api(pat).get(f"/api/precheck/jobs/{issue.key}/guide/").data
    assert state["latest"]["guide"]["summary"] == "Bank and rates first." and state["has_precheck"]
    # The pre-check panel still shows pre-check runs only.
    assert api(pat).get(f"/api/precheck/jobs/{issue.key}/").data["latest"]["run_id"] == pre.run_id

    comments = list(Comment.objects.filter(issue=issue).order_by("created_at"))
    assert len(comments) == 2 and all(c.author == pat for c in comments)
    precheck_text, guide_text = comment_text(comments[0]), comment_text(comments[1])
    assert "AI pre-check — posted automatically" in precheck_text and "Information required from the client" in precheck_text
    assert "AI preparation guide — posted automatically" in guide_text
    assert "Rates: Account for rates of 2,610.00 paid from ANZ to Auckland Council." in guide_text and "(waits on the client)" in guide_text
    stamped = {m.kind: m for m in TaskMilestone.objects.filter(issue=issue)}
    assert set(stamped) == {"precheck", "guide"} and stamped["guide"].auto and stamped["guide"].on == timezone.localdate()


def test_a_result_is_posted_once_and_a_failed_run_not_at_all(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    run = services.start_run(issue, pat)
    result = finish(run.run_id)
    APIClient().post("/api/precheck/internal/events/", {"run_id": run.run_id, "type": "ai_precheck.completed", "result": result}, format="json", **TOKEN)
    assert Comment.objects.filter(issue=issue).count() == 1  # a repeated event changes nothing
    failed = services.start_run(issue, pat)
    APIClient().post("/api/precheck/internal/events/", {"run_id": failed.run_id, "type": "ai_precheck.failed", "reason": "x"}, format="json", **TOKEN)
    assert Comment.objects.filter(issue=issue).count() == 1 and TaskMilestone.objects.filter(issue=issue).count() == 1


def test_a_review_round_is_posted_too(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    run = services.start_run(issue, pat, kind=AIPrecheck.Kind.REVIEW)
    finish(run.run_id, mode="review", review={"summary": "One problem.", "findings": [
        {"ref": "", "area": "Comparatives", "fs_line": "Repairs", "issue": "Comparative wrong.", "why": "", "action": "", "severity": "high",
         "sources": [], "assumptions": [], "flags": []}], "resolved": [], "assumption_reviews": [], "checks": [], "evidence": {},
        "decision": {"state": "findings", "label": "Findings to address", "reason": "1 open"}, "counts": {"high": 1, "medium": 0, "low": 0}, "draft_fs": []})
    text = comment_text(Comment.objects.get(issue=issue))
    assert "AI review — posted automatically" in text and "R1 [high] Repairs: Comparative wrong." in text
    assert TaskMilestone.objects.get(issue=issue).kind == "review"


def test_people_stamp_checks_preparation_and_adjustments_with_their_dates(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    url = f"/api/precheck/jobs/{issue.key}/milestones/"
    assert api(pat).post(url, {"kind": "checks"}, format="json").data["on"] == timezone.localdate()
    earlier = (timezone.localdate() - timedelta(days=3)).isoformat()
    r = api(pat).post(url, {"kind": "adjustments", "on": earlier, "note": "Depreciation and accruals posted"}, format="json")
    assert r.status_code == 201 and str(r.data["on"]) == earlier and r.data["by"] == "Pat" and not r.data["auto"]
    future = (timezone.localdate() + timedelta(days=1)).isoformat()
    assert api(pat).post(url, {"kind": "preparation", "on": future}, format="json").status_code == 400
    assert api(pat).post(url, {"kind": "precheck"}, format="json").status_code == 400  # the AI's own stages are stamped by the AI
    listed = api(pat).get(url).data["milestones"]
    assert [m["label"] for m in listed] == ["Adjustments", "Checks"]  # in date order


def test_ask_keeps_where_each_point_came_from(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    q = api(pat).post(f"/api/precheck/jobs/{issue.key}/ask/", {"question": "Is the gain taxable?"}, format="json").data
    result = {"answer": "Possibly.", "status": "answered", "flags": [], "cost_usd": 0.01, "sources": [], "outside_job": False, "beyond_nz": True,
              "points": [{"text": "The bright-line test may apply.", "basis": "nz_standards_law", "reference": "Income Tax Act 2007, s CB 6AA", "sources": [], "flags": []},
                         {"text": "In Australia a CGT discount applies.", "basis": "general_knowledge", "reference": "Australian tax law", "sources": [], "flags": []}]}
    APIClient().post("/api/precheck/internal/events/", {"run_id": q["id"], "type": "ai_assistant.answered", "result": result}, format="json", **TOKEN)
    shown = api(pat).get(f"/api/precheck/jobs/{issue.key}/ask/").data["questions"][0]
    assert [p["basis"] for p in shown["points"]] == ["nz_standards_law", "general_knowledge"] and shown["beyond_nz"] and not shown["outside_job"]
