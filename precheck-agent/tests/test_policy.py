"""AFIT, 20 Nov 2026: pre-check policies. Accountants write the firm's standards for a client, a client
group, a location or every task; once the pre-check has produced its points, each point is checked
against the policies that apply and the result is adjusted to follow them. Feedback on a policy has
the AI revise it. The chat answers about one point; the review builds on the pre-check's stored
result; and a task's memory is freed after its final review."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import ask, llm, runner
from precheck_agent import policy as PO
from precheck_agent.embeddings import get_embedder
from precheck_agent.knowledge import Scope, get_knowledge
from precheck_agent.store import get_store

from .test_ask import answering
from .test_precheck import ready_folder

NO_ROUNDING = {"id": 7, "title": "No council rates for sold rentals", "scope": "group", "scope_label": "Group: Smith group",
               "text": "When a rental property was sold during the year, do not ask for the full year's council rates; ask only for the "
                       "settlement statement, which shows the rates apportionment."}


def answering_policy(answer_of, seen=None):
    """A stand-in policy checker: `answer_of(body)` gives its answer."""
    def responder(messages, kwargs):
        body = messages[-1].content
        if seen is not None:
            seen["body"], seen["system"] = body, messages[0].content if isinstance(messages[0].content, str) else str(messages[0].content)
        text = json.dumps(answer_of(body))
        return AIMessage(content=text, usage_metadata={"input_tokens": 100, "output_tokens": 50, "total_tokens": 150})
    return responder


def point_ids(body: str) -> dict[str, str]:
    """P id -> item, from the policy checker's input."""
    out = {}
    for line in body.splitlines():
        parts = line.split(" | ")
        if parts[0].startswith("P") and parts[0][1:].isdigit():
            out[parts[0]] = parts[4]
    return out


def smith_job(env, policies):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.pm.jobs["1"]["policies"] = policies
    env.pm.jobs["1"]["group"] = "Smith group"
    return env.pm.jobs["1"]


def test_with_no_policy_nothing_is_checked_and_no_call_is_made(env):
    smith_job(env, [])
    checker = llm.set_fake("policy", answering_policy(lambda body: {"points": [], "added": []}))
    result = env.run("1")
    assert checker.calls == [] and "policy_check" not in result["precheck"]


def test_every_point_is_checked_against_the_policies_and_changed_where_a_policy_says_so(env):
    smith_job(env, [NO_ROUNDING])
    seen: dict = {}

    def answer(body):
        ids = point_ids(body)
        changed = next(pid for pid, item in ids.items() if item.startswith("Evidence for"))
        return {"points": [
            {"id": pid, "verdict": "change", "policies": ["Y1"], "decision": "not_needed", "priority": "normal",
             "reason": "The property was sold, so the settlement statement covers the rates.", "note": "Sold rentals: settlement statement only."}
            if pid == changed else
            {"id": pid, "verdict": "keep", "policies": [], "decision": "request", "priority": "normal", "reason": "", "note": ""}
            for pid in ids],
            "added": [{"group": "12 Kauri Street", "item": "Settlement statement for the sale", "decision": "request", "priority": "blocking",
                       "reason": "It shows the sale price and the rates apportionment.", "policies": ["Y1"]},
                      {"group": "Tax", "item": "Something no policy asks for", "decision": "request", "priority": "normal",
                       "reason": "Made up.", "policies": []}]}

    llm.set_fake("policy", answering_policy(answer, seen))
    result = env.run("1")
    body = seen["body"]
    assert "== AFIT'S PRE-CHECK POLICIES THAT APPLY TO THIS TASK ==" in body
    assert "Y1 | Group: Smith group | No council rates for sold rentals |" in body
    assert "group Smith group" in body
    assert "# Skill: plain-language" in seen["system"]
    pre = result["precheck"]
    check = pre["policy_check"]
    assert check["changed"] == 1 and check["added"] == 1 and check["checked"] == len(point_ids(body))
    assert check["policies"][0]["title"] == NO_ROUNDING["title"] and check["policies"][0]["applied_to"] == 2

    moved = [p for p in pre["not_needed"] if (p.get("policy") or {}).get("changed")]
    assert len(moved) == 1 and moved[0]["item"].startswith("Evidence for")
    assert moved[0]["policy"]["was"]["decision"] == "request" and moved[0]["policy"]["policies"][0]["id"] == 7
    assert moved[0]["policy"]["note"] == "Sold rentals: settlement statement only."
    added = [p for p in pre["requests"] if "policy_added" in (p.get("flags") or [])]
    assert [a["item"] for a in added] == ["Settlement statement for the sale"]  # the one citing no policy is not added
    # The email and the decision follow the adjusted list.
    assert "Settlement statement for the sale" in pre["email"]["body"] and moved[0]["item"] not in pre["email"]["body"]


def test_a_change_citing_no_policy_or_a_figure_not_in_the_input_is_not_applied():
    out = {"requests": [{"group": "Tax", "item": "Provisional tax", "decision": "request", "priority": "normal", "reason": "Needed."}],
           "provided": [], "not_needed": [], "accountant_questions": []}
    body, pol, points = PO.build_input({"title": "T"}, out, [NO_ROUNDING])
    raw = {"points": [{"id": "P1", "verdict": "change", "policies": ["Y9"], "decision": "not_needed", "priority": "normal",
                       "reason": "No.", "note": ""}], "added": []}
    assert PO.apply(out, raw, body, pol, points)["requests"][0]["item"] == "Provisional tax"
    raw["points"][0]["policies"] = ["Y1"]
    raw["points"][0]["reason"] = "The client paid 98,765.43 already."
    changed = PO.apply(out, raw, body, pol, points)
    assert changed["not_needed"][0]["reason"] == "Needed."  # moved as the policy says, but the invented figure is not used


