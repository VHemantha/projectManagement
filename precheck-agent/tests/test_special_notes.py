"""AFIT, 13 Nov 2026: staff give special notes on a task, and the pre-check, the guide, the review and
Ask follow them when they decide and write, cite them where they mattered, and list them with the
result so people can see each note was considered."""
from precheck_agent import ask, llm
from precheck_agent import special_notes as SN

from .test_ask import answering
from .test_precheck import ready_folder

SALE = {"id": 1, "text": "The client sold 12 Kauri Street in June 2025: treat this year as the year of sale.", "by": "Rita", "agents": []}
REVIEW_ONLY = {"id": 2, "text": "Check the depreciation recovery on the sale first.", "by": "Lee", "agents": ["review"]}
GUIDE_ONLY = {"id": 3, "text": "Start with the bank reconciliation.", "by": "Lee", "agents": ["guide"]}


def job_with_notes(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.pm.jobs["1"]["special_notes"] = [SALE, REVIEW_ONLY, GUIDE_ONLY]
    return env.pm.jobs["1"]


def test_the_precheck_is_given_its_notes_to_follow_and_lists_them_with_the_result(env):
    job_with_notes(env)
    result = env.run("1")
    body = env.precheck.calls[0]["messages"][-1].content
    assert "SPECIAL NOTES FROM AFIT STAFF FOR THIS TASK (follow each one" in body
    assert "SN1 | from Rita | The client sold 12 Kauri Street in June 2025" in body
    assert "depreciation recovery" not in body and "bank reconciliation" not in body  # meant for other agents
    notes = result["precheck"]["special_notes"]
    assert [(n["id"], n["by"]) for n in notes] == [("SN1", "Rita")] and notes[0]["text"] == SALE["text"]


def test_a_changed_note_is_a_new_input_so_the_answer_is_not_reused(env):
    job = job_with_notes(env)
    env.run("1")
    job["special_notes"] = [{**SALE, "text": "Treat the property as still held."}]
    env.run("1")
    assert len(env.precheck.calls) == 2


def test_the_guide_reads_the_notes_for_it(env):
    job = job_with_notes(env)
    job["last_precheck"] = {"business_nature": {"label": "Residential rental"}, "requests": [], "preparer_notes": []}
    result = env.run("1", mode="guide")
    body = env.precheck.calls[0]["messages"][-1].content
    assert "SN1 | from Rita | The client sold" in body and "SN2 | from Lee | Start with the bank reconciliation." in body
    assert "depreciation recovery" not in body
    assert [n["id"] for n in result["guide"]["special_notes"]] == ["SN1", "SN2"]


def test_ask_follows_the_notes_and_shows_a_cited_one(env):
    env.pm.add_job("1", "client-empty", "nothing-here", direction=[])
    env.pm.jobs["1"]["special_notes"] = [SALE]
    seen: dict = {}
    llm.set_fake("assistant", answering({
        "answer": "Yes: this is the year the rental was sold.", "status": "answered", "outside_job": False,
        "points": [{"text": "The rental was sold in June 2025.", "basis": "task_documents", "sources": ["SN1"], "reference": ""}]}, seen))
    out = ask.answer(env.pm.jobs["1"], "Is this the year of sale?")
    assert "SN1 | from Rita | The client sold 12 Kauri Street" in seen["body"]
    assert out["points"][0]["sources"][0]["label"].startswith("Special note: The client sold 12 Kauri Street")
    assert out["special_notes"] == [{"id": "SN1", "text": SALE["text"], "by": "Rita", "cited": True}]


def test_which_notes_were_cited_is_worked_out_from_the_answer():
    job = {"special_notes": [SALE, {"text": "Second note", "by": "", "agents": ["precheck"]}, {"text": "  "}]}
    cleaned = {"items": [{"sources": ["Q1", "SN2"]}], "preparer_notes": [{"sources": ["SN2"]}]}
    assert SN.considered(job, "precheck", cleaned) == [
        {"id": "SN1", "text": SALE["text"], "by": "Rita", "cited": False},
        {"id": "SN2", "text": "Second note", "by": "", "cited": True},
    ]
    assert SN.for_agent(job, "review") == [SALE]  # notes for every agent, and none that are blank


def test_the_review_reads_the_notes_for_it(env):
    from .test_review import add_review_job, review_folder

    review_folder(env)
    add_review_job(env)
    env.pm.jobs["1"]["special_notes"] = [SALE, REVIEW_ONLY, GUIDE_ONLY]
    result = env.run("1", mode="review")
    body = env.precheck.calls[0]["messages"][-1].content
    assert "SN2 | from Lee | Check the depreciation recovery on the sale first." in body and "bank reconciliation" not in body
    assert [n["id"] for n in result["review"]["special_notes"]] == ["SN1", "SN2"]
