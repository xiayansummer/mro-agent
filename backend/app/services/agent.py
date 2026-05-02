import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from app.db.mysql import AsyncSessionLocal
from app.services.intent_parser import parse_intent
from app.services.sku_search import search_skus, relaxed_search, attach_files, find_alternatives
from app.services.competitor_search import search_ehsy
from app.services.response_gen import (
    generate_response_stream,
    generate_broad_response_stream,
    generate_guided_selection_stream,
    generate_clarification_stream,
    generate_no_results_stream,
)
from app.services.memory_service import memory_service
from app.services.standard_mapping import find_equivalents, ATTRIBUTE_KNOWLEDGE  # noqa: F401  # find_equivalents used in Task 6
from app.services.preference_ranker import rank_by_preference
from sqlalchemy import text as _text

logger = logging.getLogger(__name__)


async def _slot_round_count(session_id: str) -> int:
    """Count prior assistant messages in this session that have a slot_clarification.

    Returns 0 if the slot_clarification column doesn't exist yet (pre-migration).
    """
    async with AsyncSessionLocal() as s:
        try:
            r = await s.execute(
                _text(
                    "SELECT COUNT(*) FROM t_chat_message "
                    "WHERE session_id = :sid "
                    "AND role = 'assistant' "
                    "AND slot_clarification IS NOT NULL"
                ),
                {"sid": session_id},
            )
            return int(r.scalar() or 0)
        except Exception as e:
            # Column not yet migrated, or transient DB issue. Log and treat as 0
            # so the cap fails open (no spurious search-forcing).
            logger.warning("slot_round_count query failed: %s", e)
            return 0


# In-memory session store for multi-turn conversations
_sessions: dict[str, dict] = {}


def get_session_context(session_id: str) -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "conversation": [],
            "last_intent": None,
            "last_results": None,
        }
    return _sessions[session_id]


