"""The only two calls this service makes to the PM application: read one job, and send an
event. Both carry the shared service token. Nothing here can change a job: there is no call
that sets a job's status or marks it reviewed."""
import logging

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)


class PMError(Exception):
    pass


class PMClient:
    def __init__(self):
        s = get_settings()
        self.base = s.pm_base_url.rstrip("/")
        self.headers = {"X-Precheck-Token": s.service_token}

    def get_job(self, job_id: str) -> dict:
        try:
            resp = httpx.get(f"{self.base}/api/precheck/internal/jobs/{job_id}/", headers=self.headers, timeout=20)
        except httpx.HTTPError as exc:
            raise PMError("The pre-check service could not reach AFIT Connect.") from exc
        if resp.status_code != 200:
            raise PMError(f"AFIT Connect would not give the pre-check this job ({resp.status_code}).")
        return resp.json()

    def send_event(self, run_id: str, event: dict) -> None:
        """Progress and completion events. Best-effort for progress; the final event is retried."""
        final = event.get("type") in ("ai_precheck.completed", "ai_precheck.failed")
        for attempt in range(3 if final else 1):
            try:
                resp = httpx.post(
                    f"{self.base}/api/precheck/internal/events/", json={"run_id": run_id, **event}, headers=self.headers, timeout=20
                )
                if resp.status_code < 300:
                    return
                logger.warning("PM rejected event %s: %s %s", event.get("type"), resp.status_code, resp.text[:200])
            except httpx.HTTPError:
                logger.warning("Could not send event %s (attempt %s)", event.get("type"), attempt + 1)


_client = None


def get_pm():
    global _client
    if _client is None:
        _client = PMClient()
    return _client


def set_pm(client) -> None:
    """Tests replace the PM application with an in-memory stand-in."""
    global _client
    _client = client
