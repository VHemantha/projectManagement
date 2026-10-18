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


def answering(answer: dict, seen: dict | None = None):
    def responder(messages, kwargs):
        if seen is not None:
            seen["body"] = messages[-1].content
            seen["system"] = messages[0].content if isinstance(messages[0].content, str) else messages[0].content[0]["text"]
            seen["k"] = next((ln.split(" | ")[0] for ln in seen["body"].splitlines() if "845,000" in ln), "K1")
        body = json.dumps(answer(seen) if callable(answer) else answer)
        return AIMessage(content=body, usage_metadata={"input_tokens": 3000, "output_tokens": 120, "total_tokens": 3120},
                         response_metadata={"stop_reason": "end_turn"})
    return responder


def test_each_point_says_where_it_comes_from_and_document_points_are_checked(env):
    """AFIT, 18 Oct 2026: Ask answers from general knowledge too, NZ standards and law first, and says
    exactly where it went beyond the task's documents and NZ standards."""
    job = folder_with_sale(env)
    seen: dict = {}
    llm.set_fake("assistant", answering(lambda s: {
        "answer": "It settled for 845,000.00; the gain may be taxable under the bright-line test.", "status": "answered", "outside_job": False,
        "points": [
            {"text": "The property sold for 845,000.00 and settled on 2 October 2025.", "basis": "task_documents", "sources": [s["k"], "K99"], "reference": ""},
            {"text": "The vendor received 999,999.00.", "basis": "task_documents", "sources": [s["k"]], "reference": ""},
            {"text": "Residential land sold within 2 years of purchase is taxed under the bright-line test.", "basis": "nz_standards_law",
             "sources": [], "reference": "Income Tax Act 2007, s CB 6AA"},
            {"text": "In Australia a 50% CGT discount would apply.", "basis": "general_knowledge", "sources": [], "reference": "Australian tax law"},
            {"text": "Buyers usually pay a deposit of 10%.", "basis": "task_documents", "sources": [], "reference": ""},
        ]}, seen))
    out = ask.answer(job, "How much was 43 Te Wharo Drive sold for, and is it taxable?", [{"question": "Who is the vendor?", "answer": "Smith Rentals Ltd."}])
    assert "nz_standards_law" in seen["system"] and "Companies Act 1993" in seen["system"] and "Q: Who is the vendor?" in seen["body"]
    sold, invented, brightline, australia, uncited = out["points"]
    assert sold["basis"] == "task_documents" and [x["label"].split(",")[0] for x in sold["sources"]] == ["Settlement Statement.txt"]  # K99 does not exist
    assert invented["flags"] == ["figure_not_in_documents"]  # 999,999 is in no document
    assert brightline["basis"] == "nz_standards_law" and brightline["reference"] == "Income Tax Act 2007, s CB 6AA" and brightline["flags"] == []
    assert australia["basis"] == "general_knowledge" and out["beyond_nz"]
    assert uncited["basis"] == "general_knowledge" and uncited["flags"] == ["no_source"]  # "from the documents" with no source: not passed off as such
    assert out["status"] == "answered" and not out["outside_job"]
    assert set(out["flags"]) == {"figure_not_in_documents", "no_source"}


def test_general_questions_are_answered_even_before_the_documents_are_read(env):
    env.pm.add_job("1", "client-empty", "nothing-here", direction=[])
    seen: dict = {}
    llm.set_fake("assistant", answering({
        "answer": "Companies must keep accounting records for 7 years.", "status": "answered", "outside_job": True,
        "points": [{"text": "Accounting records must be kept for 7 years.", "basis": "nz_standards_law", "sources": [],
                    "reference": "Companies Act 1993, s 189; Tax Administration Act 1994, s 22"}]}, seen))
    out = ask.answer(env.pm.jobs["1"], "How long must a company keep its records?")
    assert "this task's documents have not been read yet" in seen["body"]
    assert out["status"] == "answered" and out["outside_job"] and out["points"][0]["basis"] == "nz_standards_law" and out["flags"] == []


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
