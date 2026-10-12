"""Ask the AI: answers from the knowledge store only — this task's tags first, then meaning, then
exact words — with every citation checked by code."""
import json

from langchain_core.messages import AIMessage

from precheck_agent import ask, llm, runner
from precheck_agent.knowledge import Scope

from .test_review import add_review_job, review_folder

SETTLEMENT = ("Settlement Statement\nVendor: Smith Rentals Ltd\nProperty: 43 Te Wharo Drive, Papamoa\nSettlement date 2 October 2025\n"
              "Purchase price 845,000.00\nLess mortgage repaid to ASB 312,400.00\nBalance to vendor 520,113.45\n")
FILLER = ["Insurance renewal for the rental at Kauri Street, premium 1,840.00",
          "Rates instalment Tauranga City Council 1,120.50 paid by direct debit",
          "Property manager monthly statement: rent received, management fee, letting fee"]


def folder_with_sale(env):
    root = review_folder(env)
    (root / "2026" / "Sale" ).mkdir()
    (root / "2026" / "Sale" / "Settlement Statement.txt").write_text(SETTLEMENT, encoding="utf-8")
    for n, text in enumerate(FILLER):
        (root / "2026" / f"Other {n}.txt").write_text(text + "\n", encoding="utf-8")
    add_review_job(env)
    env.run("1", mode="review")  # reads and indexes the folder
    return env.pm.jobs["1"]


def test_tags_meaning_and_exact_words_find_the_passage(env):
    job = folder_with_sale(env)
    files = {fid: {**row, "file_id": fid} for fid, row in __import__("precheck_agent.store", fromlist=["x"]).get_store().get_manifest("client-smith", "1").items()}
    hits = ask.retrieve(Scope.of(job), "How much was 43 Te Wharo Drive sold for?", files, None)
    assert any("845,000" in h["text"] for h in hits)
    # Exact words find it even when the meaning of the question points elsewhere.
    from precheck_agent.embeddings import get_embedder
    from precheck_agent.knowledge import get_knowledge

    unrelated = get_embedder().embed(["insurance premium renewal"])[0]
    assert [h for h in get_knowledge().search(Scope.of(job), unrelated, 1, contains="Te Wharo") if "845,000" in h["text"]]
    assert ask.tag_filters("What was last year's bank closing balance?") == {"year_role": ["prior", "older"], "doc_class": ["bank"]}
    assert ask.key_terms("How much was 43 Te Wharo Drive sold for?")[:2] == ["43 Te Wharo Drive", "Te Wharo Drive"]
    # Review knowledge is found too: the assumption and the reviewer's feedback.
    kinds = {h["source_type"] for h in ask.retrieve(Scope.of(job), "Why was the hot water cylinder treated as a repair?", files, None)}
    assert "assumption" in kinds


def test_an_answer_cites_only_what_was_found_and_never_invents_a_figure(env):
    job = folder_with_sale(env)
    seen = {}

    def responder(messages, kwargs):
        seen["body"] = messages[-1].content
        seen["system"] = messages[0].content if isinstance(messages[0].content, str) else messages[0].content[0]["text"]
        k = next(ln.split(" | ")[0] for ln in seen["body"].splitlines() if "845,000" in ln)
        return AIMessage(content=json.dumps({"answer": "It settled on 2 October 2025 for $845,000.00; the vendor received 520,113.45 after the ASB loan of 999,999.",
                                             "sources": [k, "K99", "skill"], "status": "answered"}),
                         usage_metadata={"input_tokens": 3000, "output_tokens": 120, "total_tokens": 3120}, response_metadata={"stop_reason": "end_turn"})

    llm.set_fake("assistant", responder)
    out = ask.answer(job, "How much was 43 Te Wharo Drive sold for?", [{"question": "Who is the vendor?", "answer": "Smith Rentals Ltd."}])
    assert "# Skill: nz-fs-review" in seen["system"] and "Q: Who is the vendor?" in seen["body"]
    assert [s["label"].split(",")[0] for s in out["sources"]] == ["Settlement Statement.txt"] and out["skill"]  # K99 does not exist
    assert out["sources"][0]["evidence"]["quote"].startswith("Settlement Statement") or "845,000" in out["sources"][0]["evidence"]["quote"]
    assert out["flags"] == ["figure_not_in_documents"]  # 999,999 is not in any passage
    assert out["status"] == "answered"


def test_nothing_read_yet_and_nothing_found(env):
    env.pm.add_job("1", "client-empty", "nothing-here", direction=[])
    out = ask.answer(env.pm.jobs["1"], "What is the rental income?")
    assert out["status"] == "not_found" and "have not been read yet" in out["answer"] and not llm._fake.get("assistant")

    job = folder_with_sale(env)
    llm.set_fake("assistant", lambda m, k: AIMessage(content=json.dumps({"answer": "Yes.", "sources": [], "status": "answered"}),
                                                    usage_metadata={"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}))
    out = ask.answer(job, "Is there a home office?")
    assert out["status"] == "partial" and out["flags"] == ["no_source"]  # an answer with nothing behind it is not "answered"


def test_the_answer_goes_back_to_the_pm_application_as_an_event(env):
    folder_with_sale(env)
    result = runner.ask_now("1", "q-1", "Who manages the property?", [])
    event = env.pm.events[-1]
    assert event["run_id"] == "q-1" and event["type"] == "ai_assistant.answered" and event["result"]["answer"] == result["answer"]


def test_the_documents_own_words_are_found_whatever_the_question_calls_them(env):
    """Landm, 12 Oct 2026: "when did it settle" missed a "Settlement Statement" (matching is exact and
    case-sensitive) and "sold" missed "Sale"; meaning-only passages also crowded the exact ones out."""
    assert {"Sale", "Settlement"} <= set(ask.key_terms("When was it sold, and when did it settle?"))
    job = folder_with_sale(env)
    files = {fid: {**row, "file_id": fid} for fid, row in __import__("precheck_agent.store", fromlist=["x"]).get_store().get_manifest("client-smith", "1").items()}
    hits = ask.retrieve(Scope.of(job), "when did it settle?", files, None)
    assert any("845,000" in h["text"] and h["how"].startswith("words") for h in hits)
    assert hits[0]["how"].startswith("words")  # exact matches lead the list
