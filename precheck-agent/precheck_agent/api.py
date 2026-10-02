"""HTTP API of the precheck-agent service. Called only by the PM application, which has already
checked that the user may open the job; every request must carry the shared service token."""
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import __version__, runner
from .config import get_settings
from .llm import model_id
from .store import get_store

app = FastAPI(title="AFIT Connect pre-check agent", version=__version__)


def require_token(x_precheck_token: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_precheck_token, get_settings().service_token):
        raise HTTPException(status_code=401, detail="Invalid service token.")


class RunRequest(BaseModel):
    job_id: str
    run_id: str | None = None


@app.get("/healthz")
def healthz():
    s = get_settings()
    return {"status": "ok", "version": __version__, "llm_mode": s.llm_mode, "drive_mode": s.drive_mode,
            "models": {r: model_id(r, s) for r in ("reader", "judge", "escalate")}}


@app.post("/precheck/runs", status_code=202, dependencies=[Depends(require_token)])
def create_run(body: RunRequest):
    """Start a pre-check for one job. Returns the run id at once; progress and the result come
    back to the PM application as events. The run id is the LangGraph thread id."""
    return {"run_id": runner.start(body.job_id, body.run_id), "status": "running"}


@app.get("/precheck/runs/{run_id}", dependencies=[Depends(require_token)])
def get_run(run_id: str):
    run = get_store().get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="No such run.")
    return {"run_id": run_id, "job_id": run["job_id"], "status": run["status"], "result": run["result"]}
