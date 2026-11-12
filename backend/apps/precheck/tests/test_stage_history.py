"""The task view's milestone bar (AFIT, 12 Nov 2026): each stage's state and date, the AI's results
posted under their stage, comments on a stage, and the AI's draft of a stage's completion note."""
import pytest

from apps.coordinator import llm
from apps.coordinator.models import AgentAction
from apps.issues import stages as issue_stages
from apps.issues.models import Comment, Issue
from apps.precheck import services
from apps.precheck import stages
from apps.precheck.models import AIPrecheck, TaskMilestone

from .test_direction_drafting import make_job
from .test_guide_milestones import agent, api, comment_text, finish, person  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db


def with_stage_subtasks(issue):
    issue_stages.create_default_subtasks(issue)
    return {s.summary: s for s in issue.subtasks.all()}


def done_status(issue):
    return issue.project.workflow.statuses.filter(category="done").first()


def by_key(rows):
    return {r["key"]: r for r in rows}


def test_the_bar_shows_five_stages_with_the_first_unfinished_one_active(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    subs = with_stage_subtasks(issue)
    r = api(pat).get(f"/api/precheck/jobs/{issue.key}/stages/")
    assert r.status_code == 200
    rows = r.data["stages"]
    assert [s["label"] for s in rows] == ["Pre-check", "Preparation", "Internal review", "Client review", "Dispatch"]
    assert [s["state"] for s in rows] == ["active", "upcoming", "upcoming", "upcoming", "upcoming"]
    # Each stage is due when its standard sub-task is; client review has no date.
    assert rows[1]["due_date"] == subs["Preparation"].due_date and rows[3]["due_date"] is None

    # The AI's pre-check being posted completes the pre-check; preparation becomes active.
    pre = services.start_run(issue, pat)
    finish(pre.run_id)
    rows = by_key(api(pat).get(f"/api/precheck/jobs/{issue.key}/stages/").data["stages"])
    assert rows["precheck"]["state"] == "done" and rows["precheck"]["done_on"] is not None
    assert rows["preparation"]["state"] == "active"

    # A finished sub-task completes its stage.
    subs["Preparation"].status = done_status(issue)
    subs["Preparation"].save()
    rows = by_key(api(pat).get(f"/api/precheck/jobs/{issue.key}/stages/").data["stages"])
    assert rows["preparation"]["state"] == "done" and rows["internal_review"]["state"] == "active"


def test_a_finished_task_is_dispatched_and_nothing_is_active(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    Issue.objects.filter(pk=issue.pk).update(status=done_status(issue))
    rows = by_key(stages.stage_states(Issue.objects.get(pk=issue.pk)))
    assert rows["dispatch"]["state"] == "done"
    assert all(r["state"] != "active" for r in rows.values())


def test_the_ai_results_are_posted_under_their_stage(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    pre = services.start_run(issue, pat)
    finish(pre.run_id)
    posted = Comment.objects.get(issue=issue)
    assert posted.stage == "precheck"
    r = api(pat).get(f"/api/issues/{issue.key}/comments/", {"stage": "precheck"})
    assert [c["id"] for c in r.data["results"]] == [posted.id] and r.data["results"][0]["stage"] == "precheck"
    assert api(pat).get(f"/api/issues/{issue.key}/comments/", {"stage": "preparation"}).data["results"] == []
    stage_rows = by_key(stages.stage_states(issue))
    assert stage_rows["precheck"]["comments"] == 1


def test_a_wp_agent_reconciliation_is_posted_under_preparation_without_a_milestone(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    run = services.start_run(issue, pat, kind=AIPrecheck.Kind.GST, options={"drive_link": "x"})
    gst = {"status": "Reconciled subject to corrections", "summary": "GST agrees to the control account after one correction.",
           "exceptions": [{"severity": "review", "text": "March return filed late", "next_evidence": "IRD statement"}],
           "corrections": [{"title": "Reclassify import GST", "status": "proposed"}], "conclusions": []}
    finish(run.run_id, gst=gst, workbook_b64="")
    posted = Comment.objects.get(issue=issue)
    assert posted.stage == "preparation"
    text = comment_text(posted)
    assert "WP Agent: GST reconciliation" in text and "March return filed late" in text and "Reclassify import GST" in text
    assert not TaskMilestone.objects.filter(issue=issue).exists()


def test_a_person_comments_on_a_stage(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    body = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Client review done."}]}]}
    r = api(pat).post(f"/api/issues/{issue.key}/comments/", {"body": body, "stage": "client_review"}, format="json")
    assert r.status_code == 201 and r.data["stage"] == "client_review"
    bad = api(pat).post(f"/api/issues/{issue.key}/comments/", {"body": body, "stage": "lunch"}, format="json")
    assert bad.status_code == 400
    # A comment without a stage is a general one, as before.
    plain = api(pat).post(f"/api/issues/{issue.key}/comments/", {"body": body}, format="json")
    assert plain.status_code == 201 and plain.data["stage"] == ""


def test_the_ai_drafts_a_completion_note_from_the_stages_results(agent, monkeypatch):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    pre = services.start_run(issue, pat)
    finish(pre.run_id)
    seen = {}

    def fake(system, messages, schema, **kwargs):
        seen["facts"] = messages[0]["content"]
        return {"note": "Pre-check complete.\n- Two items still to come from the client."}, 0.002

    monkeypatch.setattr(llm, "structured", fake)
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/stage-note/", {"stage": "precheck"}, format="json")
    assert r.status_code == 200 and r.data["ai"] is True
    assert r.data["text"].startswith("Pre-check complete.")
    # The model is given the stage's latest AI result, worked out by code.
    assert "Stage being completed: Pre-check" in seen["facts"] and "Latest Pre-check" in seen["facts"]
    # Nothing is posted; the call is counted against the daily AI cap.
    assert Comment.objects.filter(issue=issue).count() == 1
    assert AgentAction.objects.get(trigger="stage_note").cost_usd == 0.002


def test_without_the_model_code_writes_the_note_from_the_same_facts(agent, monkeypatch):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")

    def unavailable(*args, **kwargs):
        raise llm.Unavailable("no API key")

    monkeypatch.setattr(llm, "structured", unavailable)
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/stage-note/", {"stage": "preparation"}, format="json")
    assert r.status_code == 200 and r.data["ai"] is False
    # Not finished yet, so the note says where it stands rather than calling it complete.
    assert r.data["text"].startswith("Preparation: not started, no due date.")
    assert "- The AI has not run for preparation on this task yet." in r.data["text"]
    assert "- Time logged on the task: 0h." in r.data["text"]

    # A finished stage is recorded as complete, and earlier comments are not repeated in the note.
    pat_body = {"type": "doc", "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Checked the bank."}]}]}
    api(pat).post(f"/api/issues/{issue.key}/comments/", {"body": pat_body, "stage": "precheck"}, format="json")
    TaskMilestone.objects.create(issue=issue, kind="checks", on=issue.created_at.date(), by=pat)
    note = api(pat).post(f"/api/precheck/jobs/{issue.key}/stage-note/", {"stage": "precheck"}, format="json").data
    assert note["text"].startswith("Pre-check complete (done on ") and "Checked the bank." not in note["text"]
    assert any("Checked the bank." in f for f in note["facts"])  # still given to the model
    assert api(pat).post(f"/api/precheck/jobs/{issue.key}/stage-note/", {"stage": "lunch"}, format="json").status_code == 400
