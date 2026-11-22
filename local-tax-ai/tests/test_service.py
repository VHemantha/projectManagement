"""Local_Tax_AI (AFIT, 22 Nov 2026): the LangGraph agents answer in their checked shapes; whatever the model
says, only lines the engagement has are kept, and no figure of the model's survives except a "what if" line and
amount, which the backend's engine then works out."""
import base64

import pytest
from fastapi.testclient import TestClient

from local_tax_ai import config, graphs

CONTEXT = {
    "engagement": {"entity_type": "company", "year_of_assessment": "2024/25"},
    "computation": {"payable": "65000.00", "lines": [], "rules": []},
    "reverse": {"expected": "70000.00", "calculated": "65000.00", "scenarios": [{"key": "capital_allowances:ca1", "label": "Capital allowances", "feasible": True}]},
    "levers": [{"key": "capital_allowances:ca1", "label": "Capital allowances (tax)", "amount": "1850000"},
               {"key": "add_backs:a1", "label": "Entertainment expenses", "amount": "250000"}],
    "financials": {"tb": [{"code": "6900", "name": "Sundry expenses", "amount": "12000", "heading": ""},
                          {"code": "4000", "name": "Sales", "amount": "-50000000", "heading": "revenue"}]},
    "headings": {"revenue": "Revenue", "admin_expenses": "Administrative expenses"},
    "alerts": [{"stage": "return", "severity": "review", "text": "Return field missing: Declaration."}],
}


@pytest.fixture(autouse=True)
def fake_mode(monkeypatch):
    monkeypatch.setenv("LOCAL_TAX_AI_LLM_MODE", "fake")
    monkeypatch.setenv("LOCAL_TAX_AI_SERVICE_TOKEN", "t")
    config.get_settings.cache_clear()
    yield
    config.get_settings.cache_clear()


def client():
    from local_tax_ai.api import app

    return TestClient(app)


def test_the_service_needs_its_token_and_names_itself():
    c = client()
    assert c.get("/healthz").json()["service"] == "Local_Tax_AI"
    assert c.post("/v1/chat", json={"context": CONTEXT, "question": "Hi"}).status_code == 401
    assert c.post("/v1/nothing", json={}, headers={"X-Local-Tax-Token": "t"}).status_code == 404


def test_a_what_if_names_a_real_line_and_the_new_amount_only():
    out = client().post("/v1/chat", json={"context": CONTEXT, "question": "What if entertainment expenses fall by Rs. 100,000?"},
                        headers={"X-Local-Tax-Token": "t"}).json()
    assert out["what_if"] == {"lever": "add_backs:a1", "proposed": "150000.0"}
    assert "65000.00" in out["answer"]


def test_the_check_step_drops_what_the_engagement_does_not_have(monkeypatch):
    monkeypatch.setattr(graphs, "demo", lambda agent, req, content: {
        "map_tb": {"suggestions": [{"code": "6900", "heading": "admin_expenses", "reason": "expense"}, {"code": "9999", "heading": "revenue", "reason": ""},
                                   {"code": "4000", "heading": "made_up", "reason": ""}], "notes": []},
        "chat": {"answer": "x", "points": [], "uncertain": False, "what_if": {"lever": "invented:1", "proposed": "10"}},
        "reverse": {"summary": "", "questions": ["Which line?"], "items": [{"title": "t", "text": "x", "reference": "", "lever": "nope", "severity": "high",
                                                                             "needs_review": True}]},
        "extract": {"kind": "trial_balance", "summary": "", "gaps": [], "lines": [{"description": "Sales", "amount": "(50,000,000.00)", "code": "4000",
                                                                                   "category": "", "comparative": "abc", "cite": "row 3"}]},
    }[agent])
    assert graphs.run("map_tb", {"context": CONTEXT})["suggestions"] == [{"code": "6900", "heading": "admin_expenses", "reason": "expense"}]
    assert graphs.run("chat", {"context": CONTEXT, "question": "?"})["what_if"] is None
    assert graphs.run("reverse", {"context": CONTEXT})["items"][0]["lever"] == ""
    line = graphs.run("extract", {"context": CONTEXT, "name": "tb.csv", "content_b64": base64.b64encode(b"a,b").decode()})["lines"][0]
    assert (line["amount"], line["comparative"]) == ("-50000000.00", "")


def test_the_reverse_agent_asks_the_accountant_which_line_to_review():
    out = graphs.run("reverse", {"context": CONTEXT})
    assert "Which income, expense, relief or tax-credit line should we review" in out["questions"][0]
    assert out["items"][0]["lever"] == "capital_allowances:ca1"


