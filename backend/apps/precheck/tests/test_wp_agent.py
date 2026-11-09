"""The WP Agent on the task card (AFIT, 8 Nov 2026): the GST reconciliation is started with its Drive link
and job settings, the agent's result and workpaper are kept with the run, and the workpaper downloads."""
import base64
import copy
import io

import pytest
from openpyxl import Workbook, load_workbook

from apps.precheck import services
from apps.precheck.models import AIPrecheck, TaskMilestone

from .test_direction_drafting import make_job
from .test_guide_milestones import SAMPLE, TOKEN, agent, api, person  # noqa: F401  (shared fixtures)

pytestmark = pytest.mark.django_db
FORM = {"drive_link": "https://drive.google.com/drive/folders/1AbCdEfGhIjKlMnOpQrStUv", "ap_link": "",
        "setup": {"entity": "Smith Rentals Ltd", "balance_date": "2026-03-31", "fy_start": "2026-04-01", "basis": "payments", "frequency": "two_monthly",
                  "first_year": False, "gst_accounts": "GST"}}


def workbook_bytes() -> bytes:
    wb = Workbook()
    wb.active.title = "L1 GST reconciliation"
    wb.active["A3"] = "GST reconciliation"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def complete(run_id, gst):
    from rest_framework.test import APIClient

    result = copy.deepcopy(SAMPLE)
    result.update(run_id=run_id, mode="gst", verdict="ready_with_exceptions", readiness="Reconciled subject to corrections",
                  summary="Reconciled subject to corrections.", findings=[], evidence=[], gst=gst,
                  workbook_b64=base64.b64encode(workbook_bytes()).decode())
    r = APIClient().post("/api/precheck/internal/events/", {"run_id": run_id, "type": "ai_precheck.completed", "result": result}, format="json", **TOKEN)
    assert r.status_code == 200


def test_the_wp_agent_runs_with_its_link_and_settings_and_keeps_the_workpaper(agent):
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    first = api(pat).get(f"/api/precheck/jobs/{issue.key}/wp-agent/").data
    assert first["latest"] is None and first["defaults"]["setup"]["basis"] == "payments" and first["defaults"]["setup"]["entity"]

    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/wp-agent/", FORM, format="json")
    assert r.status_code == 201 and r.data["kind"] == "gst" and r.data["status"] == "running"
    path, body = agent[-1]
    assert path == "/precheck/runs" and body["mode"] == "gst"
    assert body["options"]["drive_link"] == FORM["drive_link"] and body["options"]["setup"]["entity"] == "Smith Rentals Ltd"
    assert body["options"]["prepared_by"] == "Pat" and body["options"]["choices"] == {"ar_gl_fallback": False, "ap_gl_fallback": False}
    assert api(pat).post(f"/api/precheck/jobs/{issue.key}/wp-agent/", FORM, format="json").status_code == 409  # one at a time

    gst = {"status": "Reconciled subject to corrections", "bridge": {"E": "2575.00", "F": "2575.00", "unexplained": "0.00"}, "paused": {}}
    complete(r.data["run_id"], gst)
    run = AIPrecheck.objects.get(run_id=r.data["run_id"])
    assert run.status == "complete" and run.gst["bridge"]["E"] == "2575.00" and run.workbook
    assert not TaskMilestone.objects.filter(run=run).exists()  # nothing posted or stamped on the task

    state = api(pat).get(f"/api/precheck/jobs/{issue.key}/wp-agent/").data
    assert state["latest"]["gst"]["status"] == "Reconciled subject to corrections" and state["latest"]["has_workpaper"]
    assert state["defaults"]["drive_link"] == FORM["drive_link"]  # the next run starts from this one's inputs
    # The pre-check and guide panels don't show it.
    assert api(pat).get(f"/api/precheck/jobs/{issue.key}/guide/").data["latest"] is None

    xlsx = api(pat).get(f"/api/precheck/runs/{run.run_id}/workpaper.xlsx")
    assert xlsx.status_code == 200 and "Smith Rentals Ltd 2026-03-31.xlsx" in xlsx["Content-Disposition"]
    assert load_workbook(io.BytesIO(xlsx.content)).sheetnames == ["L1 GST reconciliation"]


def test_the_form_is_checked_and_only_people_who_can_open_the_task_get_the_workpaper(agent):
    pat, other = person("pat"), person("ozzy")
    issue = make_job(pat, "Smith", "SmithRent")
    bad = api(pat).post(f"/api/precheck/jobs/{issue.key}/wp-agent/", {"drive_link": "", "setup": {"basis": "weekly"}}, format="json")
    assert bad.status_code == 400 and {"drive_link", "balance_date", "basis"} <= set(bad.data)
    run = services.start_run(issue, pat, kind=AIPrecheck.Kind.GST, options=FORM)
    complete(run.run_id, {"status": "Reconciled"})
    if not services.can_open_job(other, issue):
        assert api(other).get(f"/api/precheck/runs/{run.run_id}/workpaper.xlsx").status_code == 403


def test_the_agent_unreachable_fails_the_run_plainly(settings, monkeypatch):
    def down(path, body):
        raise services.AgentUnavailable("down")

    monkeypatch.setattr(services, "_call_agent", down)
    pat = person("pat")
    issue = make_job(pat, "Smith", "SmithRent")
    r = api(pat).post(f"/api/precheck/jobs/{issue.key}/wp-agent/", FORM, format="json")
    assert r.status_code == 201 and r.data["status"] == "failed" and "not reachable" in r.data["failure_reason"]
