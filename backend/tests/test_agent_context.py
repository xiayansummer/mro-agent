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
