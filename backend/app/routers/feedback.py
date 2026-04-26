"""
用户反馈路由
POST /api/feedback  — 保存产品 👍/👎 反馈到 Memos
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.routers.auth import get_current_user_id
from app.services.memory_service import memory_service

router = APIRouter()


class FeedbackRequest(BaseModel):
    session_id: str
    user_id: Optional[str] = None
    action: str              # "liked" | "disliked"
    item_code: str
    item_name: str
    brand_name: Optional[str] = ""
    l2_category: Optional[str] = ""
    l3_category: Optional[str] = ""
    specification: Optional[str] = ""


@router.post("/feedback")
async def submit_feedback(
    req: FeedbackRequest,
    auth_user_id: Optional[str] = Depends(get_current_user_id),
):
    user_id = auth_user_id or req.user_id or req.session_id
    if req.action not in ("liked", "disliked"):
        return {"ok": False, "error": "action must be liked or disliked"}

    await memory_service.save_feedback(
        user_id=user_id,
        action=req.action,
        item_code=req.item_code,
        item_name=req.item_name,
        brand_name=req.brand_name or "",
        l2_category=req.l2_category or "",
        l3_category=req.l3_category or "",
        specification=req.specification or "",
    )
    return {"ok": True}
