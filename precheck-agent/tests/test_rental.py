"""Pre-check types: a residential rental task is checked against AFIT's rental checklist."""
import json

from precheck_agent import checklists as C

from .conftest import make_job_folder


def rental_folder(env, name="rental"):
    folder = make_job_folder(env.drive_root, name)
    (folder / "Property manager annual summary 2026.txt").write_text(
        "Barfoot property management\nAnnual summary 1 April 2025 to 31 March 2026\n12 Kauri Street\nGross rent 31,200.00\nManagement fees 2,496.00\n",
        encoding="utf-8")
    (folder / "Rates invoice 12 Kauri Street.txt").write_text("Auckland Council rates assessment 2025/26\nTotal rates 3,412.00\n", encoding="utf-8")
    return folder


def test_the_rental_checklist_comes_from_the_firms_rules():
    items = C.items("residential_rental")
    assert len(items) == 23 and [i["id"] for i in items][:3] == ["BS01", "BS02", "BS03"]
    assert {i["origin"] for i in items} == {"checklist"} and items[0]["basis"] == "Residential rental"
    q = C.question(items[2], "residential_rental")
    assert "BS03" in q and "do not treat principal as interest" in q and "Do not mark an item not applicable" in q
    assert C.items("general") == [] and C.readiness("residential_rental")["not_ready"] == "Blocked"


def test_a_rental_task_is_checked_against_every_rental_check(env):
    rental_folder(env)
    env.pm.add_job("1", "client-r", "rental", direction=[{"id": "D1", "text": "Confirm the tenant changed in October"}])
    env.pm.jobs["1"]["precheck_type"] = "residential_rental"
    result = env.run("1")
    assert result["status"] == "complete" and result["precheck_type"] == "residential_rental"
    ids = [i["id"] for i in result["direction_items"]]
    assert ids[:23] == [i["id"] for i in C.items("residential_rental")] and ids[-1] == "D1"
    assert len(env.reader.calls) >= 24  # every check and the Direction Note item were read
    assert not env.drafter.calls  # the checklist is the to-do list: nothing to draft
    checklist = {i["id"]: i for i in result["direction_items"]}
    assert checklist["BS01"]["origin"] == "checklist" and checklist["BS01"]["status"] in ("complete", "partial", "missing", "clarification")
    assert result["readiness"] in ("Ready to start", "Ready to start with gaps", "Blocked")
    # The reader for a check was told what to look for and the ground rules.
    asked = [c["messages"][-1].content[-1]["text"] for c in env.reader.calls]
    assert any("PL02" in a and "Avoid double counting" not in a and "avoid double counting with net bank transfers" in a for a in asked)
    # Requests to send: drafted, grouped by check, never sent.
    assert result["requests"] and all(r["items"] for r in result["requests"])
    assert all(r["group"].split(" ")[0] in ids or r["group"] for r in result["requests"])


def test_general_tasks_are_unchanged(env, job):
    result = env.run(job)
    assert result["precheck_type"] == "general" and [i["id"] for i in result["direction_items"]] == ["D1", "D2", "D3"]
    assert result["readiness"] in ("Ready for review", "Ready with exceptions", "Not ready")


def test_a_rental_task_without_a_direction_note_still_runs_without_drafting(env):
    rental_folder(env, "rental2")
    env.pm.add_job("2", "client-r", "rental2", direction=[])
    env.pm.jobs["2"]["precheck_type"] = "residential_rental"
    result = env.run("2")
    assert result["status"] == "complete" and len(result["direction_items"]) == 23 and not env.drafter.calls
    assert json.dumps(result)  # serialisable for the PM application


def test_a_rental_task_is_not_asked_for_a_trial_balance(env):
    folder = env.drive_root / "no-tb"
    folder.mkdir()
    (folder / "Barfoot annual summary.txt").write_text("Annual summary\nGross rent 31,200.00\n", encoding="utf-8")
    env.pm.add_job("3", "client-r", "no-tb", direction=[])
    env.pm.jobs["3"]["precheck_type"] = "residential_rental"
    result = env.run("3")
    assert not any("trial balance" in f["title"].lower() for f in result["findings"])


def test_a_finding_line_inside_a_list_or_bold_is_still_read():
    from langchain_core.messages import AIMessage

    from precheck_agent.readers import parse_reader_answer

    blocks = [{"text": "Interest charged 14,322.18", "loc": "line 4", "sheet": None, "row": None, "a1": None, "page": None}]
    chunks = [{"file_id": "F", "blocks": blocks}]
    files = {"F": {"file_id": "F", "version": "v", "name": "Loan.txt", "path": "", "web_url": "u", "mime_type": ""}}
    cite = {"type": "content_block_location", "document_index": 0, "start_block_index": 0, "end_block_index": 1}
    message = AIMessage(content=[{"type": "text", "text": "- **addressed**|low|Loan interest evidenced|Interest charged 14,322.18 for the year.", "citations": [cite]}])
    findings, _ = parse_reader_answer(message, chunks, files)
    assert findings[0]["status"] == "addressed" and findings[0]["evidence_ids"]
