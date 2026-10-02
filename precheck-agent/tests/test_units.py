from pathlib import Path

from fastapi.testclient import TestClient

from precheck_agent.classify import classify, reader_for_question
from precheck_agent.config import get_settings
from precheck_agent.drive import LocalDrive
from precheck_agent.parsing import chunk_blocks, parse_file
from precheck_agent.readers import READERS, make_get_text, system_prompt
from precheck_agent.rules import run_rules
from precheck_agent.skills_loader import all_skills, load_skill
from precheck_agent.store import get_store
from precheck_agent.textutil import est_tokens, to_number

from .conftest import make_job_folder


def test_skills_in_agent_skills_format(env):
    skills = all_skills()
    assert set(skills) == {"gdrive-folder-reader", "ledger-reading", "statements-reading", "tax-reading", "workpaper-reading",
                           "finding-format", "direction-drafting"}
    for skill in skills.values():
        path = Path(get_settings().skills_dir) / skill.name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\nname: " + skill.name)
        assert skill.description and len(skill.description) < 400
        assert len(text.splitlines()) < 500
        assert "+" in skill.version
    assert load_skill.invoke({"skill_name": "tax-reading"}).startswith("# Reading tax documents")
    assert "No skill named" in load_skill.invoke({"skill_name": "nope"})


def test_reader_prompt_is_a_stable_prefix_with_only_its_own_skill(env):
    for reader, (skill, _) in READERS.items():
        prompt = system_prompt(reader)
        assert prompt == system_prompt(reader)  # byte-stable: nothing job-specific, no timestamps
        assert f"# Skill: {skill}" in prompt and "# Skill: finding-format" in prompt
        others = [s for s, _ in READERS.values() if s != skill]
        for other in others:
            assert f"# Skill: {other}" not in prompt  # other skills: name and description only
            assert f"- {other}:" in prompt
        assert est_tokens(prompt) < 2500


def test_parsing_gives_citable_rows(env):
    folder = make_job_folder(env.drive_root, "p")
    parsed = parse_file((folder / "Trial Balance FY25.xlsx").read_bytes(), "Trial Balance FY25.xlsx")
    block = next(b for b in parsed["blocks"] if "Trade debtors" in b["text"])
    assert block["loc"] == "sheet 'TB', row 3" and block["a1"] == "A3:E3" and block["text"].startswith("row 3: 1100 | Trade debtors | 118900")
    assert parsed["tables"][0]["rows"][2][1][2] == 118900
    chunks = chunk_blocks(parsed["blocks"], chunk_tokens=40)
    assert len(chunks) > 1 and chunks[1]["blocks"][0].get("is_header")  # header repeated in later chunks
    assert parse_file(b"\x00\x01", "photo.png") == {"blocks": [], "tables": [], "vision": "image"}  # read by vision.py
    assert parse_file(b"\x00\x01", "setup.exe")["error"]
    assert parse_file(b"not a zip", "broken.xlsx")["error"].startswith("Could not read")
    text = parse_file("Line one\n\nLine two\n".encode(), "notes.txt")
    assert [b["loc"] for b in text["blocks"]] == ["line 1", "line 3"]


def test_classify_and_route(env):
    assert classify("Trial Balance FY25.xlsx") == "trial_balance"
    assert classify("ACME bank rec March.xlsx") == "reconciliation"
    assert classify("Prior year financial statements.pdf") == "prior_year_statements"
    assert classify("CT600 return.pdf") == "tax_return"
    assert classify("misc.xlsx", "Account | Debit | Credit") == "trial_balance"
    assert classify("holiday photo.txt") == "other"
    assert reader_for_question("Agree the bank reconciliation to the ledger") == "ledger_reader"
    assert reader_for_question("Check the corporation tax computation") == "tax_reader"
    assert reader_for_question("Make sure everything is fine") is None
    assert to_number("(1,234.50)") == -1234.5 and to_number("£2,000") == 2000 and to_number("n/a") is None


def test_rules_on_real_files(env):
    folder = make_job_folder(env.drive_root, "r")
    docs = []
    for f in LocalDrive(get_settings()).list_folder("r"):
        parsed = parse_file((folder / f.name).read_bytes(), f.name)
        docs.append({"file": {"file_id": f.id, "name": f.name, "document_class": classify(f.name), "error": parsed.get("error", "")}, "parsed": parsed})
    results = {r["label"]: r for r in run_rules(docs, get_settings())}
    assert results["Trial balance debits equal credits"]["passed"] is True
    assert results["Reconciliations show no difference"]["passed"] is True
    assert results["Schedules agree to the trial balance"]["passed"] is False
    movers = [r for r in run_rules(docs, get_settings()) if r["rule_id"].startswith("variance") and not r["passed"]]
    assert {m["area"] for m in movers} == {"Trade debtors"} and all(m["needs_judgment"] and m["question"] for m in movers)


def test_local_drive_versions_change_with_content(env):
    folder = make_job_folder(env.drive_root, "d")
    drive = LocalDrive(get_settings())
    before = {f.name: f.version for f in drive.list_folder("d")}
    (folder / "Tax computation.txt").write_text("changed", encoding="utf-8")
    after = {f.name: f.version for f in drive.list_folder("d")}
    assert [n for n in before if before[n] != after[n]] == ["Tax computation.txt"]


def test_one_extra_slice_per_task(env, job):
    env.run(job)
    store = get_store()
    files = store.get_manifest("client-acme", "101")
    tb = next(fid for fid, f in files.items() if f["document_class"] == "trial_balance")
    state = {"used": False}
    tool = make_get_text(store, "client-acme", "101", files, state)
    first = tool.invoke({"file_id": tb, "range": "sheet 'TB' rows 2-3"})
    assert "Cash at bank" in first and "Trade debtors" in first and "Accruals" not in first
    assert "already used" in tool.invoke({"file_id": tb, "range": "rows 1-99"})


def test_api_needs_the_service_token_and_returns_a_run_id_at_once(env, job):
    from precheck_agent import runner
    from precheck_agent.api import app

    client = TestClient(app)
    assert client.get("/healthz").json()["llm_mode"] == "fake"
    assert client.post("/precheck/runs", json={"job_id": job}).status_code == 401
    assert client.post("/precheck/runs", json={"job_id": job}, headers={"X-Precheck-Token": "wrong"}).status_code == 401
    resp = client.post("/precheck/runs", json={"job_id": job}, headers={"X-Precheck-Token": "test-token"})
    assert resp.status_code == 202 and resp.json()["status"] == "running"
    run_id = resp.json()["run_id"]
    for thread in list(__import__("threading").enumerate()):
        if thread.name.startswith("precheck-"):
            thread.join(timeout=60)
    body = client.get(f"/precheck/runs/{run_id}", headers={"X-Precheck-Token": "test-token"}).json()
    assert body["status"] == "complete" and body["result"]["run_id"] == run_id
    # The run id is the LangGraph thread id: its checkpoint can be read back.
    snapshot = runner.graph().get_state({"configurable": {"thread_id": run_id}})
    assert snapshot.values["final"]["run_id"] == run_id
    assert client.get("/precheck/runs/nope", headers={"X-Precheck-Token": "test-token"}).status_code == 404
