"""The pre-check: three key documents first, then one professional pre-check whose output is the
request list (with decisions and reasons) and the drafted email."""
import json
import zipfile
from datetime import datetime

from langchain_core.messages import AIMessage

from precheck_agent import llm
from precheck_agent import precheck as P
from precheck_agent.config import get_settings
from precheck_agent.textutil import est_tokens

from .conftest import write_xlsx

ACCOUNT = "01-0123-0456789-00"
TB = [
    ["Trial Balance"], ["Smith Rentals"], ["As at 31 March 2025"], [],
    ["Account Code", "Account", "Account Type", "Debit - Year to date", "Credit - Year to date", "31 Mar 2024"],
    [200, "Rental income", "Revenue", None, 31200, -29900],
    [410, "Body corporate levies", "Expense", 2400, None, 2300],
    [420, "Rates", "Expense", 3412, None, 3300],
    [430, "Interest", "Expense", 14322.18, None, 15010],
    [440, "Property management fees", "Expense", 2496, None, 2392],
    [680, "ANZ Rental Account", "Current Asset", 4210, None, 3100],
    [800, "ASB Home loan", "Non-current Liability", None, 418000, -424000],
]
CQ = (
    "Client Questionnaire 2026\nName: John and Kate Smith\nDid you own any rental properties this year? Yes, 12 Kauri Street, Mt Albert\n"
    "Is the property managed by a property manager? Yes, Barfoot & Thompson\nDid you open any new bank accounts? No\n"
    "Did you refinance any loans? Yes, the ASB loan was refinanced in October 2025\nWas a rental bond held? Yes, bond lodged with Tenancy Services\n"
    "Did you attend a body corporate annual meeting? Yes, in November 2025\nDid you buy or sell any property? No\n"
)


def bank_rows():
    rows, balance = [], 4210.0
    for when, typ, who, amount in [(datetime(2025, 4, 2), "Credit", "Barfoot & Thompson", 2390.0), (datetime(2025, 6, 15), "Bill", "Auckland Council rates", -853.0),
                                   (datetime(2025, 9, 1), "Bill", "Body Corporate 1234", -600.0), (datetime(2026, 3, 30), "Credit", "Barfoot & Thompson", 2390.0)]:
        balance = round(balance + amount, 2)
        rows.append([when, typ, who, amount, balance])
    return [["Transaction Date", "Type", "Details", "Amount", "Balance"]] + rows[::-1]


def ready_folder(env, name="smith", questionnaire=True, fs=True, workpapers=True):
    """A zip like a real task folder: last year's pack in …/2025/, this year's documents in …/2026/."""
    src = env.tmp / f"{name}-src"
    (src / "2025").mkdir(parents=True)
    (src / "2026").mkdir(parents=True)
    if workpapers:
        write_xlsx(src / "2025" / "Final TB 2025.xlsx", {"Trial Balance": TB})
    if fs:
        (src / "2025" / "Smith 2025 Financial Statements - Signed.txt").write_text(
            "Financial Statements\nFor the year ended 31 March 2025\nStatement of Profit or Loss\nRental income 31,200 29,900\n"
            "Body corporate levies 2,400 2,300\nInterest 14,322 15,010\n", encoding="utf-8")
    (src / "2025" / "ANZ Balance 2025.txt").write_text(f"Account number {ACCOUNT}\nClosing balance 4,210.00\n", encoding="utf-8")
    if questionnaire:
        (src / "2026" / "Client Questionnaire 2026.txt").write_text(CQ, encoding="utf-8")
    write_xlsx(src / "2026" / f"{ACCOUNT}_Transactions_2025-04-01_2026-03-31.xlsx", {"Transactions": bank_rows()})
    folder = env.drive_root / name
    folder.mkdir()
    with zipfile.ZipFile(folder / "Smith.zip", "w") as z:
        for path in sorted(src.rglob("*")):
            if path.is_file():
                z.write(path, "Smith/" + path.relative_to(src).as_posix())
    return folder


def test_without_the_questionnaire_the_precheck_stops_and_asks_for_it(env):
    ready_folder(env, questionnaire=False)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    result = env.run("1")
    p = result["precheck"]
    assert result["status"] == "complete" and result["readiness"] == "Blocked" and result["verdict"] == "not_ready"
    assert p["decision"]["state"] == "blocked" and "client questionnaire" in p["decision"]["reason"]
    assert not env.precheck.calls  # nothing else is worked out without it
    found = {k["role"]: k for k in p["key_documents"]}
    assert not found["questionnaire"]["found"] and found["last_year_fs"]["found"] and found["last_year_workpapers"]["found"]
    assert found["last_year_fs"]["files"][0]["name"].startswith("Smith 2025 Financial Statements - Signed.txt")
    assert [r["item"] for r in p["requests"]] == ["Your completed client questionnaire for the year to 31 March 2026"]
    email = p["email"]
    assert "questionnaire" in email["body"] and "ask you once" in email["body"] and "2026" in email["subject"]
    assert result["trail"]["compared"]["label"].startswith("Key documents: client questionnaire missing")


