import json

import pytest

from app.services import chat_history_service
from app.services.chat_history_service import (
    AGENT_CONTEXT_MAX_CHARS,
    _agent_context_text,
)


def test_agent_context_text_summarizes_slot_clarification():
    slot = {
        "summary": "已识别为扳手",
        "missing": [{"question": "请选择规格"}, {"question": "请选择品牌"}],
    }

    text = _agent_context_text(
        role="assistant",
        content="",
        sku_results=None,
        slot_clarification=json.dumps(slot, ensure_ascii=False),
    )

    assert "已识别为扳手" in text
    assert "请选择规格" in text
    assert "请选择品牌" in text


def test_agent_context_text_summarizes_sku_results():
    skus = [
        {"item_name": "不锈钢六角螺栓 M8"},
        {"item_name": "碳钢六角螺栓 M10"},
    ]

    text = _agent_context_text(
        role="assistant",
        content="",
        sku_results=json.dumps(skus, ensure_ascii=False),
        slot_clarification=None,
    )

    assert text == "[已展示产品: 不锈钢六角螺栓 M8、碳钢六角螺栓 M10]"


def test_agent_context_text_summarizes_comparison_draft():
    draft = {
        "structure": {
            "category": {"l3": "六角头螺栓"},
            "specification": {"productType": "外六角螺栓"},
        },
        "searchTerms": {"jd": ["外六角螺栓 304 M8"]},
    }

    text = _agent_context_text(
        role="assistant",
        content="",
        sku_results=None,
        slot_clarification=None,
        comparison_draft=json.dumps(draft, ensure_ascii=False),
    )

    assert text == "[已创建比价草稿: 外六角螺栓 搜索词:外六角螺栓 304 M8]"


def test_agent_context_text_truncates_long_content():
    text = _agent_context_text(
        role="assistant",
        content="x" * (AGENT_CONTEXT_MAX_CHARS + 10),
        sku_results=None,
        slot_clarification=None,
    )

    assert len(text) == AGENT_CONTEXT_MAX_CHARS + 1
    assert text.endswith("…")


# ── save_turn 写侧 IDOR(H-4)──────────────────────────────────────────────


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


def _fake_session(record, select_row):
    class _S:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def execute(self, statement, params=None):
            sql = str(statement)
            record.append(sql)
            if "SELECT id, title, user_id FROM t_chat_session" in sql:
                return _FakeResult(select_row(params))
            return _FakeResult()

        async def commit(self):
            pass

    return _S


@pytest.mark.asyncio
async def test_save_turn_refuses_cross_user_session(monkeypatch):
    """A 用 B 的 session_id 调 save_turn 应被拒写,不污染 B 的会话(写侧 IDOR)。"""
    executed = []
    # 会话存在且属于 user_id=999(别人),当前调用者 db_id=7
    monkeypatch.setattr(chat_history_service, "AsyncSessionLocal",
                        _fake_session(executed, lambda p: (p["id"], "B 的标题", 999)))
    monkeypatch.setattr(chat_history_service, "_external_id_to_db_id", lambda uid: 7)

    await chat_history_service.save_turn(
        session_id="B-session", user_id="u7", user_message="hi", image_b64="",
        assistant_text="ok", sku_results=None, competitor_results=None,
    )

    assert not any("INSERT INTO t_chat_message" in s for s in executed)
    assert not any("UPDATE t_chat_session" in s for s in executed)


@pytest.mark.asyncio
async def test_save_turn_allows_own_session(monkeypatch):
    """属于自己的会话正常写入。"""
    executed = []
    monkeypatch.setattr(chat_history_service, "AsyncSessionLocal",
                        _fake_session(executed, lambda p: (p["id"], "新对话", 7)))
    monkeypatch.setattr(chat_history_service, "_external_id_to_db_id", lambda uid: 7)

    await chat_history_service.save_turn(
        session_id="my-session", user_id="u7", user_message="hi", image_b64="",
        assistant_text="ok", sku_results=None, competitor_results=None,
    )

    assert any("INSERT INTO t_chat_message" in s for s in executed)
