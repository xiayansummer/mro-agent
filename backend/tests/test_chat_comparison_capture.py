import json

import pytest

from app.routers import chat


@pytest.mark.asyncio
async def test_capturing_stream_persists_comparison_draft(monkeypatch):
    draft = {"id": "cmp_draft_1", "status": "needs_confirmation"}
    saved = {}

    async def fake_handle_message(*args, **kwargs):
        yield "event: comparison_draft\ndata: " + json.dumps(draft) + "\n\n"
        yield 'event: text\ndata: "请确认比价结构"\n\n'
        yield "event: done\ndata: \n\n"

    async def fake_save_turn(**kwargs):
        saved.update(kwargs)

    scheduled = []
    def fake_ensure_future(coro):
        scheduled.append(coro)
        return coro

    monkeypatch.setattr(chat, "handle_message", fake_handle_message)
    monkeypatch.setattr(chat.chat_history_service, "save_turn", fake_save_turn)
    monkeypatch.setattr(chat.asyncio, "ensure_future", fake_ensure_future)

    chunks = [
        chunk
        async for chunk in chat._capturing_stream("u1", "s1", "M8螺栓", "")
    ]
    assert len(scheduled) == 1
    await scheduled[0]

    assert "event: comparison_draft" in "".join(chunks)
    assert saved["comparison_draft"] == draft
    assert saved["assistant_text"] == "请确认比价结构"
