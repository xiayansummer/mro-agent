import pytest

from app.services import agent


@pytest.fixture(autouse=True)
def clear_agent_sessions():
    agent._sessions.clear()
    yield
    agent._sessions.clear()


@pytest.mark.asyncio
async def test_get_session_context_loads_from_chat_history(monkeypatch):
    loaded = [
        {"role": "user", "content": "我要买M8螺栓"},
        {"role": "assistant", "content": "[已搜索: 螺栓 规格:M8, 找到8个产品]"},
    ]

    async def fake_get_recent_agent_context(session_id, user_id, limit):
        assert session_id == "s1"
        assert user_id == "u1"
        assert limit == 6
        return loaded

    monkeypatch.setattr(
        agent.chat_history_service,
        "get_recent_agent_context",
        fake_get_recent_agent_context,
    )

    ctx = await agent.get_session_context("s1", "u1")

    assert ctx["conversation"] == loaded


@pytest.mark.asyncio
async def test_get_session_context_uses_cache_after_initial_load(monkeypatch):
    calls = 0

    async def fake_get_recent_agent_context(session_id, user_id, limit):
        nonlocal calls
        calls += 1
        return [{"role": "user", "content": "第一次"}]

    monkeypatch.setattr(
        agent.chat_history_service,
        "get_recent_agent_context",
        fake_get_recent_agent_context,
    )

    first = await agent.get_session_context("s1", "u1")
    first["conversation"].append({"role": "assistant", "content": "缓存回复"})
    second = await agent.get_session_context("s1", "u1")

    assert calls == 1
    assert second["conversation"][-1]["content"] == "缓存回复"


@pytest.mark.asyncio
async def test_handle_message_emits_comparison_draft_without_sku_results(monkeypatch):
    async def fake_user_context(user_id, limit):
        return ""

    async def fake_create_draft_from_message(**kwargs):
        return {
            "shouldCreateDraft": True,
            "parsedIntent": {"query_type": "precise", "keywords": ["螺栓"]},
            "draft": {
                "id": "cmp_draft_1",
                "sessionId": kwargs["session_id"],
                "rawQuery": kwargs["message"],
                "structure": {
                    "category": {"l3": "六角头螺栓", "confidence": 0.9},
                    "specification": {"productType": "外六角螺栓"},
                    "purchaseConstraints": {"preferredPlatforms": ["jd", "zkh"]},
                    "searchTerms": {"jd": ["外六角螺栓 M8"], "zkh": ["外六角螺栓 M8"]},
                },
                "selectedPlatforms": ["jd", "zkh"],
                "searchTerms": {"jd": ["外六角螺栓 M8"], "zkh": ["外六角螺栓 M8"]},
                "status": "needs_confirmation",
                "createdAt": 0,
                "updatedAt": 0,
            },
        }

    async def fake_save_summary(**kwargs):
        return None

    monkeypatch.setattr(agent.memory_service, "get_user_context", fake_user_context)
    monkeypatch.setattr(agent.memory_service, "save_session_summary", fake_save_summary)
    monkeypatch.setattr(
        agent.comparison_draft_service,
        "create_draft_from_message",
        fake_create_draft_from_message,
    )

    chunks = [
        chunk
        async for chunk in agent.handle_message("s1", "M8 外六角螺栓", "u1")
    ]

    stream = "".join(chunks)
    assert "event: comparison_draft" in stream
    assert "cmp_draft_1" in stream
    assert "event: sku_results" not in stream
    assert "event: competitor_results" not in stream


@pytest.mark.asyncio
async def test_handle_message_guides_when_no_draft(monkeypatch):
    async def fake_user_context(user_id, limit):
        return ""

    async def fake_create_draft_from_message(**kwargs):
        return {
            "shouldCreateDraft": False,
            "guidance": "请提供要采购的产品名称或型号规格。",
            "parsedIntent": {"query_type": "vague"},
        }

    monkeypatch.setattr(agent.memory_service, "get_user_context", fake_user_context)
    monkeypatch.setattr(
        agent.comparison_draft_service,
        "create_draft_from_message",
        fake_create_draft_from_message,
    )

    chunks = [chunk async for chunk in agent.handle_message("s1", "你好", "u1")]
    stream = "".join(chunks)

    assert "请提供要采购的产品名称" in stream
    assert "event: comparison_draft" not in stream
