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


# --- a run is given the lessons that fit its job (AFIT, 29 Oct 2026) ------------------------------

def firm_rule(lid, note, item="", nature=""):
    return {"id": lid, "scope": "firm", "status": "active", "kind": "missed", "item": item, "note": note, "rule": None,
            "client_scope": "", "project_scope": "", "team_scope": "", "source": "library", "precheck_type": nature}


def rental_job():
    job = {"client_id": "client-smith", "title": "Smith rental property year end", "client_name": "Smith", "settings": {}}
    docs = [{"file": {"name": "2026 rental questionnaire.pdf", "document_class": "questionnaire"},
             "parsed": {"blocks": [{"text": "Rental property at 12 Beach Road. Interest on the mortgage. Property manager fees. Insurance."}]}}]
    return job, docs


def test_a_rule_taught_once_is_found_the_next_time_that_kind_of_check_comes_up():
    job, docs = rental_job()
    noise = [firm_rule(100 + i, f"Unrelated rule {i} about GST returns for cafe payroll and stock count {i}") for i in range(60)]
    taught = firm_rule(7, "Ask for the mortgage interest certificate and the property manager's annual statement",
                       item="Rental property mortgage interest", nature="residential_rental")
    chosen = learn.select(noise[:30] + [taught] + noise[30:], job, docs, limit=10)
    assert len(chosen) == 10 and 7 in [l["id"] for l in chosen]  # 61 rules: the one that fits is kept
    assert chosen[[l["id"] for l in chosen].index(7)]["match"] > 0


def test_the_clients_own_lessons_always_come_first():
    job, docs = rental_job()
    own = [{**lesson(i, f"Own note {i}"), "id": i} for i in range(1, 4)]
    wider = [firm_rule(100 + i, f"Unrelated rule {i}") for i in range(60)]
    chosen = learn.select(own + wider, job, docs, limit=10)
    assert [l["id"] for l in chosen[:3]] == [1, 2, 3]


def test_a_rule_for_another_type_of_check_gives_way_when_the_type_is_known():
    job, docs = rental_job()
    same = firm_rule(1, "Ask for the property manager statement for the rental", nature="residential_rental")
    other = firm_rule(2, "Ask for the property manager statement for the rental", nature="investment")
    fillers = [firm_rule(10 + i, f"Unrelated rule {i} about payroll") for i in range(45)]
    chosen = [l["id"] for l in learn.select([other, same] + fillers, job, docs, nature="residential_rental", limit=2)]
    assert chosen[0] == 1


def test_few_lessons_are_all_given():
    job, docs = rental_job()
    few = [firm_rule(i, f"Rule {i}") for i in range(5)]
    assert learn.select(few, job, docs) == few
