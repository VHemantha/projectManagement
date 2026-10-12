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


def test_a_question_is_answered_in_the_background_and_kept_with_its_sources(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    url = f"/api/precheck/jobs/{issue.key}/ask/"
    assert api(pat).post(url, {"question": " "}, format="json").status_code == 400
    q = api(pat).post(url, {"question": "How much was 43 Te Wharo Drive sold for?"}, format="json").data
    assert q["status"] == "pending" and agent[-1][0] == "/precheck/ask" and agent[-1][1]["question"] == "How much was 43 Te Wharo Drive sold for?"
    answer = {"answer": "It sold for $891,000.00.", "status": "answered", "flags": [], "cost_usd": 0.01,
              "sources": [{"id": "K1", "label": "Settlement Statement.pdf, page 1", "how": 'words "Settlement"', "evidence": {"quote": "Purchase price 891,000.00"}}]}
    r = APIClient().post("/api/precheck/internal/events/", {"run_id": q["id"], "type": "ai_assistant.answered", "result": answer}, format="json", **TOKEN)
    assert r.status_code == 200
    # A late or repeated answer changes nothing.
    assert APIClient().post("/api/precheck/internal/events/", {"run_id": q["id"], "type": "ai_assistant.failed", "reason": "x"},
                            format="json", **TOKEN).status_code == 409
    shown = api(pat).get(url).data["questions"]
    assert shown[0]["answer"] == "It sold for $891,000.00." and shown[0]["sources"][0]["label"].startswith("Settlement Statement")
    # A follow-up carries the conversation so far.
    api(pat).post(url, {"question": "And when did it settle?"}, format="json")
    assert agent[-1][1]["history"] == [{"question": "How much was 43 Te Wharo Drive sold for?", "answer": "It sold for $891,000.00."}]
    # Access follows the task (today every signed-in member may open every task); signed out, no.
    assert APIClient().post(url, {"question": "What is the rent?"}, format="json").status_code in (401, 403)


def test_a_correction_teaches_the_ai_and_the_rule_is_drafted_in_the_background(agent):
    from apps.precheck.models import PrecheckLesson

    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/review/runs/", {}, format="json")
    finish_round(r.data["run_id"], [finding("", "Show rent by property.", "low", "Rental income")])
    f = ReviewFinding.objects.get(issue=issue, ref="R1")
    api(pat).post(f"/api/precheck/review-findings/{f.id}/respond/", {"response": "agree"}, format="json")
    assert not PrecheckLesson.objects.exists()  # agreeing teaches nothing
    api(pat).post(f"/api/precheck/review-findings/{f.id}/respond/", {"response": "not_an_issue", "note": "The client owns one property only."}, format="json")
    lesson = PrecheckLesson.objects.get()
    assert (lesson.source, lesson.kind, lesson.scope, lesson.status, lesson.finding_id) == ("review", "not_needed", "client", "active", f.id)
    path, body = agent[-1]
    assert path == "/precheck/learn" and body["lesson_id"] == lesson.id and body["context"]["issue"] == "Show rent by property."
    assert lesson.drafting == "drafting"

    rule = {"title": "One property: rent in one line", "when": "The client owns a single rental property.",
            "do": "Do not ask for rental income to be split by property.", "why": "There is nothing to split."}
    assert APIClient().post("/api/precheck/internal/events/", {"run_id": f"lesson-{lesson.id}", "type": "ai_learning.drafted", "result": rule},
                            format="json", **TOKEN).status_code == 200
    lesson.refresh_from_db()
    assert lesson.drafting == "drafted" and lesson.rule_do.startswith("Do not ask")
    sent = services.job_payload(Issue.objects.get(pk=issue.pk))["lessons"]
    assert sent[0]["rule"]["when"] == "The client owns a single rental property." and sent[0]["source"] == "review"

    # Something the AI missed teaches too.
    api(pat).post(f"/api/precheck/jobs/{issue.key}/review/missed/", {"issue": "GST on the sale is not accounted for."}, format="json")
    assert PrecheckLesson.objects.filter(kind="missed", source="review").exists()


def test_wider_rules_wait_for_a_lead_and_reach_only_their_project_team_or_firm(agent):
    from apps.precheck.models import PrecheckLesson
    from apps.teams.models import Team

    pat, sam, boss = person("pat"), person("sam"), person("boss", staff=True)  # pat leads the projects; sam does not
    a1 = make_job(pat, "Smith", "SmithRent")
    a2 = make_job(pat, "Smith", "SmithRent", summary="Another task in the same project")
    other = make_job(pat, "Jones", "JonesRent")
    team = Team.objects.create(name="Rentals", organization=a1.project.organization)
    for issue in (a1, other):
        issue.project.client.team = team
        issue.project.client.save()
    url = f"/api/precheck/jobs/{a1.key}/lessons/"
    proj = api(sam).post(url, {"kind": "other", "note": "Always ask for the bond lodgement receipt.", "scope": "project"}, format="json").data
    assert proj["status"] == "pending" and proj["scope_label"] == "This project"
    assert api(sam).post(url, {"kind": "other", "note": "x x x x x", "scope": "galaxy"}, format="json").status_code == 400
    teamwide = api(boss).post(url, {"kind": "other", "note": "Check body corporate levy statements.", "scope": "team"}, format="json").data
    assert teamwide["status"] == "active"  # a lead or admin teaching it: no wait
    api(boss).patch(f"/api/precheck/lessons/{proj['id']}/", {"status": "active"}, format="json")

    notes = lambda i: {l["note"] for l in services.job_payload(Issue.objects.get(pk=i.pk))["lessons"]}  # noqa: E731
    assert notes(a2) == {"Always ask for the bond lodgement receipt.", "Check body corporate levy statements."}  # same project and team
    assert notes(other) == {"Check body corporate levy statements."}  # same team, another project
    assert PrecheckLesson.objects.filter(scope="project", status="active").count() == 1
