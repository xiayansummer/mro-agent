"""
Chat history router — list/get/delete/rename user sessions.
Sending messages is still handled by /api/chat (in chat router).
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.routers.auth import require_user_id
from app.services import chat_history_service

router = APIRouter()


class UpdateTitleRequest(BaseModel):
    title: str


@router.get("/chat/sessions")
async def list_sessions(user_id: str = Depends(require_user_id)):
    sessions = await chat_history_service.list_sessions(user_id)
    return {"sessions": sessions}


@router.get("/chat/sessions/{session_id}")
async def get_session(session_id: str, user_id: str = Depends(require_user_id)):
    session = await chat_history_service.get_session(session_id, user_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str, user_id: str = Depends(require_user_id)):
    ok = await chat_history_service.delete_session(session_id, user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}


@router.patch("/chat/sessions/{session_id}")
async def update_session_title(
    session_id: str,
    req: UpdateTitleRequest,
    user_id: str = Depends(require_user_id),
):
    ok = await chat_history_service.update_title(session_id, user_id, req.title)
    if not ok:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"ok": True}
