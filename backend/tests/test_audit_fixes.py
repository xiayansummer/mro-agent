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


# ── DPO 偏好硬加权: get_preference_signals 解析 #preference memo 为结构化偏好 ──
@pytest.mark.asyncio
async def test_get_preference_signals_parses_preference_memo(monkeypatch):
    from app.services.memory_service import memory_service

    async def fake_list_memos(uid_tag, extra_tag=None, limit=10):
        return [{"content": "## 用户偏好摘要\n偏好品牌：美和, 沪工\n常用品类：手拉葫芦\n常用规格：2吨\n"}]

    monkeypatch.setattr(memory_service, "list_memos", fake_list_memos)
    sig = await memory_service.get_preference_signals("u1")
    assert sig["brands"] == ["美和", "沪工"]
    assert sig["categories"] == ["手拉葫芦"]


@pytest.mark.asyncio
async def test_get_preference_signals_empty_when_no_memo(monkeypatch):
    from app.services.memory_service import memory_service

    async def fake_list_memos(uid_tag, extra_tag=None, limit=10):
        return []

    monkeypatch.setattr(memory_service, "list_memos", fake_list_memos)
    memory_service._disliked_cache.clear()
    sig = await memory_service.get_preference_signals("u1")
    assert sig == {"brands": [], "categories": [], "disliked_skus": []}


@pytest.mark.asyncio
async def test_get_preference_signals_extracts_disliked_skus(monkeypatch):
    """#feedback #disliked memo 里的商品编码(平台 SKU)被解析进 disliked_skus,供比价剔除。"""
    from app.services.memory_service import memory_service

    disliked_memo = {
        "content": (
            "## 产品反馈\n\n**操作：** 👎 不符合需求\n"
            "**产品：** 玉美和葫芦项链\n**编码：** `10223718206032`\n\n"
            "#u_x #feedback #disliked"
        )
    }

    async def fake_list_memos(uid_tag, extra_tag=None, limit=10):
        return [disliked_memo] if extra_tag == "disliked" else []

    monkeypatch.setattr(memory_service, "list_memos", fake_list_memos)
    memory_service._disliked_cache.clear()
    sig = await memory_service.get_preference_signals("u1")
    assert sig["disliked_skus"] == ["10223718206032"]


# ── 直接检索: skip_clarification 跳过参数追问,避免反复问未知参数 ─────────────
@pytest.mark.asyncio
async def test_skip_clarification_bypasses_slot_questions(monkeypatch):
    from app.services import comparison_structure as cs

    async def fake_parse_intent(user_message, conversation_context=None, memory_context="", image_base64=""):
        return {
            "query_type": "comparison", "keywords": ["防电弧手套"], "spec_keywords": [],
            "brand": None, "l1_category": None, "l2_category": None,
            "l3_category": "防电弧手套", "l4_category": None, "attribute_gaps": [],
            "inferred_need": "防电弧手套",
        }

    monkeypatch.setattr(cs, "parse_intent", fake_parse_intent)
    monkeypatch.setattr(cs, "_parsed_slot_clarification", lambda parsed: None)

    slot_calls = []

    def fake_slot(parsed, structure):
        slot_calls.append(1)
        return {"summary": "x", "known": [], "missing": [{"key": "quantity", "question": "数量?", "options": []}]}

    monkeypatch.setattr(cs, "_comparison_slot_clarification", fake_slot)

    # 默认:执行 slot 检查 → 返回 slotClarification(会追问)
    r1 = await cs.build_comparison_structure("防电弧手套")
    assert r1.slotClarification is not None
    assert len(slot_calls) == 1

    # skip:跳过 slot 检查 → 不再返回 slotClarification
    r2 = await cs.build_comparison_structure("防电弧手套", skip_clarification=True)
    assert r2.slotClarification is None
    assert len(slot_calls) == 1  # 没有再次调用 slot 检查


@pytest.mark.asyncio
async def test_slot_answer_message_auto_skips_even_without_flag(monkeypatch):
    """彻底解决反复追问:消息带 slot 卡片概述文本 → 后端自动识别为 slot 回答并跳过,
    不依赖前端 skip flag(防前端缓存/旧版导致同一参数被反复问)。"""
    from app.services import comparison_structure as cs

    async def fake_parse_intent(user_message, conversation_context=None, memory_context="", image_base64=""):
        return {
            "query_type": "comparison", "keywords": ["手拉葫芦"], "spec_keywords": [],
            "brand": None, "l1_category": None, "l2_category": None,
            "l3_category": "手拉葫芦", "l4_category": None, "attribute_gaps": [],
            "inferred_need": "手拉葫芦",
        }

    monkeypatch.setattr(cs, "parse_intent", fake_parse_intent)
    monkeypatch.setattr(cs, "_parsed_slot_clarification", lambda parsed: None)
    slot_calls = []
    monkeypatch.setattr(cs, "_comparison_slot_clarification",
                        lambda p, s: slot_calls.append(1) or {"summary": "x", "known": [], "missing": [{"key": "quantity", "question": "数量?", "options": []}]})

    # 模拟 slot 卡片提交回来的消息(带卡片概述文本),未显式传 skip_clarification=True
    msg = "需要采购手拉葫芦，请先确认关键参数后再查询京东工业品和震坤行。 商品类型手拉葫芦 按平台起订量"
    r = await cs.build_comparison_structure(msg)
    assert r.slotClarification is None  # 自动跳过,不再追问
    assert len(slot_calls) == 0


