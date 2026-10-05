"""Runs one pre-check: streams the graph and forwards its progress to the PM application."""
import logging
import sqlite3
import threading
import time
import uuid
from functools import lru_cache

from . import budget
from .config import get_settings
from .graph import PrecheckStop, build_graph
from .pm_client import PMError, get_pm
from .store import get_store

logger = logging.getLogger(__name__)


@lru_cache
def _checkpointer():
    """Postgres checkpointer in production, SQLite otherwise. The run id is the thread id."""
    s = get_settings()
    if s.database_url.startswith("postgresql"):
        from langgraph.checkpoint.postgres import PostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        # A pool, not one long-lived connection: steps checkpoint as they finish, and a dropped
        # connection is replaced instead of failing every later run.
        dsn = s.database_url.replace("postgresql+psycopg://", "postgresql://")
        pool = ConnectionPool(dsn, min_size=1, max_size=6, open=True,
                              kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row})
        saver = PostgresSaver(pool)
        saver.setup()
        return saver
    from langgraph.checkpoint.sqlite import SqliteSaver

    path = s.database_url.replace("sqlite:///", "")
    conn = sqlite3.connect((path + ".checkpoints") if path != ":memory:" else ":memory:", check_same_thread=False)
    saver = SqliteSaver(conn)
    saver.setup()
    return saver


@lru_cache
def graph():
    return build_graph(_checkpointer())


def new_run_id() -> str:
    return uuid.uuid4().hex


def execute(run_id: str, job_id: str, mode: str = "precheck") -> dict:
    """Run to the end (blocking). Returns the final result, or {"status": "failed", "reason"}.
    mode "draft" stops after drafting the Direction Note (no pre-check)."""
    pm, store = get_pm(), get_store()
    store.save_run(run_id, job_id, "running")
    final = None
    try:
        # One custom event per node goes to the job card as it happens; "updates" tells us when
        # each node has finished.
        for chunk in graph().stream(
            {"run_id": run_id, "job_id": job_id, "mode": mode, "started_at": time.time()},
            config={"configurable": {"thread_id": run_id}},
            stream_mode=["updates", "custom"],
            version="v2",
        ):
            if chunk["type"] == "custom":
                pm.send_event(run_id, {"type": "ai_precheck.progress", "job_id": job_id, **chunk["data"]})
            elif chunk["type"] == "updates":
                for node, update in chunk["data"].items():
                    if node == "publish" and update:
                        final = update["final"]
                    elif node == "draft_directions" and update and mode == "draft":
                        final = {"run_id": run_id, "job_id": job_id, "status": "complete", "mode": "draft", **update["drafted"],
                                 "usage": update["usage"], "skipped": update["skipped"]}
                        get_store().save_run(run_id, job_id, "complete", final)
    except (PrecheckStop, PMError) as exc:
        return _fail(run_id, job_id, str(exc))
    except Exception:  # anything unexpected: say so plainly, keep the detail in the log
        logger.exception("Pre-check run %s failed", run_id)
        return _fail(run_id, job_id, "The pre-check stopped because of an unexpected error. Nothing was changed. Please try again.")
    finally:
        budget.release(run_id)
    return final or _fail(run_id, job_id, "The pre-check ended without a result. Please try again.")


def _fail(run_id: str, job_id: str, reason: str) -> dict:
    result = {"run_id": run_id, "job_id": job_id, "status": "failed", "reason": reason}
    get_store().save_run(run_id, job_id, "failed", result)
    get_pm().send_event(run_id, {"type": "ai_precheck.failed", "job_id": job_id, "reason": reason})
    return result


def start(job_id: str, run_id: str | None = None, mode: str = "precheck") -> str:
    """Start a run in the background and return its id at once."""
    run_id = run_id or new_run_id()
    threading.Thread(target=execute, args=(run_id, job_id, mode), name=f"precheck-{run_id[:8]}", daemon=True).start()
    return run_id
