import pytest

from app.routers import inquiry


class _FakeResult:
    def __init__(self, should, structure=None, guidance=None):
        self.shouldCreateDraft = should
        self.structure = structure
        self.guidance = guidance


@pytest.mark.asyncio
async def test_compare_row_builds_task(monkeypatch):
    captured = {}

    async def fake_build(query, conversation_context=None, memory_context="", image_base64="", skip_clarification=False):
        captured["query"] = query
        captured["conversation_context"] = conversation_context
        captured["skip_clarification"] = skip_clarification
        return _FakeResult(True, structure=object())

    async def fake_create_draft(user_id, session_id, raw_query, structure):
        captured["session_id"] = session_id
        return {"id": "draft-1"}

    async def fake_start_draft(draft_id, user_id):
        captured["draft_id"] = draft_id
        return {"id": "task-1"}

    monkeypatch.setattr(inquiry, "build_comparison_structure", fake_build)
    monkeypatch.setattr(inquiry, "create_draft", fake_create_draft)
    monkeypatch.setattr(inquiry, "start_draft", fake_start_draft)
    monkeypatch.setattr(inquiry, "_require_db_user_id", lambda u: 14)

    resp = await inquiry.compare_inquiry_row(
        {"需求品名": "防尘口罩", "需求品牌": "3M", "需求型号": "KN95"}, user_id="u14"
    )

    assert resp["ok"] is True
    assert resp["taskId"] == "task-1"
    assert resp["draftId"] == "draft-1"
    assert captured["conversation_context"] == []
    assert captured["skip_clarification"] is True
    assert captured["session_id"].startswith("inquiry-14-")
    assert "防尘口罩" in captured["query"] and "3M" in captured["query"] and "KN95" in captured["query"]


@pytest.mark.asyncio
async def test_compare_row_rejects_vague(monkeypatch):
    started = {"called": False}

    async def fake_build(query, conversation_context=None, memory_context="", image_base64="", skip_clarification=False):
        return _FakeResult(False, guidance="该行需求过于宽泛")

    async def fake_start_draft(draft_id, user_id):
        started["called"] = True
        return {"id": "x"}

    monkeypatch.setattr(inquiry, "build_comparison_structure", fake_build)
    monkeypatch.setattr(inquiry, "start_draft", fake_start_draft)

    resp = await inquiry.compare_inquiry_row({"需求品名": "东西"}, user_id="u14")

    assert resp["ok"] is False
    assert "宽泛" in resp["guidance"]
    assert started["called"] is False


@pytest.mark.asyncio
async def test_compare_row_empty_query_returns_guidance():
    resp = await inquiry.compare_inquiry_row({"需求品名": "", "需求品牌": "", "需求型号": ""}, user_id="u14")
    assert resp["ok"] is False
