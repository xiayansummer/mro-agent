"""
Chrome extension polling API skeleton.

Extension authentication is intentionally separate from web user auth. The next
slice will bind short-lived pairing codes to persistent extension sessions.
"""
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.models.comparison import ExternalOffer, Platform

router = APIRouter()


class PairExtensionRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)
    deviceName: Optional[str] = None
    version: Optional[str] = None


class UpdateSubtaskStatusRequest(BaseModel):
    status: str = Field(min_length=1)
    message: Optional[str] = None


class SubmitSubtaskResultsRequest(BaseModel):
    platform: Platform
    searchTerm: str = Field(min_length=1)
    offers: list[ExternalOffer] = Field(default_factory=list)


def require_extension_token(x_extension_token: Optional[str] = Header(None)) -> str:
    if not x_extension_token:
        raise HTTPException(status_code=401, detail="扩展未绑定")
    return x_extension_token


@router.get("/extension/health")
async def extension_health():
    return {"status": "ok", "browser": "chrome"}


@router.post("/extension/pair")
async def pair_extension(req: PairExtensionRequest):  # noqa: ARG001
    raise HTTPException(status_code=501, detail="extension pairing service not implemented")


@router.get("/extension/tasks/next")
async def get_next_task(
    extension_token: str = Header(None, alias="X-Extension-Token"),  # noqa: ARG001
):
    require_extension_token(extension_token)
    raise HTTPException(status_code=501, detail="extension task lease service not implemented")


@router.post("/extension/subtasks/{subtask_id}/status")
async def update_subtask_status(
    subtask_id: str,  # noqa: ARG001
    req: UpdateSubtaskStatusRequest,  # noqa: ARG001
    extension_token: str = Header(None, alias="X-Extension-Token"),  # noqa: ARG001
):
    require_extension_token(extension_token)
    raise HTTPException(status_code=501, detail="extension subtask service not implemented")


@router.post("/extension/subtasks/{subtask_id}/results")
async def submit_subtask_results(
    subtask_id: str,  # noqa: ARG001
    req: SubmitSubtaskResultsRequest,  # noqa: ARG001
    extension_token: str = Header(None, alias="X-Extension-Token"),  # noqa: ARG001
):
    require_extension_token(extension_token)
    raise HTTPException(status_code=501, detail="extension result service not implemented")
