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
    generate_clarification_stream,
    generate_no_results_stream,
)
from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

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

    # Step 2: Search SKUs (manage DB session ourselves to avoid leaks in SSE)
    yield f"event: thinking\ndata: 正在搜索产品...\n\n"

    # Limit results by query precision to avoid overwhelming users
    # precise → 20 results; broad_spec → 8; application → 5; vague → 3
    _limit_map = {"precise": 20, "broad_spec": 8, "application": 5, "vague": 3}
    search_limit = _limit_map.get(query_type, 10)

    # Build competitor query from keywords
    kw_list = parsed.get("keywords") or []
    spec_kw = parsed.get("spec_keywords") or []
    brand_kw = parsed.get("brand") or ""
    competitor_query = " ".join(kw_list + spec_kw + ([brand_kw] if brand_kw else ""))

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

    # Step 3: Send SKU results
    if results:
        sku_data = json.dumps(results, ensure_ascii=False, default=str)
        yield f"event: sku_results\ndata: {sku_data}\n\n"

    if competitor_results:
        comp_data = json.dumps(competitor_results, ensure_ascii=False, default=str)
        yield f"event: competitor_results\ndata: {comp_data}\n\n"

    # Step 4: Generate response
    text_parts = []
    response_mode = "unknown"

    if results and need_clarification:
        response_mode = "broad"
        question = parsed.get("clarification_question", "能否提供更多细节？")
        async for chunk in generate_broad_response_stream(
            user_message, results, question, conv_messages,
            query_type=query_type, inferred_need=inferred_need, memory_context=memory_context,
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif results:
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
