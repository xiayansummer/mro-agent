import json

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


def test_agent_context_text_truncates_long_content():
    text = _agent_context_text(
        role="assistant",
        content="x" * (AGENT_CONTEXT_MAX_CHARS + 10),
        sku_results=None,
        slot_clarification=None,
    )

    assert len(text) == AGENT_CONTEXT_MAX_CHARS + 1
    assert text.endswith("…")