def test_the_key_document_requests_code_makes_are_never_changed():
    key_request = {"group": "Key documents", "item": "This year's questionnaire", "decision": "request", "priority": "blocking",
                   "reason": "It is the main source.", "flags": ["key_document"]}
    out = {"requests": [key_request], "provided": [], "not_needed": [], "accountant_questions": []}
    body, pol, points = PO.build_input({}, out, [NO_ROUNDING])
    assert points == [] and "This year's questionnaire" not in body
    assert PO.apply(out, {"points": [], "added": []}, body, pol, points)["requests"] == [key_request]


def test_when_the_policy_check_fails_the_precheck_stands_and_says_so(env):
    smith_job(env, [NO_ROUNDING])

    def broken(messages, kwargs):
        raise RuntimeError("the model could not be reached")

    llm.set_fake("policy", broken)
    result = env.run("1")
    assert result["status"] in ("complete", "partial")
    assert "could not run" in result["precheck"]["policy_check"]["error"]


def test_feedback_on_a_policy_has_the_ai_revise_it(env):
    seen: dict = {}

    def revise(messages, kwargs):
        seen["body"] = messages[-1].content
        text = json.dumps({"title": "Sold rentals: settlement statement", "text": "When a rental was sold, ask only for the settlement statement.",
                           "summary": "Shortened, as asked."})
        return AIMessage(content=text, usage_metadata={"input_tokens": 50, "output_tokens": 30, "total_tokens": 80})

    llm.set_fake("policy", revise)
    out = runner.revise_policy_now({"feedback_id": 3, "policy_id": 7, "job_id": "1", "title": NO_ROUNDING["title"], "text": NO_ROUNDING["text"],
                                    "scope_label": NO_ROUNDING["scope_label"], "feedback": "Make it shorter.", "context": ""})
    assert out["text"].startswith("When a rental was sold")
    assert "Accountant's feedback: Make it shorter." in seen["body"]
    event = env.pm.events[-1]
    assert event["run_id"] == "policy-3" and event["type"] == "ai_policy.revised" and event["result"]["summary"] == "Shortened, as asked."


def test_the_chat_answers_about_the_point_it_is_asked_about(env):
    smith_job(env, [NO_ROUNDING])
    llm.set_fake("policy", answering_policy(lambda body: {"points": [], "added": []}))
    result = env.run("1")
    item = result["precheck"]["requests"][0]["item"]
    env.pm.jobs["1"]["last_precheck_result"] = result["precheck"]
    seen: dict = {}
    llm.set_fake("assistant", answering({"answer": "It is needed.", "status": "answered", "outside_job": False, "points": []}, seen))
    ask.answer(env.pm.jobs["1"], f'About the pre-check point "{item}": why is this needed?')
    first = next(line for line in seen["body"].splitlines() if line.startswith("K1 | "))
    assert "[Pre-check result]" in first and item in first
    assert "QUESTION AREA: the pre-check" in seen["body"]


def test_the_review_builds_on_the_precheck_result_in_the_knowledge_store(env):
    from .test_review import add_review_job, review_folder

    review_folder(env)
    add_review_job(env)
    job = env.pm.jobs["1"]
    scope = Scope.of(job)
    from precheck_agent import memory

    memory.remember_precheck(scope, {"decision": {"label": "Requests to send", "reason": "1 item is still needed."},
                                     "requests": [{"group": "Tax", "item": "Provisional tax paid", "reason": "To work out tax to pay."}]})
    env.run("1", mode="review")
    body = next(c for c in env.precheck.calls if "THIS YEAR'S DRAFT FINANCIAL STATEMENTS" in c["messages"][-1].content)["messages"][-1].content
    assert "== WHAT THE PRE-CHECK CONCLUDED FOR THIS TASK" in body
    assert "Pre-check item to request from the client: Provisional tax paid (Tax)" in body


def test_freeing_a_tasks_memory_removes_its_documents_and_results_but_not_the_firms_rules(env):
    smith_job(env, [])
    env.run("1")
    job = env.pm.jobs["1"]
    scope = Scope.of(job)
    kn, store = get_knowledge(), get_store()
    assert kn.count(scope) > 0 and store.get_manifest("client-s", "1")
    kn.put(Scope(team="", vendor="", project="", task="lesson"), "skill", [{"id": "lesson:1", "text": "A firm rule.", "embedding": get_embedder().embed(["A firm rule."])[0]}])
    out = runner.flush_job("client-s", "1")
    assert out["entries"] > 0 and out["files"] > 0
    assert kn.count(scope) == 0 and kn.count(scope, source_types=["precheck_result"]) == 0
    assert store.get_manifest("client-s", "1") == {}
    assert len(kn.col.get(ids=["lesson:1"])["ids"]) == 1
    # A later run reads the folder again from the start.
    again = env.run("1")
    assert again["trail"]["read"]["documents"] > 0 and store.get_manifest("client-s", "1")