def test_last_years_statements_and_workpapers_are_needed_too(env):
    ready_folder(env, fs=False, workpapers=False)
    env.pm.add_job("1", "client-s", "smith", direction=[])
    p = env.run("1")["precheck"]
    assert p["decision"]["state"] == "blocked" and not env.precheck.calls
    asked = " ".join(r["item"] for r in p["requests"])
    assert "Last year's financial statements" in asked and "Last year's workpapers" in asked and "questionnaire" not in asked
    assert "closing balances" in p["email"]["body"] and "fixed assets, loans" in p["email"]["body"]


def test_last_years_questionnaire_is_not_this_years(env):
    folder = ready_folder(env, questionnaire=False)
    with zipfile.ZipFile(folder / "Smith.zip", "a") as z:
        z.writestr("Smith/2025/Client Questionnaire 2025.txt", "Client Questionnaire 2025\nDid you own rentals? Yes\n")
    env.pm.add_job("1", "client-s", "smith", direction=[])
    p = env.run("1")["precheck"]
    q = next(k for k in p["key_documents"] if k["role"] == "questionnaire")
    assert not q["found"] and "earlier year" in q["note"]


def test_with_all_three_the_precheck_lists_what_is_needed_with_reasons(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[{"id": "D1", "text": "Check the refinance documents carefully"}])
    env.pm.jobs["1"]["client_name"] = "John and Kate Smith"
    result = env.run("1")
    p = result["precheck"]
    assert result["status"] == "complete" and len(env.precheck.calls) == 1
    assert {k["role"] for k in p["key_documents"] if k["found"]} == {"questionnaire", "last_year_fs", "last_year_workpapers"}

    # The model read the questionnaire line by line, last year's statements, TB and workpapers,
    # the files received, the bank as summarised by code, the code checks and the Direction Note.
    body = env.precheck.calls[0]["messages"][-1].content
    for marker in ("Q1 | Client Questionnaire 2026", "F1 | Financial Statements", "T1 | Rental income", "W1 | Final TB 2025.xlsx",
                   "D1 | ", "B1 | " + ACCOUNT, "B1.1 | Barfoot & Thompson", "C1 | This year's opening bank balance", "N1 | Check the refinance documents"):
        assert marker in body, marker
    system = env.precheck.calls[0]["messages"][0].content
    assert "# Skill: precheck-method" in system and "# Skill: nz-residential-rental" in system and "Rent bond" in system

    nature = p["business_nature"]
    assert nature["type"] == "residential_rental" and nature["label"] == "Residential rental" and nature["sources"][0]["label"].startswith("Questionnaire:")
    assert p["provided"] and p["provided"][0]["documents"][0]["label"].startswith(f"{ACCOUNT}_Transactions")
    assert p["requests"] and all(r["reason"] and r["sources"] for r in p["requests"])
    src = p["requests"][0]["sources"][0]
    assert src["label"].startswith("Last year's trial balance: ") and p["evidence"][src["evidence_id"]]["file_name"].startswith("Final TB 2025.xlsx")
    assert p["decision"]["state"] == "requests" and result["readiness"] == "Requests to send"

    # The email is written by code from the checked list: every request, its reason, nothing else.
    email = p["email"]
    assert email["body"].startswith("Hi John and Kate Smith,")
    for r in p["requests"]:
        assert f"- {r['item']}: {r['reason']}" in email["body"]
    assert all(i["item"] not in email["body"] for i in p["provided"])

    # Nothing changed: the pre-check is not paid for again.
    again = env.run("1")
    assert len(env.precheck.calls) == 1 and again["precheck"]["how"] == "cache" and again["usage"]["model_calls"] == 0


def scripted(answer: dict):
    def responder(messages, kwargs):
        return AIMessage(content=json.dumps(answer), usage_metadata={"input_tokens": 9000, "output_tokens": 1500, "total_tokens": 10500},
                         response_metadata={"stop_reason": "end_turn"})
    return responder