async def handle_message(
    session_id: str,
    user_message: str,
    user_id: str = "",
    image_base64: str = "",
) -> AsyncGenerator[str, None]:
    """Main agent orchestration: parse intent → search → generate response via SSE."""
    # Immediately acknowledge receipt so the UI shows activity
    yield "event: thinking\ndata: 正在理解需求...\n\n"

    ctx = get_session_context(session_id)

    # Build conversation context for Claude (keep last 6 turns)
    conv_messages = ctx["conversation"][-6:]

    # Step 1: Parse intent (with memory context if available)
    effective_user_id = user_id or session_id
    memory_context = ""
    try:
        memory_context = await memory_service.get_user_context(effective_user_id, limit=3)
        if memory_context:
            logger.info(f"Memory context loaded for user {effective_user_id[:8]}")
    except Exception as e:
        logger.warning(f"Memory retrieval failed (non-fatal): {e}")

    try:
        parsed = await parse_intent(user_message, conv_messages, memory_context, image_base64)
        logger.info(f"Parsed intent: {json.dumps(parsed, ensure_ascii=False)}")
    except Exception as e:
        logger.error(f"Intent parsing failed: {e}")
        yield f"event: error\ndata: 抱歉，我暂时无法理解您的需求，请换个方式描述。\n\n"
        return

    ctx["last_intent"] = parsed
    need_clarification = parsed.get("need_clarification", False)
    query_type = parsed.get("query_type", "")
    inferred_need = parsed.get("inferred_need", "")

    # ── Brand-only fallback ────────────────────────────────────────────
    # If user gave only a brand and no category, list the brand's L3 categories
    # via DB GROUP BY and let the user pick via chip card.
    if (
        parsed.get("brand")
        and not parsed.get("l1_category")
        and not parsed.get("l2_category")
        and not parsed.get("l3_category")
        and query_type in ("vague", "broad_spec")
    ):
        from app.services.sku_search import search_brand_clusters
        async with AsyncSessionLocal() as db_session:
            clusters = await search_brand_clusters(db_session, parsed["brand"])
        if clusters:
            slot_payload = {
                "summary": f"{parsed['brand']}品牌下找到 {len(clusters)} 类商品",
                "known": [{"label": "品牌", "value": parsed["brand"]}],
                "missing": [
                    {
                        "key": "category",
                        "icon": "📦",
                        "question": "请选择具体品类",
                        "options": [f"{name} ({cnt})" for name, cnt in clusters] + ["其他"],
                    }
                ],
            }
            yield "event: slot_clarification\ndata: " + json.dumps(slot_payload, ensure_ascii=False) + "\n\n"
            yield "event: text\ndata: " + json.dumps(
                f"已为您整理 {parsed['brand']} 品牌的商品分布，请选择具体品类 ↑", ensure_ascii=False
            ) + "\n\n"
            yield "event: done\ndata: \n\n"
            return

    # Step 2: Search SKUs (manage DB session ourselves to avoid leaks in SSE)
    yield f"event: thinking\ndata: 正在搜索产品...\n\n"

    # Limit results by query precision to avoid overwhelming users
    # precise → 20 results; broad_spec → 8; application → 5; vague → 3
    _limit_map = {"precise": 20, "broad_spec": 8, "application": 5, "vague": 3}
    search_limit = _limit_map.get(query_type, 10)

    # Build competitor query from keywords
    # Exclude machine/equipment model numbers — they cause 西域 to return the machine itself
    from app.services.sku_search import _looks_like_model_number
    kw_list = parsed.get("keywords") or []
    spec_kw = parsed.get("spec_keywords") or []
    brand_kw = parsed.get("brand") or ""
    competitor_spec = [s for s in spec_kw if not _looks_like_model_number(s)]
    competitor_query = " ".join(kw_list + competitor_spec + ([brand_kw] if brand_kw else []))

    async with AsyncSessionLocal() as db_session:
        if competitor_query:
            db_task = search_skus(db_session, parsed, limit=search_limit)
            competitor_task = search_ehsy(competitor_query, limit=5)
            (results, competitor_results) = await asyncio.gather(db_task, competitor_task)
        else:
            results = await search_skus(db_session, parsed, limit=search_limit)
            competitor_results = []

        if not results:
            results = await relaxed_search(db_session, parsed, limit=search_limit)

        results = await attach_files(db_session, results)

    ctx["last_results"] = results

    # ── 属性建议富化（broad_spec + attribute_gaps 时）──────────────────
    attribute_gaps = parsed.get("attribute_gaps") or []
    if attribute_gaps and query_type == "broad_spec" and results:
        parsed["attribute_suggestions"] = _build_attribute_suggestions(
            attribute_gaps, results, memory_context
        )

    # ── 偏好排序（所有有结果的查询）──────────────────────────────────────
    if results and memory_context:
        results = rank_by_preference(results, memory_context)
        ctx["last_results"] = results

    # ── 等效标准替代（结果 < 3 且含已知标准号）──────────────────────────
    equivalent_results: list[dict] = []
    original_standard: str = ""
    if len(results) < 3 and not need_clarification:
        all_kws = (parsed.get("keywords") or []) + (parsed.get("spec_keywords") or [])
        equivalents = find_equivalents(all_kws)
        if equivalents:
            # 找出触发等效替代的原始标准号（从 all_kws 中找第一个匹配已知标准的关键词）
            from app.services.standard_mapping import STANDARD_EQUIVALENTS
            for kw in all_kws:
                normalized = kw.upper().replace(" ", "").replace("/", "").replace("-", "").replace(".", "")
                if normalized in {k.upper().replace(" ", "").replace("/", "").replace("-", "").replace(".", "") for k in STANDARD_EQUIVALENTS}:
                    original_standard = kw
                    break

            yield f"event: thinking\ndata: 正在搜索等效替代产品...\n\n"
            equiv_parsed = {
                **parsed,
                "spec_keywords": (parsed.get("spec_keywords") or []) + equivalents,
            }
            async with AsyncSessionLocal() as db_session:
                equivalent_results = await search_skus(db_session, equiv_parsed, limit=search_limit)
                equivalent_results = await attach_files(db_session, equivalent_results)

            if equivalent_results:
                ctx["last_results"] = equivalent_results
                equiv_data = json.dumps(equivalent_results, ensure_ascii=False, default=str)
                yield f"event: sku_results\ndata: {equiv_data}\n\n"

    # Guided mode: vague only — application now searches first, shows products if found
    is_guided = need_clarification and query_type == "vague"

    # 3-round hard cap: stop asking, search with whatever we have
    rounds_so_far = await _slot_round_count(session_id)
    force_search = rounds_so_far >= 3
    if force_search:
        need_clarification = False
        is_guided = False
    # application with no results falls back to guided knowledge response
    application_no_results = query_type == "application" and not results

    # Step 3: Send SKU results (skip for guided/no-results application)
    # Skip original results if equivalent results were already sent to avoid duplicate sku_results events
    if results and not is_guided and not equivalent_results:
        sku_data = json.dumps(results, ensure_ascii=False, default=str)
        yield f"event: sku_results\ndata: {sku_data}\n\n"

    if competitor_results and not is_guided:
        comp_data = json.dumps(competitor_results, ensure_ascii=False, default=str)
        yield f"event: competitor_results\ndata: {comp_data}\n\n"

    # Step 4: Generate response
    text_parts = []
    response_mode = "unknown"

    # Prepend structured requirement summary for application queries with results
    requirement_summary = parsed.get("requirement_summary")
    if requirement_summary and query_type == "application" and results:
        summary_text = f"**需求解析：** {requirement_summary}\n\n---\n\n"
        yield f"event: text\ndata: {json.dumps(summary_text, ensure_ascii=False)}\n\n"
        text_parts.append(summary_text)

    if is_guided or application_no_results:
        # Guided flow step 1+2: identify product type + ask structured questions
        response_mode = "guided"
        question = parsed.get("clarification_question", "能否提供更多细节？")
        async for chunk in generate_guided_selection_stream(
            user_message, inferred_need, question, conv_messages,
            query_type=query_type, memory_context=memory_context,
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif results and need_clarification:
        # broad_spec: show products + ask for missing specs
        response_mode = "broad"
        question = parsed.get("clarification_question", "能否提供更多细节？")
        async for chunk in generate_broad_response_stream(
            user_message, results, question, conv_messages,
            query_type=query_type, inferred_need=inferred_need, memory_context=memory_context,
            attribute_suggestions=parsed.get("attribute_suggestions"),
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif equivalent_results and original_standard:
        response_mode = "equivalent"
        from app.services.response_gen import generate_equivalent_stream
        async for chunk in generate_equivalent_stream(
            user_message, equivalent_results, original_standard,
            memory_context=memory_context,
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif results and not equivalent_results:
        response_mode = "precise"
        async for chunk in generate_response_stream(
            user_message, results, conv_messages,
            query_type=query_type, inferred_need=inferred_need, memory_context=memory_context,
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif need_clarification:
        response_mode = "clarification"
        question = parsed.get("clarification_question", "能否提供更多细节？")
        async for chunk in generate_clarification_stream(
            user_message, question, conv_messages
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    else:
        response_mode = "no_results"
        # Find similar products to show as alternatives
        async with AsyncSessionLocal() as db_session:
            alternatives = await find_alternatives(db_session, parsed, limit=10)
            alternatives = await attach_files(db_session, alternatives)

        if alternatives:
            alt_data = json.dumps(alternatives, ensure_ascii=False, default=str)
            yield f"event: sku_results\ndata: {alt_data}\n\n"

        async for chunk in generate_no_results_stream(user_message, parsed, alternatives):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    # Store compact search summary for continuity (cleaner than full prose for intent parsing)
    kws = parsed.get("keywords") or []
    specs = parsed.get("spec_keywords") or []
    brand = parsed.get("brand") or ""
    search_summary = f"[已搜索: {' '.join(kws)}"
    if specs:
        search_summary += f" 规格:{' '.join(specs)}"
    if brand:
        search_summary += f" 品牌:{brand}"
    search_summary += f", 找到{len(results)}个产品]"
    if results:
        top_names = "、".join(r["item_name"][:15] for r in results[:3])
        search_summary += f" 代表: {top_names}"

    ctx["conversation"].append({"role": "user", "content": user_message})
    ctx["conversation"].append({"role": "assistant", "content": search_summary})

    # Step 5: Save memory before yielding done (runs concurrently, non-blocking)
    logger.info(f"Scheduling memory save for user={effective_user_id[:8]}")
    asyncio.ensure_future(
        memory_service.save_session_summary(
            user_id=effective_user_id,
            user_message=user_message,
            intent=parsed,
            results=results,
            response_mode=response_mode,
            query_type=query_type,
        )
    )

    yield "event: done\ndata: \n\n"


def _build_attribute_suggestions(
    attribute_gaps: list[str],
    results: list[dict],
    memory_context: str,
) -> dict[str, list[dict]]:
    """
    对每个 attribute_gap，从行业知识库取基础选项，
    过滤保留搜索结果中实际出现的值，并将用户偏好项排到首位。
    """
    result_text = " ".join(
        f"{r.get('specification', '')} {r.get('attribute_details', '')}"
        for r in results
    ).lower()

    preferred_values = _preferred_attr_values(memory_context)
    suggestions: dict[str, list[dict]] = {}

    for gap in attribute_gaps:
        base_options = ATTRIBUTE_KNOWLEDGE.get(gap, [])
        if not base_options:
            continue

        # 过滤到结果中实际存在的选项（找不到匹配时保留全部）
        matched = [opt for opt in base_options if _value_appears_in_text(opt["value"], result_text)]
        options = matched if matched else base_options

        # 用户偏好项排到首位
        if preferred_values:
            preferred = [opt for opt in options
                         if opt["value"].split("（")[0].lower() in preferred_values]
            others = [opt for opt in options
                      if opt["value"].split("（")[0].lower() not in preferred_values]
            options = preferred + others

        suggestions[gap] = options

    return suggestions


def _value_appears_in_text(value: str, text: str) -> bool:
    """检查选项的核心标识符是否出现在结果文本中。"""
    core = value.split("（")[0].strip().lower()
    return bool(core) and core in text


def _preferred_attr_values(memory_context: str) -> set[str]:
    """从 memory_context 提取偏好材质/规格关键词（小写）。"""
    preferred: set[str] = set()
    for line in memory_context.splitlines():
        if "偏好材质" in line or "常用规格" in line:
            parts = line.split("：", 1)
            if len(parts) == 2:
                for p in parts[1].split(","):
                    preferred.add(p.strip().lower())
    return preferred
