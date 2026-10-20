"""A run can never go on without end: a person can stop it, it stops itself after a time limit,
and runs a restart interrupted are reported as failed when the service comes back."""
from fastapi.testclient import TestClient

from precheck_agent import config, runner
from precheck_agent.store import get_store


def failures(env):
    return [e for e in env.pm.events if e["type"] == "ai_precheck.failed"]


def test_a_stopped_run_does_no_more_work_and_reports_the_stop(env, job):
    run_id = runner.new_run_id()
    client = TestClient(runner_app())
    assert client.post(f"/precheck/runs/{run_id}/cancel", headers={"X-Precheck-Token": "test-token"}).status_code == 202
    result = runner.execute(run_id, job)
    assert result["status"] == "failed" and result["reason"].startswith("Stopped by a person")
    assert not env.precheck.calls and not env.pm.completed()
    assert failures(env)[-1]["run_id"] == run_id
    assert get_store().get_run(run_id)["status"] == "failed"
    # The stop applied to that run only: the next one runs to the end.
    assert env.run(job)["status"] == "complete"


def test_a_run_past_its_time_limit_is_stopped(env, job, monkeypatch):
    monkeypatch.setenv("PRECHECK_RUN_DEADLINE_S", "-1")
    config.get_settings.cache_clear()
    result = env.run(job)
    assert result["status"] == "failed" and "took longer than" in result["reason"]
    assert not env.pm.completed()


def test_runs_a_restart_interrupted_are_reported_as_failed(env, job):
    get_store().save_run("interrupted", job, "running")
    get_store().save_run("finished", job, "complete", {"status": "complete"})
    assert runner.fail_orphans() == 1
    (event,) = failures(env)
    assert event["run_id"] == "interrupted" and "restarted" in event["reason"]
    assert get_store().get_run("interrupted")["status"] == "failed"
    assert get_store().get_run("finished")["status"] == "complete"
    assert runner.fail_orphans() == 0  # once only


def test_cancelling_needs_the_service_token(env):
    assert TestClient(runner_app()).post("/precheck/runs/x/cancel").status_code == 401


def runner_app():
    from precheck_agent.api import app

    return app
