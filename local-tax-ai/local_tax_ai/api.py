"""Local_Tax_AI's HTTP API (AFIT, 22 Nov 2026): called only by the PM application (TASKO's backend), on localhost,
with the shared service token. Each POST /v1/<agent> runs that agent's graph and returns its checked answer."""
import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from . import __version__, graphs
from . import drive
from .config import get_settings
from .documents import Unreadable
from .llm import Unusable

app = FastAPI(title="Local_Tax_AI", version=__version__)
ROUTES = {"chat": "chat", "map-tb": "map_tb", "analyse": "analyse", "reverse": "reverse", "return": "return_prep", "extract": "extract", "policies": "policies", "rule-check": "rule_check", "prefill": "prefill",
          "tb-story": "tb_story", "ppe-classify": "ppe_classify", "fs-edit-accounts": "fs_edit_accounts"}


def require_token(x_local_tax_token: str = Header(default="")) -> None:
    if not hmac.compare_digest(x_local_tax_token, get_settings().service_token):
        raise HTTPException(status_code=401, detail="Invalid service token.")


class Body(BaseModel):
    context: dict = {}
    question: str = ""
    history: list[dict] = []
    request: str = ""
    name: str = ""
    kind: str = ""
    content_b64: str = ""
    policies: list[dict] = []
    rule: dict = {}
    fields: list[dict] = []


class DriveBody(BaseModel):
    folder_id: str = ""
    file_id: str = ""


@app.get("/healthz")
def healthz():
    s = get_settings()
    return {"status": "ok", "service": "Local_Tax_AI", "version": __version__, "llm_mode": s.llm_mode, "model": s.model,
            "agents": list(ROUTES)}


@app.post("/v1/drive/account", dependencies=[Depends(require_token)])
def drive_account():
    return drive.account()


@app.post("/v1/drive/list", dependencies=[Depends(require_token)])
def drive_list(body: DriveBody):
    try:
        return drive.listing(body.folder_id)
    except drive.DriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/drive/download", dependencies=[Depends(require_token)])
def drive_download(body: DriveBody):
    try:
        return drive.fetch(body.file_id)
    except drive.DriveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/v1/{agent}", dependencies=[Depends(require_token)])
def run(agent: str, body: Body):
    if agent not in ROUTES:
        raise HTTPException(status_code=404, detail="No such agent.")
    try:
        return graphs.run(ROUTES[agent], body.model_dump())
    except Unreadable as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Unusable as exc:
        raise HTTPException(status_code=502, detail=f"The AI's answer could not be used: {exc} Try again.") from exc
