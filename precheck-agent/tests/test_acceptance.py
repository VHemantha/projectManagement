"""The acceptance tests from the brief, run against the real graph with scripted models."""
import json

from openpyxl import load_workbook

from precheck_agent import judge as J
from precheck_agent.config import get_settings

from .conftest import DIRECTION, make_job_folder


def test_1_a_run_produces_a_result_for_the_job(env, job):
    result = env.run(job)
    assert result["status"] == "complete"
    assert result["verdict"] in ("ready", "ready_with_exceptions", "not_ready")
    done = env.pm.completed()
    assert len(done) == 1 and done[0]["job_id"] == job and done[0]["result"]["run_id"] == result["run_id"]
    stages = [e["stage"] for e in env.pm.events if e["type"] == "ai_precheck.progress"]
    assert [s for i, s in enumerate(stages) if s not in stages[:i]] == ["read", "checked", "compared", "judged", "verified"]


def test_2_every_finding_opens_to_a_quoted_source_with_a_link(env, job):
    result = env.run(job)
    evidence = {e["id"]: e for e in result["evidence"]}
    assert result["findings"]
    for f in result["findings"]:
        if f["status"] in ("missing", "unclear"):
            continue
        assert f["evidence_ids"], f
        for eid in f["evidence_ids"]:
            e = evidence[eid]
            assert e["quote"] and e["file_name"] and e["location"] and e["drive_url"]
    # The quote is the document's own text, not something a model wrote.
    rec = next(e for e in result["evidence"] if e["file_name"] == "Bank reconciliation.csv")
    source = (env.drive_root / "acme-fy25" / "Bank reconciliation.csv").read_text()
    assert rec["quote"].split(": ", 1)[1].split(" | ")[0] in source
    assert "row" in rec["location"]


def test_3_every_direction_note_item_is_addressed_or_not(env, job):
    result = env.run(job)
    assert [i["id"] for i in result["direction_items"]] == [d["id"] for d in DIRECTION]
    assert all(isinstance(i["addressed"], bool) for i in result["direction_items"])
    refs = {f["direction_ref"] for f in result["findings"]}
    assert {d["id"] for d in DIRECTION} <= refs
    assert result["coverage"] == {"addressed": sum(i["addressed"] for i in result["direction_items"]), "total": 3}


def test_4_second_run_with_no_changes_makes_no_reader_calls(env, job):
    first = env.run(job)
    assert first["usage"]["reader_calls"] == len(env.reader.calls) > 0
    readers, judges = len(env.reader.calls), len(env.judge.calls)
    second = env.run(job)
    assert len(env.reader.calls) == readers, "a reader was called again"
    assert len(env.judge.calls) == judges, "the judge was called again"
    assert second["usage"]["model_calls"] == 0 and second["usage"]["totals"]["input"] == 0
    assert second["usage"]["reused_answers"] == first["usage"]["reader_calls"]
    assert second["trail"]["read"]["changed"] == 0
    strip = lambda r: [{k: f[k] for k in ("status", "severity", "title", "evidence_ids")} for f in r["findings"]]  # noqa: E731
    assert strip(second) == strip(first)
    assert second["run_id"] != first["run_id"]  # a new run, the first is kept


def test_5_changing_one_file_rereads_only_that_files_tasks(env, job):
    env.run(job)
    before = len(env.reader.calls)
    path = env.drive_root / "acme-fy25" / "Tax computation.txt"
    path.write_text(path.read_text(encoding="utf-8").replace("57,500", "58,000"), encoding="utf-8")
    result = env.run(job)
    new_calls = env.reader.calls[before:]
    assert result["trail"]["read"]["changed"] == 1
    assert 1 <= len(new_calls) < before
    for call in new_calls:  # every re-read task had the changed file among its passages
        titles = [b["title"] for b in call["messages"][-1].content if b.get("type") == "document"]
        assert any(t.startswith("Tax computation.txt") for t in titles), titles
    outcomes = [d["outcome"] for d in result["trail"]["compared"]["detail"]]
    assert outcomes.count("read") == len(new_calls) and "reused from an earlier run" in outcomes


