from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.models.comparison import ComparisonStructure, ExtensionStatus, Platform
from app.routers.auth import require_user_id
from app.services import comparison_draft_service, comparison_task_service, extension_service

router = APIRouter()


class CreateComparisonDraftRequest(BaseModel):
    sessionId: str = Field(min_length=1)
    message: str = Field(min_length=1)


class UpdateComparisonDraftRequest(BaseModel):
    structure: ComparisonStructure
    selectedPlatforms: list[Platform] | None = None


class RetryComparisonSubtaskRequest(BaseModel):
    platform: Platform


@router.get("/comparison/health")
async def comparison_health():
    return {"status": "ok"}


@router.post("/comparison/drafts")
async def create_draft(
    req: CreateComparisonDraftRequest,
    user_id: str = Depends(require_user_id),
):
    return await comparison_draft_service.create_draft_from_message(
        user_id=user_id,
        session_id=req.sessionId,
        message=req.message,
    )


@router.get("/comparison/drafts/{draft_id}")
async def get_draft(
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    draft = await comparison_draft_service.get_draft(draft_id, user_id)
    if not draft:
        raise HTTPException(status_code=404, detail="比价草稿不存在")
    return draft


@router.patch("/comparison/drafts/{draft_id}")
async def update_draft(
    draft_id: str,
    req: UpdateComparisonDraftRequest,
    user_id: str = Depends(require_user_id),
):
    draft = await comparison_draft_service.update_draft_structure(
        draft_id=draft_id,
        user_id=user_id,
        structure=req.structure,
        selected_platforms=req.selectedPlatforms,
    )
    if not draft:
        raise HTTPException(status_code=404, detail="比价草稿不存在")
    return draft


@router.post("/comparison/drafts/{draft_id}/confirm")
async def confirm_draft(
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    task = await comparison_task_service.start_draft(draft_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="比价草稿不存在")
    return task


@router.post("/comparison/drafts/{draft_id}/start")
async def start_draft(
    draft_id: str,
    user_id: str = Depends(require_user_id),
):
    return await confirm_draft(draft_id, user_id)


@router.get("/comparison/tasks/{task_id}")
async def get_task(
    task_id: str,
    user_id: str = Depends(require_user_id),
):
    task = await comparison_task_service.get_task(task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="比价任务不存在")
    return task


@router.post("/comparison/tasks/{task_id}/retry")
async def retry_task_platform(
    task_id: str,
    req: RetryComparisonSubtaskRequest,
    user_id: str = Depends(require_user_id),
):
    task = await comparison_task_service.retry_subtask(task_id, req.platform, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="比价任务不存在或平台不可重试")
    return task


@router.get("/comparison/extension/status", response_model=ExtensionStatus)
async def get_extension_status(
    user_id: str = Depends(require_user_id),
):
    return await extension_service.get_extension_status(user_id)
