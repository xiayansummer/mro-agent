import json

import pytest

from app.routers import chat
from app.services import agent


async def _collect(gen):
    return "".join([c async for c in gen])


def _fake_ctx():
    async def ctx(session_id, user_id):
        return {"conversation": [], "last_intent": None}
    return ctx


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
    real_ensure_future = chat.asyncio.ensure_future

    def fake_ensure_future(coro):
        # 返回真实 Task(而非裸 coroutine),才支持 L-1 加的 add_done_callback 强引用跟踪
        task = real_ensure_future(coro)
        scheduled.append(task)
        return task

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


@pytest.mark.asyncio
async def test_handle_message_emits_refined_offers_when_results_exist(monkeypatch):
    monkeypatch.setattr(agent.comparison_refine_service, "parse_refinement",
                        lambda m: {"sort": "asc", "limit": 1, "platform": None, "brandKeep": None,
                                   "brandDrop": None, "priceMin": None, "priceMax": None, "label": "按价格最低取前1"})
    async def fake_offers(sid, uid):
        return [{"id": "b", "priceValue": 1, "title": "便宜货"}, {"id": "a", "priceValue": 9, "title": "贵货"}]
    monkeypatch.setattr(agent.comparison_task_service, "get_latest_session_offers", fake_offers)
    monkeypatch.setattr(agent, "get_session_context", _fake_ctx())

    out = await _collect(agent.handle_message("s1", "最便宜的1个", "u1"))
    assert "event: refined_offers" in out
    assert "便宜货" in out and "event: done" in out


@pytest.mark.asyncio
async def test_handle_message_guides_when_no_results(monkeypatch):
    monkeypatch.setattr(agent.comparison_refine_service, "parse_refinement",
                        lambda m: {"sort": "asc", "limit": 5, "label": "x", "platform": None,
                                   "brandKeep": None, "brandDrop": None, "priceMin": None, "priceMax": None})
    async def no_offers(sid, uid): return None
    monkeypatch.setattr(agent.comparison_task_service, "get_latest_session_offers", no_offers)
    monkeypatch.setattr(agent, "get_session_context", _fake_ctx())

    out = await _collect(agent.handle_message("s1", "最便宜的5个", "u1"))
    assert "event: refined_offers" not in out
    assert "比价结果" in out  # 引导文案


@pytest.mark.asyncio
async def test_handle_message_falls_through_when_not_refinement(monkeypatch):
    monkeypatch.setattr(agent.comparison_refine_service, "parse_refinement", lambda m: None)
    called = {"draft": False}
    async def fake_create(**kw):
        called["draft"] = True
        return {"parsedIntent": {}, "shouldCreateDraft": False, "guidance": "请补充产品名称"}
    monkeypatch.setattr(agent.comparison_draft_service, "create_draft_from_message", fake_create)
    monkeypatch.setattr(agent, "get_session_context", _fake_ctx())

    out = await _collect(agent.handle_message("s1", "防尘口罩", "u1"))
    assert called["draft"] is True  # 非精炼 → 走原路径