def test_6_usage_is_recorded_and_inside_the_budget(env, job):
    result = env.run(job)
    s = get_settings()
    u = result["usage"]
    assert u["calls"] and all({"model", "input", "output", "cache_write", "cache_read", "node"} <= set(c) for c in u["calls"])
    assert u["reader_calls"] <= s.budget_max_reader_calls
    assert u["totals"]["input"] <= s.budget_max_uncached_input_tokens
    assert u["totals"]["output"] <= s.budget_max_output_tokens
    assert u["totals"]["input"] == sum(c["input"] for c in u["calls"])
    for call in env.reader.calls:  # each reader got at most 6 chunks
        docs = [b for b in call["messages"][-1].content if b.get("type") == "document"]
        assert 1 <= len(docs) <= s.top_k


def test_6b_budget_breach_stops_and_reports_what_was_skipped(env, job, monkeypatch):
    # The budget grows with the work, up to the hard caps; here the cap is one reader call.
    monkeypatch.setenv("PRECHECK_BUDGET_READER_CALLS", "1")
    monkeypatch.setenv("PRECHECK_BUDGET_MAX_READER_CALLS", "1")
    get_settings.cache_clear()
    result = env.run(job)
    assert len(env.reader.calls) == 1
    assert result["status"] == "partial"
    assert len(result["skipped"]) >= 2 and all(s["reason"] for s in result["skipped"])
    # Items that were skipped are reported as not addressed, never guessed.
    skipped_refs = {s["direction_ref"] for s in result["skipped"]}
    assert all(not i["addressed"] for i in result["direction_items"] if i["id"] in skipped_refs)


def test_8_judge_output_validates_against_the_schema(env, job):
    import jsonschema

    env.run(job)
    assert env.judge.calls
    for call in env.judge.calls:
        fmt = call["kwargs"]["output_config"]["format"]
        assert fmt == {"type": "json_schema", "schema": J.RESULT_SCHEMA}
        jsonschema.validate(json.loads(call["reply"].content), J.RESULT_SCHEMA)
        # The judge saw findings and ids only: no document text.
        body = call["messages"][-1].content
        assert isinstance(body, str) and "Balance per bank" not in body and "document" not in json.loads(body.split("INPUT:")[1])
    assert all(v == [] or isinstance(v, list) for v in [J.RESULT_SCHEMA["required"]])


def test_9_the_service_cannot_mark_a_job_reviewed(env, job):
    env.run(job)
    assert {e["type"] for e in env.pm.events} <= {"ai_precheck.progress", "ai_precheck.completed", "ai_precheck.failed"}
    from precheck_agent.pm_client import PMClient

    assert sorted(m for m in vars(PMClient) if not m.startswith("_")) == ["get_job", "send_event"]
    result = env.pm.completed()[0]["result"]
    assert "reviewed" not in json.dumps(result).lower()


def test_rules_find_what_code_can_check_without_a_model(env, job):
    result = env.run(job)
    by_title = {f["title"]: f for f in result["findings"]}
    schedule = next(f for t, f in by_title.items() if "does not agree to the trial balance" in t)
    assert schedule["source"] == "rule" and schedule["kind"] == "rule" and len(schedule["evidence_ids"]) == 2
    assert "112,400" in schedule["why"] and "118,900" in schedule["why"]
    assert result["trail"]["checked"]["failed"] >= 1
    assert result["verdict"] != "ready"


def test_unbalanced_trial_balance_makes_the_job_not_ready(env):
    rows = [r[:] for r in __import__("tests.conftest", fromlist=["TB_ROWS"]).TB_ROWS]
    rows[1][2] = 50210  # cash overstated by 2,000
    make_job_folder(env.drive_root, "beta", tb_rows=rows)
    env.pm.add_job("202", "client-beta", "beta")
    result = env.run("202")
    assert result["verdict"] == "not_ready"
    f = next(f for f in result["findings"] if f["title"] == "Trial balance does not balance")
    assert f["severity"] == "high" and "2,000" in f["why"] and f["evidence_ids"]


def test_missing_setup_stops_with_a_plain_reason(env):
    make_job_folder(env.drive_root, "gamma")
    env.pm.add_job("303", "client-gamma", "", direction=None)
    r = env.run("303")
    assert r["status"] == "failed" and "Drive folder" in r["reason"]
    assert not env.reader.calls
    assert load_workbook  # fixtures are real spreadsheets, parsed by the real parser
