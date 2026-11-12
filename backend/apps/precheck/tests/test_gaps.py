"""The pre-check's missing-information gaps on the PM side (12 Nov 2026): the latest report is kept on
the task, what the agent's re-checks change is posted under the task's Pre-check stage, and a person
can ask for a re-check or finalise the case."""
import copy

import pytest
from rest_framework.test import APIClient

from apps.issues.models import Comment
from apps.precheck import services
from apps.precheck.models import JobFolder

from .test_direction_drafting import make_job
from .test_guide_milestones import SAMPLE, TOKEN, agent, api, finish, person  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db


def gap(gid, item, status, evidence=(), still_needed=""):
    return {"gap_id": gid, "case_id": "1", "field_or_requirement": gid, "group": "Applicant", "item": item, "description": item,
            "status": status, "still_needed": still_needed, "detected_in_doc_id": "precheck", "detected_at": "2026-11-12T00:00:00+00:00",
            "origin": "precheck", "evidence": list(evidence), "history": []}


def report(*gaps, provisional=True, finalized_at=None):
    keys = {"RESOLVED": "resolved", "PARTIALLY_RESOLVED": "partially_resolved", "CONFLICTING": "conflicting", "OPEN": "open",
            "CONFIRMED_MISSING": "confirmed_missing"}
    out = {"case_id": "1", "provisional": provisional, "finalized_at": finalized_at, "counts": {s: 0 for s in keys}}
    for k in keys.values():
        out[k] = []
    for g in gaps:
        out[keys[g["status"]]].append(g)
        out["counts"][g["status"]] += 1
    return out


PAYSLIP = {"doc_id": "f1", "doc_name": "Payslip summary.txt", "chunk_id": "c1", "page": None, "location": "line 2",
           "quoted_snippet": "Annual income: $50,000", "extracted_value": "50,000", "confidence": 0.95, "found_direction": "forward",
           "found_at": "2026-11-12T00:00:00+00:00", "drive_url": ""}


def gaps_event(issue, rep):
    return APIClient().post("/api/precheck/internal/events/", {"run_id": "gaps-x", "type": "ai_precheck.gaps_updated", "job_id": str(issue.id),
                                                                "report": rep}, format="json", **TOKEN)


def test_a_run_keeps_its_gap_report_on_the_task(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    run = services.start_run(issue, pat)
    finish(run.run_id)
    folder = JobFolder.objects.get(issue=issue)
    assert folder.gap_report == SAMPLE["precheck"]["gaps"] and folder.gap_report_at is not None
    r = api(pat).get(f"/api/precheck/jobs/{issue.key}/gaps/")
    assert r.status_code == 200 and r.data["provisional"] is True
    assert len(r.data["gaps"]) == sum(SAMPLE["precheck"]["gaps"]["counts"].values())
    # The run posts its own result; the gaps are not posted a second time.
    assert Comment.objects.filter(issue=issue).count() == 1


def test_the_agents_recheck_is_kept_and_what_changed_is_posted_under_the_precheck_stage(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    assert gaps_event(issue, report(gap("g1", "Applicant annual income", "OPEN"), gap("g2", "Bank statements", "OPEN"))).status_code == 200
    assert not Comment.objects.filter(issue=issue).exists()  # nothing found yet: nothing to say

    rep = report(gap("g1", "Applicant annual income", "RESOLVED", [PAYSLIP]),
                 gap("g2", "Bank statements", "PARTIALLY_RESOLVED", still_needed="the statement for June 2025"))
    assert gaps_event(issue, rep).status_code == 200
    c = Comment.objects.get(issue=issue)
    assert c.stage == "precheck" and c.author.is_agent
    text = str(c.body)
    assert "Found: Applicant annual income — Payslip summary.txt (Annual income: $50,000)" in text
    assert "Partly found: Bank statements — still needed: the statement for June 2025" in text
    summary = api(pat).get(f"/api/precheck/jobs/{issue.key}/gaps/").data
    assert [(g["item"], g["label"]) for g in summary["gaps"]] == [("Applicant annual income", "Found"), ("Bank statements", "Partly found")]

    # The same report again: nothing new to post.
    gaps_event(issue, rep)
    assert Comment.objects.filter(issue=issue).count() == 1

    # Settled: the case is final.
    final = report(gap("g1", "Applicant annual income", "RESOLVED", [PAYSLIP]), gap("g2", "Bank statements", "CONFIRMED_MISSING"),
                   provisional=False, finalized_at="2026-11-15T00:00:00+00:00")
    gaps_event(issue, final)
    last = Comment.objects.filter(issue=issue).order_by("-id").first()
    assert "the case is settled" in str(last.body) and "Confirmed missing: Bank statements" in str(last.body)
    assert api(pat).get(f"/api/precheck/jobs/{issue.key}/gaps/").data["provisional"] is False


def test_a_person_can_ask_for_a_recheck_or_finalise_the_case(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    assert api(pat).post(f"/api/precheck/jobs/{issue.key}/gaps/", {"action": "recheck"}, format="json").status_code == 202
    assert agent[-1] == ("/precheck/gaps/sweep", {"job_id": str(issue.id)})
    assert api(pat).post(f"/api/precheck/jobs/{issue.key}/gaps/", {"action": "finalize"}, format="json").status_code == 202
    assert agent[-1] == ("/precheck/gaps/finalize", {"job_id": str(issue.id)})
    assert api(pat).post(f"/api/precheck/jobs/{issue.key}/gaps/", {"action": "delete"}, format="json").status_code == 400


def test_an_event_for_an_unknown_task_or_a_bad_report_is_refused_or_ignored(agent):
    r = APIClient().post("/api/precheck/internal/events/", {"run_id": "gaps-x", "type": "ai_precheck.gaps_updated", "job_id": "999999",
                                                            "report": report()}, format="json", **TOKEN)
    assert r.status_code == 409
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    gaps_event(issue, {"not": "a report"})
    assert JobFolder.objects.get(issue=issue).gap_report == {}
    # The agent's token is required.
    bad = copy.deepcopy(TOKEN)
    bad["HTTP_X_PRECHECK_TOKEN"] = "wrong"
    assert APIClient().post("/api/precheck/internal/events/", {"type": "ai_precheck.gaps_updated", "job_id": str(issue.id), "report": report()},
                            format="json", **bad).status_code == 403
