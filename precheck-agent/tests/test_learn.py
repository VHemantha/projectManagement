"""Learned skills: a correction drafted as a rule, given to the review and the pre-check as a rule,
and found by Ask only where it applies."""
from precheck_agent import ask, learn, runner
from precheck_agent.knowledge import Scope

from .test_review import add_review_job, review_folder

RULE = {"title": "One property: rent in one line", "when": "The client owns a single rental property.",
        "do": "Do not ask for rental income to be split by property.", "why": "There is nothing to split."}


def lesson(lid, note, scope="client", client="client-smith", rule=None, team="team-1"):
    return {"id": lid, "scope": scope, "status": "active", "kind": "not_needed", "item": "Rent by property", "note": note,
            "rule": rule, "client_scope": client, "project_scope": "project-client-smith", "team_scope": team, "source": "review"}


def test_a_correction_is_drafted_as_a_rule_and_sent_back(env):
    rule = runner.learn_now({"lesson_id": 7, "job_id": "1", "kind": "not_needed", "item": "Rent by property", "note": "Only one property.",
                             "source": "review", "context": {"fs_line": "Rental income", "issue": "Show rent by property.", "why": ""}})
    event = env.pm.events[-1]
    assert event["type"] == "ai_learning.drafted" and event["run_id"] == "lesson-7" and event["result"]["do"] == "Only one property."
    assert rule == event["result"]
    assert learn.lesson_text(lesson(1, "Only one property.", rule=RULE)).startswith("When: The client owns a single rental property. Do: Do not ask")
    assert learn.lesson_text(lesson(1, "Only one property.")) == "Only one property."


def test_the_review_reads_lessons_as_rules(env):
    review_folder(env)
    add_review_job(env, findings=[], assumptions=[])
    env.pm.jobs["1"]["lessons"] = [lesson(3, "Only one property.", rule=RULE)]
    env.run("1", mode="review")
    body = env.precheck.calls[0]["messages"][-1].content
    assert "L3 | not_needed | Rent by property | When: The client owns a single rental property. Do: Do not ask for rental income" in body


def test_ask_finds_the_learned_rules_that_apply_here_and_no_others(env):
    review_folder(env)
    add_review_job(env, findings=[], assumptions=[])
    env.run("1", mode="review")  # index the folder
    job = env.pm.jobs["1"]
    mine = lesson(3, "Only one property.", rule=RULE)
    elsewhere = lesson(9, "Rent is split by property for this client.", client="client-jones", team="team-9",
                       rule={**RULE, "do": "Always split rental income by property."})
    learn.remember([elsewhere])  # in the store, but not one of this task's lessons
    files = {fid: {**row, "file_id": fid} for fid, row in __import__("precheck_agent.store", fromlist=["x"]).get_store().get_manifest("client-smith", "1").items()}
    hits = ask.retrieve(Scope.of(job), "Should rental income be split by property?", files, None, lessons=[mine])
    rules = [h for h in hits if h["source_type"] == "skill"]
    assert [h["lesson_id"] for h in rules] == [3] and rules[0]["applies"] == "client" and rules[0]["how"] == "learned rule"
    body, _ = ask.build_input(job, "Should rental income be split by property?", [], hits, files)
    assert "[AFIT's learned rule]" in body and "Always split" not in body