# ── 搜索词去型号:厂家内部型号(HSZ-622A)京东标题常不含,带上搜不到;交 ranker 打分 ──
def test_search_terms_exclude_model_for_recall():
    from app.models.comparison import (
        ComparisonStructure, ComparisonSpecification, ComparisonCategory,
    )
    from app.services.comparison_query_builder import build_search_terms

    structure = ComparisonStructure(
        category=ComparisonCategory(l3="手拉葫芦"),
        specification=ComparisonSpecification(
            productType="手拉葫芦", brand="美和", model="HSZ-622A", size="1吨",
        ),
    )
    terms = build_search_terms(structure)
    # 没有任何 jd/zkh 搜索词带型号
    assert all("HSZ-622A" not in t for t in terms.jd), terms.jd
    assert all("HSZ-622A" not in t for t in terms.zkh), terms.zkh
    # 但保留"品牌+品类(+规格)"这种平台能搜到的有效词
    assert any("美和" in t and "手拉葫芦" in t for t in terms.jd)


# ── 环节1(系统性,非特例):多词品类降级序列必含"单核心品类词"最宽档,保证召回 ──
def test_search_terms_multiword_producttype_has_core_word_fallback():
    from app.models.comparison import ComparisonStructure, ComparisonSpecification
    from app.services.comparison_query_builder import build_search_terms

    # 用三个不同品类验证系统性:核心词取多词品类的最后一个词(通常是上位品类)
    cases = [
        ("防电弧手套 绝缘手套", "安全牌", "安全牌 绝缘手套"),
        ("不锈钢 法兰", "某牌", "某牌 法兰"),
        ("外六角 螺栓", "固万基", "固万基 螺栓"),
    ]
    for product_type, brand, expected_core_term in cases:
        s = ComparisonStructure(
            specification=ComparisonSpecification(productType=product_type, brand=brand)
        )
        jd = build_search_terms(s).jd
        assert expected_core_term in jd, (product_type, jd)

    # 单词品类:核心词==品类,不引入重复
    s_single = ComparisonStructure(
        specification=ComparisonSpecification(productType="球阀", brand="某牌")
    )
    jd_single = build_search_terms(s_single).jd
    assert jd_single == list(dict.fromkeys(jd_single))  # 无重复项


