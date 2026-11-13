"""AFIT, 13 Nov 2026: staff give special notes to the AI agents on a task. They are kept with the task,
sent with the job to every agent they name, and changed or removed by their author or a lead."""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import ProjectMembership

from .test_direction_drafting import make_job
from .test_guide_milestones import TOKEN, agent, api, person  # noqa: F401 (fixture)

pytestmark = pytest.mark.django_db
SALE = "The client sold 12 Kauri Street in June 2025: treat this year as the year of sale."


@pytest.fixture
def job():
    rita = person("rita")
    issue = make_job(rita, "Smith", "SMITH")
    pat = person("pat")
    ProjectMembership.objects.create(project=issue.project, user=pat, role=ProjectMembership.Role.MEMBER)
    return issue, rita, pat


def test_a_note_is_added_and_sent_with_the_job_to_the_agents(job, agent):
    issue, rita, pat = job
    url = f"/api/precheck/jobs/{issue.key}/notes/"
    made = api(pat).post(url, {"text": SALE, "agents": []}, format="json")
    assert made.status_code == 201 and made.data["by"] == "Pat" and made.data["agents"] == []
    review_only = api(pat).post(url, {"text": "Check the depreciation recovery first.", "agents": ["review"]}, format="json").data
    assert api(pat).post(url, {"text": "x", "agents": []}, format="json").status_code == 400
    assert api(pat).post(url, {"text": "A note", "agents": ["payroll"]}, format="json").status_code == 400
    assert api(pat).post(url, {"text": "Every agent", "agents": ["precheck", "guide", "review", "ask"]}, format="json").data["agents"] == []

    assert [n["text"] for n in api(rita).get(url).data["notes"]] == [SALE, "Check the depreciation recovery first.", "Every agent"]
    assert all(n["can_edit"] for n in api(rita).get(url).data["notes"])  # the project's lead
    payload = APIClient().get(f"/api/precheck/internal/jobs/{issue.id}/", **TOKEN).json()
    assert payload["special_notes"][0] == {"id": made.data["id"], "text": SALE, "by": "Pat", "agents": []}
    assert payload["special_notes"][1]["agents"] == ["review"] and review_only["id"] == payload["special_notes"][1]["id"]


def test_only_its_author_or_a_lead_changes_or_removes_a_note(job):
    issue, rita, pat = job
    note = api(rita).post(f"/api/precheck/jobs/{issue.key}/notes/", {"text": SALE}, format="json").data
    url = f"/api/precheck/jobs/{issue.key}/notes/{note['id']}/"
    assert api(pat).patch(url, {"text": "Not a sale."}, format="json").status_code == 403
    assert api(pat).get(f"/api/precheck/jobs/{issue.key}/notes/").data["notes"][0]["can_edit"] is False
    mine = api(pat).post(f"/api/precheck/jobs/{issue.key}/notes/", {"text": "Keep the email short."}, format="json").data
    changed = api(pat).patch(f"/api/precheck/jobs/{issue.key}/notes/{mine['id']}/", {"text": "Keep the email very short.", "agents": ["precheck"]},
                             format="json")
    assert changed.status_code == 200 and changed.data["text"] == "Keep the email very short." and changed.data["agents"] == ["precheck"]
    assert api(rita).delete(f"/api/precheck/jobs/{issue.key}/notes/{mine['id']}/").status_code == 204  # the project's lead
    assert api(rita).delete(url).status_code == 204
    assert issue.agent_notes.count() == 0
