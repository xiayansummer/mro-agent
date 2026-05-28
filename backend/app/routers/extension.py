"""
Chrome extension polling API skeleton.

Extension authentication is intentionally separate from web user auth. The next
slice will bind short-lived pairing codes to persistent extension sessions.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.models.comparison import ExternalOffer, ExtensionStatus, Platform, PlatformStatus
from app.routers.auth import require_user_id
from app.services import comparison_task_service, extension_service

router = APIRouter()


class RegisterExtensionRequest(BaseModel):
    code: str = Field(min_length=6, max_length=16)
    deviceName: Optional[str] = None
    version: Optional[str] = None


class UpdateExtensionStatusRequest(BaseModel):
    deviceName: Optional[str] = None
    version: Optional[str] = None
    platforms: list[PlatformStatus] = Field(default_factory=list)


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


@router.post("/extension/pairing-code")
async def create_pairing_code(user_id: str = Depends(require_user_id)):
    return await extension_service.create_pairing_code(user_id)


@router.post("/extension/register")
async def register_extension(req: RegisterExtensionRequest):
    result = await extension_service.register_extension(
        code=req.code,
        device_name=req.deviceName,
        version=req.version,
    )
    if not result:
        raise HTTPException(status_code=400, detail="配对码无效或已过期")
    return result


@router.post("/extension/pair")
async def pair_extension(req: RegisterExtensionRequest):
    return await register_extension(req)


@router.get("/extension/status", response_model=ExtensionStatus)
async def get_web_extension_status(user_id: str = Depends(require_user_id)):
    return await extension_service.get_extension_status(user_id)


@router.post("/extension/status")
async def update_extension_status(
    req: UpdateExtensionStatusRequest,
    extension_token: str = Header(None, alias="X-Extension-Token"),
):
    if not await extension_service.update_extension_status(
        ext_token=extension_token or "",
        device_name=req.deviceName,
        version=req.version,
        platforms=req.platforms,
    ):
        raise HTTPException(status_code=401, detail="扩展未绑定或已失效")
    return {"ok": True}


@router.get("/extension/tasks/next")
async def get_next_task(
    extension_token: str = Header(None, alias="X-Extension-Token"),
):
    require_extension_token(extension_token)
    task = await comparison_task_service.lease_next_subtask(extension_token)
    if not task:
        return Response(status_code=204)
    return task


@router.post("/extension/subtasks/{subtask_id}/status")
async def update_subtask_status(
    subtask_id: str,
    req: UpdateSubtaskStatusRequest,
    extension_token: str = Header(None, alias="X-Extension-Token"),
):
    require_extension_token(extension_token)
    if not await comparison_task_service.update_subtask_status(
        ext_token=extension_token,
        subtask_id=subtask_id,
        status=req.status,
        message=req.message,
    ):
        raise HTTPException(status_code=404, detail="任务不存在或状态无效")
    return {"ok": True}


@router.post("/extension/subtasks/{subtask_id}/results")
async def submit_subtask_results(
    subtask_id: str,
    req: SubmitSubtaskResultsRequest,
    extension_token: str = Header(None, alias="X-Extension-Token"),
):
    require_extension_token(extension_token)
    if not await comparison_task_service.submit_subtask_results(
        ext_token=extension_token,
        subtask_id=subtask_id,
        platform=req.platform,
        search_term=req.searchTerm,
        offers=[offer.model_dump(mode="json") for offer in req.offers],
    ):
        raise HTTPException(status_code=404, detail="任务不存在或平台不匹配")
    return {"ok": True}
