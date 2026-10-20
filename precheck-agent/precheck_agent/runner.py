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

# Runs a person stopped. Checked between steps: the step under way finishes (a model call cannot
# be taken back), then nothing more runs and nothing is sent but the failure.
_cancelled: set[str] = set()
_lock = threading.Lock()


class RunStopped(Exception):
    pass


def cancel(run_id: str) -> None:
    with _lock:
        _cancelled.add(run_id)


def _check(run_id: str, started: float, deadline_s: int) -> None:
    with _lock:
        stopped = run_id in _cancelled
    if stopped:
        raise RunStopped("Stopped by a person. Nothing was changed.")
    if time.time() - started > deadline_s:
        raise RunStopped(f"The run took longer than {deadline_s // 60} minutes, so it was stopped. Nothing was changed. Please try again.")


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
    started, deadline_s = time.time(), get_settings().run_deadline_s
    try:
        _check(run_id, started, deadline_s)
        # One custom event per node goes to the job card as it happens; "updates" tells us when
        # each node has finished.
        for chunk in graph().stream(
            {"run_id": run_id, "job_id": job_id, "mode": mode, "started_at": time.time()},
            config={"configurable": {"thread_id": run_id}},
            stream_mode=["updates", "custom"],
            version="v2",
        ):
            _check(run_id, started, deadline_s)
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
    except (PrecheckStop, PMError, RunStopped) as exc:
        return _fail(run_id, job_id, str(exc))
    except Exception:  # anything unexpected: say so plainly, keep the detail in the log
        logger.exception("Pre-check run %s failed", run_id)
        return _fail(run_id, job_id, "The pre-check stopped because of an unexpected error. Nothing was changed. Please try again.")
    finally:
        budget.release(run_id)
        with _lock:
            _cancelled.discard(run_id)
    return final or _fail(run_id, job_id, "The pre-check ended without a result. Please try again.")


def _fail(run_id: str, job_id: str, reason: str) -> dict:
    result = {"run_id": run_id, "job_id": job_id, "status": "failed", "reason": reason}
    get_store().save_run(run_id, job_id, "failed", result)
    get_pm().send_event(run_id, {"type": "ai_precheck.failed", "job_id": job_id, "reason": reason})
    return result


def fail_orphans() -> int:
    """At start-up: runs left "running" by the previous process (stopped by a restart or a
    crash) can never finish. Report them as failed so the task card does not wait for ever."""
    orphans = get_store().running_run_ids()
    for run_id, job_id in orphans:
        logger.warning("Run %s was interrupted by a restart", run_id)
        _fail(run_id, job_id, "The AI service restarted while this was running, so it stopped. Nothing was changed. Please run it again.")
    return len(orphans)


def start(job_id: str, run_id: str | None = None, mode: str = "precheck") -> str:
    """Start a run in the background and return its id at once."""
    run_id = run_id or new_run_id()
    threading.Thread(target=execute, args=(run_id, job_id, mode), name=f"precheck-{run_id[:8]}", daemon=True).start()
    return run_id


def ask_now(job_id: str, question_id: str, question: str, history: list[dict]) -> dict:
    """Answer a question about a task and send the answer to the PM application (blocking)."""
    from . import ask

    pm = get_pm()
    try:
        result = ask.answer(pm.get_job(job_id), question, history)
        pm.send_event(question_id, {"type": "ai_assistant.answered", "job_id": job_id, "result": result})
        return result
    except PMError as exc:
        reason = str(exc)
    except Exception:  # say so plainly; keep the detail in the log
        logger.exception("Answering question %s failed", question_id)
        reason = "The AI could not answer just now. Please ask again."
    pm.send_event(question_id, {"type": "ai_assistant.failed", "job_id": job_id, "reason": reason})
    return {"status": "failed", "reason": reason}


def learn_now(body: dict) -> dict:
    """Draft a lesson as a rule and send it to the PM application (blocking)."""
    from . import learn

    pm, run_id = get_pm(), f"lesson-{body['lesson_id']}"
    try:
        rule, _ = learn.draft(body)
        pm.send_event(run_id, {"type": "ai_learning.drafted", "job_id": body.get("job_id", ""), "result": rule})
        return rule
    except Exception:  # the person's note still applies; the rule can be drafted again later
        logger.exception("Drafting lesson %s failed", body.get("lesson_id"))
        pm.send_event(run_id, {"type": "ai_learning.failed", "job_id": body.get("job_id", ""), "reason": "The rule could not be drafted."})
        return {}


def start_learn(body: dict) -> None:
    threading.Thread(target=learn_now, args=(body,), name=f"learn-{body['lesson_id']}", daemon=True).start()


def start_ask(job_id: str, question_id: str, question: str, history: list[dict]) -> None:
    threading.Thread(target=ask_now, args=(job_id, question_id, question, history), name=f"ask-{question_id[:8]}", daemon=True).start()

