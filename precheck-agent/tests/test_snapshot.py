"""The Job Snapshot (AFIT design requirements, 16 Nov 2026): the pre-check's first output, the story of
the client and its year. Code works out every figure from the records, with the line each came from;
the model writes the words, which code checks."""
from precheck_agent import memory
from precheck_agent import snapshot as JS

from .test_precheck import ready_folder


def run(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    return env.run("1")


def test_the_snapshot_comes_first_with_figures_worked_out_by_code(env):
    result = run(env)
    p = result["precheck"]
    assert next(iter(p)) == "snapshot"  # the first thing the preparer sees
    s = p["snapshot"]
    f = s["figures"]
    assert f["available"] and f["basis"] == "trial_balance" and f["comparative_label"] == "Year before"
    kpis = {k["label"]: k for k in f["kpis"]}
    # Last year's trial balance: rental income 31,200 (29,900 the year before); four expenses.
    assert kpis["Revenue"]["amount"] == 31200 and kpis["Revenue"]["comparative"] == 29900 and kpis["Revenue"]["change_pct"] == 4
    assert kpis["Expenses"]["amount"] == 22630.18 and kpis["Expenses"]["comparative"] == 23002
    assert kpis["Net profit"]["amount"] == 8569.82 and kpis["Net profit"]["comparative"] == 6898
    assert [e["label"] for e in f["expenses"]][0] == "Interest"
    # What it owns and how that is funded, grouped by what each balance is.
    assert [(g["label"], g["amount"]) for g in f["asset_mix"]] == [("Cash and bank", 4210)]
    funding = {g["label"]: g for g in f["funding_mix"]}
    assert funding["Bank borrowing"]["amount"] == 418000 and funding["Bank borrowing"]["lines"][0]["label"] == "ASB Home loan"
    assert funding["Shortfall (owed more than the recorded assets)"]["derived"]
    # Every figure opens to the line it came from.
    src = f["income"][0]["source"]
    assert src["id"].startswith("T") and src["label"].startswith("Last year's trial balance: ")
    assert p["evidence"][src["evidence_id"]]["file_name"].startswith("Final TB 2025.xlsx")
    # The model's words, with checked sources and a status for each event.
    assert s["written"] and s["business_story"].startswith("Demo:")
    assert s["events"][0]["status"] == "inferred" and s["events"][0]["sources"][0]["label"].startswith("Questionnaire:")
    assert s["changes"] == []  # the first pre-check


def test_what_changed_since_the_last_precheck_is_said(env):
    run(env)
    job = env.pm.jobs["1"]
    job["last_precheck_result"] = {"snapshot": {"figures": {"available": True, "kpis": [{"label": "Revenue", "amount": 25000}], "this_year": None}}}
    job["direction_items"] = [{"id": "D1", "text": "Check the rent schedule"}]  # a new input, so the answer is not reused
    s = env.run("1")["precheck"]["snapshot"]
    assert s["changes"] == ["Revenue is now 31,200 (was 25,000 in the last pre-check)."]


def test_the_models_words_are_checked():
    valid = lambda ids: [i for i in ids if i in {"Q1", "T2"}]  # noqa: E731
    known = lambda text: all(n in ("75", "25", "31,200") for n in __import__("re").findall(r"\d[\d,]*", text))  # noqa: E731
    raw = {
        "business_story": "Rents one house for 31,200 a year.", "financial_story": "Profit rose by 48,000.",
        "revenue_sources": [{"label": "Rent", "detail": "One house", "sources": ["Q1", "X9"]}],
        "events": [{"text": "Bought a car.", "kind": "purchase", "status": "confirmed", "sources": []},
                   {"text": "Refinanced the loan.", "kind": "financing", "status": "confirmed", "sources": ["Q1"]}],
        "ownership": {"shareholders": [{"name": "John", "percent": 75, "sources": ["Q1"]}, {"name": "Kate", "percent": 60, "sources": []}],
                      "note": "", "sources": []},
        "current_accounts": "", "focus_areas": [{"area": "Loan", "why": "Refinanced.", "sources": ["T2"]}],
        "understood": [{"text": "Read the questionnaire.", "status": "confirmed", "sources": ["Q1"]}],
    }
    c = JS.clean(raw, valid, known)
    assert c["revenue_sources"][0]["sources"] == ["Q1"]  # an id not in the input is dropped
    assert c["story_flags"] == [] and c["financial_flags"] == ["figure_not_in_documents"]
    assert c["events"][0]["status"] == "inferred"  # "confirmed" with no source is only inferred
    assert c["events"][1]["status"] == "confirmed"
    # A percentage stands only when a document states it.
    assert [(h["name"], h["percent"]) for h in c["ownership"]["shareholders"]] == [("John", 75.0), ("Kate", None)]
    assert JS.clean(None, valid, known) is None


def test_ownership_that_adds_up_to_more_than_everything_is_not_shown():
    raw = {"ownership": {"shareholders": [{"name": "A", "percent": 75, "sources": ["Q1"]}, {"name": "B", "percent": 75, "sources": ["Q1"]}],
                         "note": "", "sources": []}}
    c = JS.clean(raw, lambda ids: ids, lambda text: True)
    assert [h["percent"] for h in c["ownership"]["shareholders"]] == [None, None]


def test_the_chat_can_find_the_snapshot(env):
    p = run(env)["precheck"]
    texts = [e["text"] for e in memory.precheck_entries(p)]
    assert any(t.startswith("Job Snapshot figures, worked out by code from last year's trial balance: Revenue 31,200.00") for t in texts)
    assert any(t.startswith("Job Snapshot - how it is funded, by code: Bank borrowing") for t in texts)


def test_the_precheck_answer_shape_stays_small_enough_for_the_api():
    """With the Job Snapshot in it the API refused the pre-check's answer shape ("the compiled grammar is too
    large", 19 Nov 2026): every list of ids is now one shared definition, which the API accepts."""
    from precheck_agent.precheck import SCHEMA

    def raw_id_lists(v) -> int:
        if isinstance(v, dict):
            here = 1 if v.get("type") == "array" and v.get("items") == {"type": "string"} else 0
            return here + sum(raw_id_lists(x) for k, x in v.items() if k != "$defs")
        return sum(raw_id_lists(x) for x in v) if isinstance(v, list) else 0

    assert raw_id_lists(SCHEMA) == 0 and SCHEMA["$defs"]["ids"] == {"type": "array", "items": {"type": "string"}}
    assert "snapshot" in SCHEMA["required"] and SCHEMA["properties"]["items"]["items"]["properties"]["sources"] == {"$ref": "#/$defs/ids"}


def test_a_finding_carries_its_label_and_level_in_the_text_so_the_answer_shape_compiles():
    """The API compiles the answer shape into a grammar and refused it as too large with "label" and "level" as
    fields of their own (every pre-check failed, 23 Nov 2026): a finding is {text, status, sources}, and code
    splits "[high] Label: text" back out."""
    finding = JS.SCHEMA["properties"]["sections"]["items"]["properties"]["findings"]["items"]
    assert sorted(finding["properties"]) == ["sources", "status", "text"]
    raw = {"sections": [
        {"key": "key_risks", "summary": "Two risks.", "findings": [
            {"text": "[high] Revenue cut-off: sales after March were booked early.", "status": "confirmed", "sources": ["Q1"]},
            {"text": "Plain text with no label.", "status": "inferred", "sources": []}]},
        {"key": "nature_of_business", "summary": "A shop.", "findings": [
            {"text": "[high] Main income: retail sales.", "status": "confirmed", "sources": ["Q1"]}]}]}
    out = JS.clean(raw, lambda ids: [i for i in ids if i == "Q1"], lambda text: True)
    sec = {s["key"]: s for s in out["sections"]}
    risk, plain = sec["key_risks"]["findings"]
    assert (risk["label"], risk["level"], risk["text"]) == ("Revenue cut-off", "high", "Sales after March were booked early.")
    assert (plain["label"], plain["level"], plain["text"]) == ("", "none", "Plain text with no label.")
    # a level only means something for a key risk
    assert sec["nature_of_business"]["findings"][0]["level"] == "none"
