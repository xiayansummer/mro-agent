"""
Chat endpoint: streams the assistant response via SSE and persists each turn to DB.

The wrapper around handle_message accumulates assistant text + structured results
from the SSE events as they pass through, then fires save_turn after the stream ends.
"""
import asyncio
import json
import logging
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.routers.auth import require_user_id
from app.services import chat_history_service
from app.services.agent import handle_message

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    session_id: str
    message: str
    image_base64: Optional[str] = None  # Base64-encoded image for vision queries


def _parse_sse_text(data_line: str) -> str:
    """`event: text\\ndata: "..."` — try JSON parse, fall back to raw."""
    try:
        return json.loads(data_line)
    except Exception:
        return data_line


async def _capturing_stream(
    user_id: str,
    session_id: str,
    user_message: str,
    image_b64: str,
) -> AsyncIterator[str]:
    """
    Wrap the agent generator: forward each event to the client unchanged,
    while accumulating assistant text + structured results for persistence.
    """
    text_parts: list[str] = []
    sku_results: Optional[list] = None
    competitor_results: Optional[list] = None

    pending_event: str = ""
    try:
        async for chunk in handle_message(session_id, user_message, user_id, image_b64):
            yield chunk

            # SSE events are formatted as "event: X\ndata: Y\n\n" — parse to extract structured content.
            # Each yielded chunk may contain one full event or partial; agent.py emits whole events
            # per yield in practice, so we parse line-by-line from the chunk.
            for line in chunk.split("\n"):
                if line.startswith("event: "):
                    pending_event = line[7:].strip()
                elif line.startswith("data: "):
                    data = line[6:]
                    if pending_event == "text":
                        text_parts.append(_parse_sse_text(data))
                    elif pending_event == "sku_results":
                        try:
                            sku_results = json.loads(data)
                        except Exception:
                            pass
                    elif pending_event == "competitor_results":
                        try:
                            competitor_results = json.loads(data)
                        except Exception:
                            pass
                    pending_event = ""
    finally:
        # Persist after the stream ends (also runs on client disconnect)
        assistant_text = "".join(text_parts)
        # Don't await — fire and forget, don't block the response close
        asyncio.ensure_future(
            chat_history_service.save_turn(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                image_b64=image_b64,
                assistant_text=assistant_text,
                sku_results=sku_results,
                competitor_results=competitor_results,
            )
        )


@router.post("/chat")
async def chat(
    req: ChatRequest,
    user_id: str = Depends(require_user_id),
):
    return StreamingResponse(
        _capturing_stream(user_id, req.session_id, req.message, req.image_base64 or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