def test_code_holds_the_answer_to_what_is_really_in_the_folder(env):
    ready_folder(env)
    env.pm.add_job("1", "client-s", "smith", direction=[], lessons=[{"id": 7, "scope": "client", "precheck_type": "residential_rental",
                                                                     "kind": "not_needed", "item": "Home office", "note": "Barfoot manages everything: no home office."}])
    env.precheck = llm.set_fake("precheck", scripted({
        "business_nature": {"type": "residential_rental", "summary": "One rental property managed by Barfoot.", "reasoning": "Q3 and Q4 say so; rent 31,200 last year.",
                            "sources": ["Q3", "Q99"], "facts": [{"text": "Refinanced in October 2025.", "sources": ["Q6"]}]},
        "items": [
            {"group": "ASB loan", "item": "Refinancing documents", "decision": "request", "reason": "The questionnaire says the ASB loan was refinanced.", "sources": ["Q6"], "documents": []},
            {"group": "ASB loan", "item": "refinancing documents", "decision": "request", "reason": "Duplicate.", "sources": ["Q6"], "documents": []},
            {"group": "12 Kauri Street", "item": "Property manager annual summary", "decision": "already_provided", "reason": "Received.", "sources": [], "documents": []},
            {"group": "Tax", "item": "Rental income summary", "decision": "request", "reason": "Rent was 45,000 last year.", "sources": ["T1"], "documents": []},
            {"group": "12 Kauri Street", "item": "Home office details", "decision": "not_needed", "reason": "Lesson L7: the property is fully managed.", "sources": ["Q4"], "documents": []},
            {"group": "Bank", "item": "ANZ statements", "decision": "already_provided", "reason": "Received.", "sources": ["B1"], "documents": ["D2", "D999"]},
        ],
        "preparer_notes": [{"text": "Interest is fully deductible from 1 April 2025.", "sources": ["T4"]}, {"text": "Profit will be 99,999.", "sources": []}],
        "lessons_applied": ["L7", "L8"],
    }))
    p = env.run("1")["precheck"]
    requests = {r["item"]: r for r in p["requests"]}
    assert list(requests) == ["Refinancing documents", "Property manager annual summary", "Rental income summary"]  # duplicate dropped
    assert requests["Property manager annual summary"]["flags"] == ["no_file_named", "no_source"]  # "provided" but no file: ask
    assert requests["Rental income summary"]["flags"] == ["figure_not_in_documents"]  # 45,000 is not in the documents
    assert requests["Refinancing documents"]["flags"] == [] and requests["Refinancing documents"]["sources"][0]["label"].startswith("Questionnaire: Did you refinance")
    assert [i["item"] for i in p["not_needed"]] == ["Home office details"]
    provided = p["provided"][0]
    assert len(provided["documents"]) == 1  # D999 does not exist
    assert [s["id"] for s in p["business_nature"]["sources"]] == ["Q3"]  # Q99 does not exist
    assert [n["text"] for n in p["preparer_notes"]] == ["Interest is fully deductible from 1 April 2025."]  # 99,999 is invented
    assert [lesson["id"] for lesson in p["lessons_applied"]] == ["L7"]
    assert "Rental income summary" in p["email"]["body"] and "Home office" not in p["email"]["body"]


def test_lessons_and_a_fixed_business_nature_reach_the_model(env):
    ready_folder(env)
    lessons = [{"id": 3, "scope": "firm", "precheck_type": "residential_rental", "kind": "not_needed", "item": "Bank confirmation",
                "note": "Do not ask for a bank confirmation letter when statements cover the year."}]
    env.pm.add_job("1", "client-s", "smith", direction=[], precheck_type="investment", lessons=lessons)
    p = env.run("1")["precheck"]
    body = env.precheck.calls[0]["messages"][-1].content
    assert "business nature fixed by AFIT: Investment" in body
    assert "L3 | all Residential rental | not_needed | item: Bank confirmation | Do not ask for a bank confirmation letter" in body
    assert p["business_nature"]["type"] == "investment" and p["business_nature"]["fixed"]
    assert [lesson["id"] for lesson in p["lessons_applied"]] == ["L3"]


def test_the_input_is_shortened_to_fit_the_cap(env, monkeypatch):
    folder = ready_folder(env)
    with zipfile.ZipFile(folder / "Smith.zip", "a") as z:
        z.writestr("Smith/2025/Smith 2025 Notes to the Financial Statements.txt",
                   "Financial Statements\nFor the year ended 31 March 2025\n" + "\n".join(f"Note line {n} about the accounts" for n in range(3000)))
    monkeypatch.setenv("PRECHECK_PRECHECK_MAX_INPUT_TOKENS", "6000")
    get_settings.cache_clear()
    env.pm.add_job("1", "client-s", "smith", direction=[])
    env.run("1")
    body = env.precheck.calls[0]["messages"][-1].content
    assert est_tokens(body) <= 9000 and "more lines not shown" in body and "Q1 | Client Questionnaire 2026" in body


def test_nothing_is_shared_between_clients(env):
    ready_folder(env, "one")
    ready_folder(env, "two")
    env.pm.add_job("1", "client-one", "one", direction=[])
    env.pm.add_job("2", "client-two", "two", direction=[])
    env.run("1")
    env.run("2")
    assert len(env.precheck.calls) == 2  # identical folders, but no answer crosses clients
    assert P.cache_key("a", "1", "x", get_settings()) != P.cache_key("b", "1", "x", get_settings())


def test_figures_check():
    known = P.known_numbers("T1 | Rental income | -31,200.00 | year before -29,900.00")
    assert P.figures_ok("Rent was 31,200 last year, down from 29,900.", known)
    assert P.figures_ok("Refinanced in October 2025; 12 months; 15% of rent.", known)  # years, counts, percentages
    assert not P.figures_ok("Rent was 45,000.", known)
