"""Test setup: a temp database, a local directory standing in for Drive, an in-memory PM
application and scripted models. The real graph, agents, storage and parsers run unchanged."""
import csv
import os
from pathlib import Path

import pytest
from openpyxl import Workbook


def write_xlsx(path: Path, sheets: dict[str, list[list]]):
    wb = Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(name)
        for row in rows:
            ws.append(row)
    wb.save(path)


TB_ROWS = [
    ["Code", "Account", "Debit", "Credit", "Prior year"],
    [1000, "Cash at bank", 48210, None, 51000],
    [1100, "Trade debtors", 118900, None, 60000],
    [1200, "Prepayments", 4200, None, 4000],
    [2000, "Trade creditors", None, 39310, -41000],
    [2100, "Accruals", None, 12000, -11500],
    [2200, "Directors loan", None, 20000, -20000],
    [3000, "Share capital", None, 100, -100],
    [3100, "Retained earnings", None, 99900, -42400],
    [None, "Total", 171310, 171310, None],
]


def make_job_folder(root: Path, name: str, tb_rows=None, debtors_total=112400):
    folder = root / name
    folder.mkdir(parents=True)
    write_xlsx(folder / "Trial Balance FY25.xlsx", {"TB": tb_rows or TB_ROWS})
    write_xlsx(folder / "Debtors schedule.xlsx", {"Debtors": [
        ["Customer", "Invoice", "Amount"], ["Alpha Ltd", "INV-101", 70400], ["Beta Ltd", "INV-102", 42000], ["Total", None, debtors_total],
    ]})
    with open(folder / "Bank reconciliation.csv", "w", newline="") as fh:
        csv.writer(fh).writerows([
            ["Bank reconciliation at 31 March 2025", ""], ["Balance per bank statement", "49,010.00"],
            ["Less unpresented cheques", "(800.00)"], ["Balance per cash book", "48,210.00"], ["Difference", "0.00"],
        ])
    (folder / "Workpaper - accruals.txt").write_text(
        "Accruals workpaper FY25\nPrepared by JS on 12 April 2025\nAccruals listing agreed to post year end invoices.\n"
        "Conclusion: accruals of 12,000 are fairly stated.\nDirectors loan interest: TBC, awaiting client confirmation.\n", encoding="utf-8")
    (folder / "Tax computation.txt").write_text(
        "Corporation tax computation FY25\nProfit per accounts 57,500\nAdd back depreciation 6,000\n"
        "Less capital allowances (4,500)\nTaxable profit 59,000\nCorporation tax payable at 19% 11,210\n", encoding="utf-8")
    return folder


DIRECTION = [
    {"id": "D1", "text": "Agree the bank reconciliation to the cash at bank balance in the ledger"},
    {"id": "D2", "text": "Confirm the accruals workpaper is complete and signed off"},
    {"id": "D3", "text": "Check the corporation tax computation starts from the profit per accounts"},
]


class FakePM:
    """Stands in for the PM application: serves jobs, records the events it is sent."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.events: list[dict] = []

    def add_job(self, job_id, client_id, folder, direction=None):
        self.jobs[job_id] = {
            "job_id": job_id, "key": f"JOB-{job_id}", "title": "Year end accounts", "client_id": client_id, "client_name": client_id,
            "drive_folder_id": folder, "direction_items": DIRECTION if direction is None else direction, "knowledge_ids": [],
        }

    def get_job(self, job_id):
        return self.jobs[job_id]

    def send_event(self, run_id, event):
        self.events.append({"run_id": run_id, **event})

    def completed(self):
        return [e for e in self.events if e["type"] == "ai_precheck.completed"]


@pytest.fixture
def env(tmp_path, monkeypatch):
    from precheck_agent import budget, config, embeddings, llm, pm_client, runner, skills_loader, store

    drive_root = tmp_path / "drive"
    drive_root.mkdir()
    # SQLite by default. Set PRECHECK_TEST_DATABASE_URL to a Postgres with pgvector to run the
    # same tests against the production storage (the schema is emptied before each test).
    pg_url = os.environ.get("PRECHECK_TEST_DATABASE_URL")
    if pg_url:
        import sqlalchemy as sa

        engine = sa.create_engine(pg_url)
        with engine.begin() as conn:
            conn.execute(sa.text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        engine.dispose()
    monkeypatch.setenv("PRECHECK_DATABASE_URL", pg_url or f"sqlite:///{(tmp_path / 'precheck.db').as_posix()}")
    monkeypatch.setenv("PRECHECK_LLM_MODE", "fake")
    monkeypatch.setenv("PRECHECK_DRIVE_MODE", "local")
    monkeypatch.setenv("PRECHECK_LOCAL_DRIVE_ROOT", str(drive_root))
    monkeypatch.setenv("PRECHECK_SERVICE_TOKEN", "test-token")
    for cached in (config.get_settings, store.get_store, embeddings.get_embedder, runner.graph, runner._checkpointer, skills_loader.all_skills):
        cached.cache_clear()
    store.metadata.clear()
    llm.reset_fakes()
    budget._budgets.clear()
    pm = FakePM()
    pm_client.set_pm(pm)

    class Env:
        pass

    e = Env()
    e.pm, e.drive_root, e.tmp = pm, drive_root, tmp_path
    e.reader = llm.set_fake("reader", llm.demo_reader)
    e.judge = llm.set_fake("judge", llm.demo_judge)
    e.escalate = llm.set_fake("escalate", llm.demo_escalate)

    def run(job_id):
        return runner.execute(runner.new_run_id(), job_id)

    e.run = run
    yield e
    pm_client.set_pm(None)
    for cached in (config.get_settings, store.get_store, embeddings.get_embedder, runner.graph, runner._checkpointer, skills_loader.all_skills):
        cached.cache_clear()


@pytest.fixture
def job(env):
    make_job_folder(env.drive_root, "acme-fy25")
    env.pm.add_job("101", "client-acme", "acme-fy25")
    return "101"
