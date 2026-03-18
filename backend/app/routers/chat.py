from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.agent import handle_message

router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    user_id: Optional[str] = None
    image_base64: Optional[str] = None  # Base64-encoded image for vision queries


@router.post("/chat")
async def chat(req: ChatRequest):
    user_id = req.user_id or req.session_id
    return StreamingResponse(
        handle_message(req.session_id, req.message, user_id, req.image_base64 or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
