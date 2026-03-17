import json
import logging
from collections.abc import AsyncGenerator
from app.db.mysql import AsyncSessionLocal
from app.services.intent_parser import parse_intent
from app.services.sku_search import search_skus, relaxed_search, attach_files
from app.services.response_gen import (
    generate_response_stream,
    generate_broad_response_stream,
    generate_clarification_stream,
    generate_no_results_stream,
)

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
) -> AsyncGenerator[str, None]:
    """Main agent orchestration: parse intent → search → generate response via SSE."""
    ctx = get_session_context(session_id)

    # Build conversation context for Claude (keep last 6 turns)
    conv_messages = ctx["conversation"][-6:]

    # Step 1: Parse intent
    try:
        parsed = await parse_intent(user_message, conv_messages)
        logger.info(f"Parsed intent: {json.dumps(parsed, ensure_ascii=False)}")
    except Exception as e:
        logger.error(f"Intent parsing failed: {e}")
        yield f"event: error\ndata: 抱歉，我暂时无法理解您的需求，请换个方式描述。\n\n"
        return

    ctx["last_intent"] = parsed
    need_clarification = parsed.get("need_clarification", False)

    # Step 2: Search SKUs (manage DB session ourselves to avoid leaks in SSE)
    yield f"event: thinking\ndata: 正在搜索产品...\n\n"

    async with AsyncSessionLocal() as db_session:
        results = await search_skus(db_session, parsed, limit=20)

        if not results:
            results = await relaxed_search(db_session, parsed, limit=20)

        results = await attach_files(db_session, results)

    ctx["last_results"] = results

    # Step 3: Send SKU results
    if results:
        sku_data = json.dumps(results, ensure_ascii=False, default=str)
        yield f"event: sku_results\ndata: {sku_data}\n\n"

    # Step 4: Generate response
    text_parts = []

    if results and need_clarification:
        question = parsed.get("clarification_question", "能否提供更多细节？")
        async for chunk in generate_broad_response_stream(
            user_message, results, question, conv_messages
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif results:
        async for chunk in generate_response_stream(user_message, results, conv_messages):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    elif need_clarification:
        question = parsed.get("clarification_question", "能否提供更多细节？")
        async for chunk in generate_clarification_stream(
            user_message, question, conv_messages
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    else:
        async for chunk in generate_no_results_stream(user_message, parsed):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    ctx["conversation"].append({"role": "user", "content": user_message})
    ctx["conversation"].append({"role": "assistant", "content": "".join(text_parts)})

    yield "event: done\ndata: \n\n"