def test_documents_are_read_as_the_model_sees_them():
    from local_tax_ai import documents

    pdf = documents.blocks("TB.pdf", b"%PDF-1.4")
    assert pdf[0]["type"] == "document" and pdf[0]["source"]["media_type"] == "application/pdf"
    rows = documents.blocks("tb.csv", b"Code,Account,Debit\n4000,Sales,10")[0]["text"]
    assert "row 2 | 4000 | Sales | 10" in rows
    with pytest.raises(documents.Unreadable):
        documents.blocks("x.exe", b"MZ")


def test_phase_two_to_four_agents_answer_in_their_shapes():
    c, h = client(), {"X-Local-Tax-Token": "t"}
    pol = c.post("/v1/policies", json={"context": CONTEXT, "policies": [{"key": "ppe", "title": "PPE", "text": "Cost less depreciation."}]}, headers=h).json()
    assert [p["key"] for p in pol["policies"]] == ["ppe"]
    chk = c.post("/v1/rule-check", json={"rule": {"rule": "company.standard_rate", "value": 0.3}, "name": "act.txt",
                                         "content_b64": base64.b64encode(b"The rate is 30 per cent.").decode()}, headers=h).json()
    assert chk["agrees"] in ("yes", "no", "unclear")


def test_extracted_fixed_assets_keep_only_known_classes_and_real_dates():
    raw = {"kind": "fixed_assets", "summary": "", "gaps": [], "year_of_assessment": "2023-24",
           "lines": [{"description": "Lathe", "amount": "1,200,000", "category": "plant_machinery", "date": "2023-05-01", "code": "", "comparative": "", "cite": "row 2"},
                     {"description": "Van", "amount": "(5)", "category": "spaceships", "date": "May 2023", "code": "", "comparative": "", "cite": "row 3"}]}
    out = graphs.check({"agent": "extract", "raw": raw, "request": {"context": {"asset_classes": ["plant_machinery"]}}})["result"]
    assert [ln["category"] for ln in out["lines"]] == ["plant_machinery", ""]
    assert [ln["date"] for ln in out["lines"]] == ["2023-05-01", ""]
    assert out["lines"][0]["amount"] == "1200000" and out["lines"][1]["amount"] == "-5"
    assert out["year_of_assessment"] == ""


def test_a_shared_drive_folder_is_listed_and_its_files_downloaded(tmp_path, monkeypatch):
    folder = tmp_path / "client-folder"
    (folder / "bank").mkdir(parents=True)
    (folder / "bank" / "statement.csv").write_text("Date,Balance\n2025-03-31,554300\n")
    monkeypatch.setenv("LOCAL_TAX_AI_DRIVE_MODE", "local")
    monkeypatch.setenv("LOCAL_TAX_AI_LOCAL_DRIVE_ROOT", str(tmp_path))
    config.get_settings.cache_clear()
    c, h = client(), {"X-Local-Tax-Token": "t"}
    listed = c.post("/v1/drive/list", json={"folder_id": "client-folder"}, headers=h).json()
    assert [f["name"] for f in listed["files"]] == ["statement.csv"] and listed["files"][0]["path"] == "bank/"
    got = c.post("/v1/drive/download", json={"file_id": listed["files"][0]["id"]}, headers=h).json()
    assert base64.b64decode(got["content_b64"]).startswith(b"Date,Balance")
    assert c.post("/v1/drive/list", json={"folder_id": "not-shared"}, headers=h).status_code == 400
    assert c.post("/v1/drive/download", json={"file_id": "client-folder:../../etc/passwd"}, headers=h).status_code == 400


def test_prefill_keeps_only_known_fields_and_plain_numbers():
    raw = {"kind": "bank_confirmation", "summary": "", "period_end": "31/03/2025",
           "fields": [{"field": "tin", "value": " 114 567 890 ", "cite": "p1"}, {"field": "favourite_colour", "value": "red", "cite": ""},
                      {"field": "fy_end", "value": "March 2025", "cite": ""}],
           "lines": [{"list": "payments", "category": "WHT", "description": "WHT on interest", "amount": "(1,200.50)", "comparative": "", "code": "",
                      "date": "2025-03-31", "cite": "p2"}, {"list": "income", "category": "", "description": "x", "amount": "n/a", "comparative": "",
                                                            "code": "", "date": "", "cite": ""}],
           "balances": [{"bank": "BOC", "account": "****123", "date": "2025-03-31", "balance": "554,300.00", "cite": "p1"}],
           "flags": [{"kind": "inconsistent", "text": "Name differs from the client info.", "cite": "p1"}]}
    out = graphs.check({"agent": "prefill", "raw": raw, "request": {"context": {}}})["result"]
    assert out["fields"] == [{"field": "tin", "value": "114 567 890", "cite": "p1"}]
    assert [ln["amount"] for ln in out["lines"]] == ["-1200.50"]
    assert out["balances"][0]["balance"] == "554300.00" and out["period_end"] == ""
    assert out["flags"][0]["kind"] == "inconsistent"
