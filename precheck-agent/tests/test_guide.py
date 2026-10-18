"""The preparation guide: after the pre-check, the steps to prepare this year's statements with the
figures from the documents and how to verify each; code checks every figure and source."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import llm

from .test_precheck import ACCOUNT, ready_folder


def scripted(answer: dict):
    def responder(messages, kwargs):
        return AIMessage(content=json.dumps(answer), usage_metadata={"input_tokens": 9000, "output_tokens": 1200, "total_tokens": 10200},
                         response_metadata={"stop_reason": "end_turn"})
    return responder


def test_the_guide_reads_what_the_precheck_reads_plus_its_result(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.pm.jobs["1"]["last_precheck"] = {"business_nature": {"label": "Residential rental"},
                                         "requests": [{"group": "ASB loan", "item": "Annual loan summary"}],
                                         "preparer_notes": [{"text": "Interest is fully deductible from 1 April 2025."}]}
    result = env.run("1", mode="guide")
    assert result["status"] == "complete" and result["mode"] == "guide" and len(env.precheck.calls) == 1
    body = env.precheck.calls[0]["messages"][-1].content
    system = env.precheck.calls[0]["messages"][0].content
    assert "# Skill: nz-preparation-guide" in system
    assert f"B1 | {ACCOUNT}" in body and "Still requested from the client: ASB loan — Annual loan summary" in body
    assert "Note for the preparer: Interest is fully deductible from 1 April 2025." in body
    assert "items: everything this year's accounts need" not in body  # the pre-check's answer instructions are replaced
    guide = result["guide"]
    assert guide["steps"] and guide["steps"][0]["area"] == "Bank" and guide["steps"][0]["sources"][0]["id"] == "B1"
    assert result["readiness"] == "Preparation guide" and "review" not in result
    again = env.run("1", mode="guide")
    assert len(env.precheck.calls) == 1 and again["guide"]["how"] == "cache"  # nothing changed: not paid again


def test_code_checks_every_figure_and_source_in_the_guide(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.precheck = llm.set_fake("precheck", scripted({"summary": "Two steps.", "steps": [
        {"area": "Rates", "step": "Account for rates of 853.00 paid from the ANZ account to Auckland Council.", "check": "Agree to the rates statement.",
         "waits_on_client": False, "sources": ["B1.2", "Z9"]},
        {"area": "Interest", "step": "Accrue interest of 99,999.00 on the ASB loan.", "check": "Agree to the loan summary.",
         "waits_on_client": True, "sources": []},
        {"area": "Rates", "step": "Account for rates of 853.00 paid from the ANZ account to Auckland Council.", "check": "Duplicate.",
         "waits_on_client": False, "sources": ["B1"]},
    ]}))
    guide = env.run("1", mode="guide")["guide"]
    rates, interest = guide["steps"]
    assert [s["id"] for s in rates["sources"]] == ["B1.2"] and rates["flags"] == []  # Z9 does not exist
    assert interest["flags"] == ["no_source", "figure_not_in_documents"] and interest["waits_on_client"]
    assert len(guide["steps"]) == 2  # the duplicate was dropped
    assert guide["decision"]["reason"] == "2 steps; 1 waits on information from the client."
