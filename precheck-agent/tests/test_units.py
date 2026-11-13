from pathlib import Path

from fastapi.testclient import TestClient

from precheck_agent.classify import classify
from precheck_agent.config import get_settings
from precheck_agent.drive import LocalDrive
from precheck_agent.parsing import chunk_blocks, parse_file
from precheck_agent.rules import run_rules
from precheck_agent.skills_loader import all_skills, load_skill
from precheck_agent.store import get_store
from precheck_agent.textutil import to_number

from .conftest import make_job_folder


def test_skills_in_agent_skills_format(env):
    skills = all_skills()
    assert set(skills) == {"precheck-method", "nz-residential-rental", "nz-general-business", "nz-investment", "direction-drafting", "nz-fs-review", "nz-preparation-guide",
                           "nz-gst-reconciliation", "gst-document-reading",  # the WP Agent (8 Nov 2026)
                           "nz-wages-reconciliation", "nz-imputation-reconciliation",  # its wages and ICA agents (10 Nov 2026)
                           "plain-language"}  # every report in plain words (13 Nov 2026)
    for skill in skills.values():
        path = Path(get_settings().skills_dir) / skill.name / "SKILL.md"
        text = path.read_text(encoding="utf-8")
        assert text.startswith("---\nname: " + skill.name)
        assert skill.description and len(skill.description) < 400
        assert len(text.splitlines()) < 500
        assert "+" in skill.version
    assert load_skill.invoke({"skill_name": "nz-investment"}).startswith("# Investment entities (NZ)")
    assert "No skill named" in load_skill.invoke({"skill_name": "nope"})


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


def test_classify(env):
    assert classify("Trial Balance FY25.xlsx") == "trial_balance"
    assert classify("ACME bank rec March.xlsx") == "reconciliation"
    assert classify("Prior year financial statements.pdf") == "prior_year_statements"
    assert classify("CT600 return.pdf") == "tax_return"
    assert classify("misc.xlsx", "Account | Debit | Credit") == "trial_balance"
    assert classify("holiday photo.txt") == "other"
    assert classify("Client Questionnaire 2026.pdf") == "questionnaire" and classify("CQ rental.docx") == "questionnaire"
    assert classify("form.pdf", "\n".join(["Did you buy a property this year?"] * 6)) == "questionnaire"
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


def test_control_characters_never_reach_storage(env):
    """A file whose text holds NUL bytes stopped a real run on Postgres (4 Oct 2026)."""
    folder = make_job_folder(env.drive_root, "ctrl-chars")
    (folder / "Export with nulls.txt").write_bytes(b"Bank export\x00 line one\nTotal\x00\x01 1,200.00\n")
    env.pm.add_job("1", "client-nul", "ctrl-chars")
    result = env.run("1")
    assert result["status"] == "complete"
    store = get_store()
    files = store.get_manifest("client-nul", "1")
    fid = next(f for f, row in files.items() if row["name"] == "Export with nulls.txt")
    from precheck_agent.knowledge import Scope, get_knowledge

    chunks = get_knowledge().get(Scope.of(env.pm.jobs["1"]), file_id=fid)
    assert chunks and all("\x00" not in c["text"] and "\x01" not in c["text"] for c in chunks)
    assert "Bank export line one" in chunks[0]["text"]


def test_broken_unicode_in_a_document_never_stops_a_run():
    """12 Nov 2026: a document whose text held half an emoji (an unpaired surrogate) made the
    embedder's tokenizer refuse it, and every pre-check on the task failed. It is repaired now."""
    from precheck_agent.parsing import clean_text, scrub

    assert clean_text("Rent \ud83d received") == "Rent � received"
    assert clean_text("ok 😀 fine") == "ok \U0001F600 fine"  # a proper pair is joined
    assert clean_text("plain\x00 text") == "plain text"
    assert scrub({"blocks": [{"text": "a\udc80b"}]}) == {"blocks": [{"text": "a�b"}]}
    "x".join(scrub(["\ud800"])).encode("utf-8")  # storable and tokenizable


def test_every_report_writing_agent_writes_in_plain_language(env):
    """AFIT, 13 Nov 2026: the pre-check, Ask, the preparation guide, the review and the Direction Note
    are all written so anyone can understand them."""
    from precheck_agent import ask, directions, guide, precheck, review

    for system in (precheck.system_text(), ask.system_text("general"), guide.system_text(), review.system_text("residential_rental"),
                   directions.draft_system()):
        assert "# Skill: plain-language" in system and "Use everyday words" in system
    assert "plain-language" in precheck.skill_versions() and "plain-language" in review.skill_versions("general")
