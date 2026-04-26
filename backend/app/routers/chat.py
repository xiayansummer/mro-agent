from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.routers.auth import get_current_user_id
from app.services.agent import handle_message

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: Optional[str] = None
    image_base64: Optional[str] = None  # Base64-encoded image for vision queries


@router.post("/chat")
async def chat(
    req: ChatRequest,
    auth_user_id: Optional[str] = Depends(get_current_user_id),
):
    # Authenticated user takes priority over body user_id; anonymous falls back to session_id
    user_id = auth_user_id or req.user_id or req.session_id
    return StreamingResponse(
        handle_message(req.session_id, req.message, user_id, req.image_base64 or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