# ── 环节2(系统性):productType 部分命中按比例给分,替代全词二元,避免相关结果被误杀 ──
def test_producttype_partial_match_scored_proportionally():
    from app.models.comparison import ComparisonStructure, ComparisonSpecification
    from app.services.comparison_ranker import rank_external_offers

    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="防电弧手套 绝缘手套")
    )
    offers = [
        {"id": "partial", "title": "绝缘手套 5KV 电工", "priceValue": 50, "rawRank": 1},
        {"id": "full", "title": "防电弧手套 绝缘手套 Class00", "priceValue": 60, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    by_id = {o["id"]: o for o in ranked}
    # 部分命中("绝缘手套")也保留并拿到正分,全命中分更高
    assert "full" in by_id and "partial" in by_id, [o["id"] for o in ranked]
    assert by_id["full"]["matchScore"] > by_id["partial"]["matchScore"]
    assert by_id["partial"]["matchScore"] > 0
    assert any("部分匹配" in r for r in by_id["partial"]["matchReasons"])


# ── 环节3(系统性):相对过滤替代绝对阈值——低分群保召回、高分时滤离谱 ──────────────
def test_relative_filter_keeps_recall_when_all_scores_low():
    from app.models.comparison import ComparisonStructure, ComparisonSpecification
    from app.services.comparison_ranker import rank_external_offers

    structure = ComparisonStructure(
        specification=ComparisonSpecification(productType="防电弧手套 绝缘手套")
    )
    # 全部只部分匹配(绝缘手套),无高分基准 → 不应被误杀(绝对阈值会全保留,相对也应保留)
    offers = [{"id": f"g{i}", "title": "绝缘手套 5KV", "priceValue": 50 + i, "rawRank": i} for i in range(4)]
    ranked = rank_external_offers(structure, offers)
    assert len(ranked) == 4, [o["matchScore"] for o in ranked]


def test_relative_filter_drops_low_relative_when_top_high():
    from app.models.comparison import ComparisonStructure, ComparisonSpecification
    from app.services.comparison_ranker import rank_external_offers

    structure = ComparisonStructure(
        specification=ComparisonSpecification(
            productType="防电弧手套 绝缘手套", material="橡胶", standard="GB17622",
            attributes=[{"name": "电压", "value": "5KV"}, {"name": "等级", "value": "00级"}],
        )
    )
    offers = [
        {"id": "top", "title": "防电弧手套 绝缘手套 橡胶 GB17622 5KV 00级", "priceValue": 50, "rawRank": 1},
        {"id": "weak", "title": "绝缘手套 普通款", "priceValue": 30, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    ids = [o["id"] for o in ranked]
    assert "top" in ids
    # weak 仅部分匹配(~17 分),远低于 top,相对过滤应滤掉(绝对阈值 10 下本会保留)
    assert "weak" not in ids, [(o["id"], o["matchScore"]) for o in ranked]


# ── 系统 bug:_compact 大小写不统一,型号/标准等英文参数匹配失效 ──────────────
def test_english_params_match_case_insensitively():
    from app.models.comparison import ComparisonStructure, ComparisonSpecification
    from app.services.comparison_ranker import rank_external_offers

    structure = ComparisonStructure(
        specification=ComparisonSpecification(
            productType="手拉葫芦", brand="美和", model="HSZ-622A", size="2吨"
        )
    )
    offers = [
        {"id": "with_model", "title": "美和 手拉葫芦 HSZ-622A 2吨 环链", "priceValue": 268, "rawRank": 1},
        {"id": "no_model", "title": "美和 手拉葫芦 2吨 手扳葫芦", "priceValue": 255, "rawRank": 2},
    ]
    ranked = rank_external_offers(structure, offers)
    by_id = {o["id"]: o for o in ranked}
    # 含型号的应命中型号加权 → 分更高、排第一(haystack 已小写,model token 也须小写比较)
    assert ranked[0]["id"] == "with_model", [(o["id"], o["matchScore"]) for o in ranked]
    assert by_id["with_model"]["matchScore"] > by_id["no_model"]["matchScore"]
    assert any("型号匹配" in r for r in by_id["with_model"]["matchReasons"])

    # standard 同样大小写不敏感
    s2 = ComparisonStructure(
        specification=ComparisonSpecification(productType="外六角螺栓", standard="DIN933")
    )
    r2 = rank_external_offers(s2, [{"id": "a", "title": "外六角螺栓 din933 m8 全牙", "priceValue": 1, "rawRank": 1}])
    assert any("标准匹配" in r for r in r2[0]["matchReasons"]), r2[0]["matchReasons"]


# ── 比价解析鲁棒性:LLM 偶发返回空抽取时用原始消息兜底,不误弹"请提供产品名称" ──
def test_fallback_keyword_strips_procurement_prefix():
    from app.services.comparison_structure import _fallback_keyword_from_message
    assert _fallback_keyword_from_message("需要采购防尘口罩") == "防尘口罩"
    assert _fallback_keyword_from_message("帮我找M8螺栓") == "M8螺栓"
    assert _fallback_keyword_from_message("买O型圈") == "O型圈"
    assert _fallback_keyword_from_message("你好") == ""
    assert _fallback_keyword_from_message("") == ""
    assert _fallback_keyword_from_message("买") == ""  # 单字无实义


def test_has_procurement_object_accepts_l2_only():
    from app.services.comparison_structure import _has_procurement_object
    # LLM 只归到 l2 也算有产品对象(与 _product_type 用 l2 兜底保持一致)
    assert _has_procurement_object({"query_type": "vague", "l2_category": "口罩"}) is True


@pytest.mark.asyncio
async def test_comparison_fallback_when_llm_returns_empty(monkeypatch):
    """复现线上 bug:LLM 对清晰输入返回空 keywords 时,不应弹回"请提供产品名称",
    而是用原始消息兜底建出比价结构。"""
    from app.services import comparison_structure as cs

    async def fake_parse(user_message, conversation_context=None, memory_context="", image_base64=""):
        return {"query_type": "vague", "keywords": [], "spec_keywords": [], "brand": None,
                "l1_category": None, "l2_category": None, "l3_category": None,
                "l4_category": None, "attribute_gaps": []}

    monkeypatch.setattr(cs, "parse_intent", fake_parse)
    res = await cs.build_comparison_structure("需要采购防尘口罩", skip_clarification=True)
    assert res.shouldCreateDraft is True
    assert res.structure.specification.productType == "防尘口罩"


@pytest.mark.asyncio
async def test_comparison_greeting_still_bounces(monkeypatch):
    """纯问候/无产品消息仍应弹回 guidance,不被兜底误判为产品。"""
    from app.services import comparison_structure as cs

    async def fake_parse(user_message, conversation_context=None, memory_context="", image_base64=""):
        return {"query_type": "vague", "keywords": [], "spec_keywords": [], "brand": None,
                "l1_category": None, "l2_category": None, "l3_category": None,
                "l4_category": None, "attribute_gaps": []}

    monkeypatch.setattr(cs, "parse_intent", fake_parse)
    res = await cs.build_comparison_structure("你好", skip_clarification=True)
    assert res.shouldCreateDraft is False
    assert "请提供" in (res.guidance or "")
