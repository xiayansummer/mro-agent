import pytest
from fastapi import HTTPException


# ── M-5: Excel 解析坏文件 → 400(而非未捕获 500)──────────────────────────
def test_parse_excel_bytes_corrupt_raises_400():
    from app.routers.inquiry import parse_excel_bytes
    with pytest.raises(HTTPException) as exc:
        parse_excel_bytes(b"this is not a real xlsx", "bad.xlsx")
    assert exc.value.status_code == 400


def test_parse_excel_bytes_unsupported_ext_raises_400():
    from app.routers.inquiry import parse_excel_bytes
    with pytest.raises(HTTPException) as exc:
        parse_excel_bytes(b"x", "file.pdf")
    assert exc.value.status_code == 400


# ── M-1: get_session_context LRU 淘汰 + conversation 裁剪 ────────────────
@pytest.mark.asyncio
async def test_get_session_context_lru_evicts_oldest(monkeypatch):
    from app.services import agent
    monkeypatch.setattr(agent, "_sessions", agent.OrderedDict())
    monkeypatch.setattr(agent, "_MAX_SESSIONS", 3)

    async def fake_load(sid, uid):
        return []
    monkeypatch.setattr(agent, "_load_session_conversation", fake_load)

    for i in range(5):
        await agent.get_session_context(f"s{i}", "u")

    assert len(agent._sessions) == 3
    assert "s0" not in agent._sessions  # 最旧被淘汰
    assert "s4" in agent._sessions


@pytest.mark.asyncio
async def test_get_session_context_trims_conversation(monkeypatch):
    from app.services import agent
    monkeypatch.setattr(agent, "_sessions", agent.OrderedDict())
    monkeypatch.setattr(agent, "_MAX_CONVERSATION", 4)

    async def fake_load(sid, uid):
        return []
    monkeypatch.setattr(agent, "_load_session_conversation", fake_load)

    ctx = await agent.get_session_context("s", "u")
    ctx["conversation"].extend([{"role": "user", "content": str(i)} for i in range(10)])
    ctx2 = await agent.get_session_context("s", "u")  # 第二次访问触发裁剪
    assert len(ctx2["conversation"]) == 4


# ── M-2: parse_intent 在 LLM 失败时兜底返回 vague(不抛 500)──────────────
@pytest.mark.asyncio
async def test_parse_intent_falls_back_on_llm_error(monkeypatch):
    from app.services import intent_parser

    class _Completions:
        @staticmethod
        def create(**kw):
            raise RuntimeError("LLM unavailable")

    class _Chat:
        completions = _Completions()

    class _BadClient:
        chat = _Chat()

    monkeypatch.setattr(intent_parser, "client", _BadClient())
    result = await intent_parser.parse_intent("买点 M8 螺栓")
    assert result["query_type"] == "vague"
    assert result["keywords"] == []
    assert result["brand"] is None


# ── M-6: _millis 把 naive(UTC)datetime 按 UTC 解释,不依赖运行机器时区 ────────
def test_millis_interprets_naive_datetime_as_utc():
    from datetime import datetime
    from app.services.comparison_task_service import _millis
    # DB 读出的 naive datetime 代表 UTC 值,转 epoch 必须按 UTC,
    # 否则在非 UTC 机器/容器上会偏移整数小时(本地 CST 会偏 -8h)。
    dt = datetime(2026, 6, 3, 1, 35, 32)
    assert _millis(dt) == 1780450532000  # 2026-06-03T01:35:32Z 的毫秒 epoch


def test_millis_none_returns_zero():
    from app.services.comparison_task_service import _millis
    assert _millis(None) == 0


# ── M-14: image_base64 从 create_draft_from_message 一路透传到 parse_intent ──
@pytest.mark.asyncio
async def test_image_base64_flows_through_to_parse_intent(monkeypatch):
    from app.services import comparison_structure, comparison_draft_service

    captured = {}

    async def fake_parse_intent(user_message, conversation_context=None, memory_context="", image_base64=""):
        captured["image_base64"] = image_base64
        # 返回 vague:_has_procurement_object 为假 → build 提前返回,链路不碰 DB
        return {
            "query_type": "vague", "need_clarification": False,
            "keywords": [], "spec_keywords": [], "brand": None,
            "l1_category": None, "l2_category": None,
            "l3_category": None, "l4_category": None, "attribute_gaps": [],
        }

    monkeypatch.setattr(comparison_structure, "parse_intent", fake_parse_intent)

    await comparison_draft_service.create_draft_from_message(
        user_id="u1", session_id="s1", message="看看这个轴承", image_base64="IMGDATA",
    )

    assert captured["image_base64"] == "IMGDATA"
