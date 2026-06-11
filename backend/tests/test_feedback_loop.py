"""反馈闭环测试:Memos(非结构化 memo)与结构化比价数据的配合。

覆盖三个易漏缝隙:
1. 写/读格式 round-trip —— save_feedback 写出的 memo 必须能被
   _get_disliked_offer_skus 的解析逻辑读回(两边只靠文本约定,改一边就断)。
2. 读取路径过滤 —— get_task 回放已落库的 items_json 时也要剔除 disliked
   (否则刷新/回看历史时已标记的 offer 复现;写入路径的 ranker 过滤管不到它)。
3. disliked 缓存 —— get_task 被前端高频轮询,不能每次打 Memos;但新反馈
   写入后缓存必须立刻失效,否则"标完 60 秒内再轮询又出现"。
"""
import pytest

from app.services.comparison_task_service import filter_disliked_items
from app.services.memory_service import memory_service


# ── 1) 写/读格式 round-trip ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_save_feedback_roundtrip_parsable(monkeypatch):
    """save_feedback 实际写出的 memo 内容,必须能被 disliked 解析逻辑读回同一编码。"""
    captured: list[str] = []

    async def fake_create_memo(content):
        captured.append(content)
        return {"name": "memos/fake"}

    monkeypatch.setattr(memory_service, "create_memo", fake_create_memo)
    await memory_service.save_feedback(
        user_id="roundtrip-user",
        action="disliked",
        item_code="10223718206032",
        item_name="玉美和葫芦项链 轻奢时尚百搭",
        brand_name="",
        l2_category="jd",
        l3_category="外部平台候选",
        specification="",
    )
    assert len(captured) == 1

    async def fake_list_memos(uid_tag, extra_tag=None, limit=10):
        return [{"content": captured[0]}] if extra_tag == "disliked" else []

    monkeypatch.setattr(memory_service, "list_memos", fake_list_memos)
    memory_service._disliked_cache.clear()
    sig = await memory_service.get_preference_signals("roundtrip-user")
    assert sig["disliked_skus"] == ["10223718206032"]


# ── 2) 读取路径过滤(纯函数) ────────────────────────────────────────────


def test_filter_disliked_items_removes_marked_offers():
    subtasks = [
        {
            "id": "st1",
            "platform": "jd",
            "items": [
                {"id": "a", "platformSku": "10223718206032", "title": "项链"},
                {"id": "b", "platformSku": "100351117472", "title": "手拉葫芦"},
            ],
        },
        {
            "id": "st2",
            "platform": "zkh",
            "items": [{"id": "c", "platformSku": "AA123", "title": "正常"}],
        },
    ]
    out = filter_disliked_items(subtasks, ["10223718206032"])
    assert [i["platformSku"] for i in out[0]["items"]] == ["100351117472"]
    assert [i["platformSku"] for i in out[1]["items"]] == ["AA123"]
    # 原列表不被原地修改
    assert len(subtasks[0]["items"]) == 2


def test_filter_disliked_items_matches_by_id_fallback():
    subtasks = [{"id": "st", "platform": "jd", "items": [{"id": "jd-h-3", "title": "无SKU商品"}]}]
    out = filter_disliked_items(subtasks, ["jd-h-3"])
    assert out[0]["items"] == []


def test_filter_disliked_items_noop_when_empty():
    subtasks = [{"id": "st", "platform": "jd", "items": [{"id": "a", "platformSku": "X"}]}]
    assert filter_disliked_items(subtasks, []) is subtasks
    assert filter_disliked_items(subtasks, None) is subtasks


# ── 3) disliked 缓存 + 新反馈写入立即失效 ───────────────────────────────


@pytest.mark.asyncio
async def test_disliked_cache_hits_and_busts_on_new_feedback(monkeypatch):
    calls = {"n": 0}

    async def fake_list_memos(uid_tag, extra_tag=None, limit=10):
        calls["n"] += 1
        return [{"content": "**编码：** `SKU-1`\n#feedback #disliked"}] if extra_tag == "disliked" else []

    async def fake_create_memo(content):
        return {"name": "memos/fake"}

    monkeypatch.setattr(memory_service, "list_memos", fake_list_memos)
    monkeypatch.setattr(memory_service, "create_memo", fake_create_memo)
    memory_service._disliked_cache.clear()

    first = await memory_service.get_disliked_skus_cached("cache-user")
    second = await memory_service.get_disliked_skus_cached("cache-user")
    assert first == second == ["SKU-1"]
    assert calls["n"] == 1  # 第二次命中缓存,没再打 Memos

    # 新反馈写入后缓存失效 → 下次重新拉取
    await memory_service.save_feedback(
        user_id="cache-user", action="disliked",
        item_code="SKU-2", item_name="x",
    )
    await memory_service.get_disliked_skus_cached("cache-user")
    assert calls["n"] == 2
