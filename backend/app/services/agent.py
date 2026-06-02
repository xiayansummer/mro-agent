import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from app.db.mysql import AsyncSessionLocal
from app.services import chat_history_service, comparison_draft_service
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


def _slot_clarification_event(parsed: dict, force_search: bool) -> str | None:
    """Build the SSE 'slot_clarification' event payload, or None to skip emission."""
    if force_search:
        return None
    payload = parsed.get("slot_clarification")
    if not payload:
        return None
    return "event: slot_clarification\ndata: " + json.dumps(payload, ensure_ascii=False) + "\n\n"


def _slot_context_summary(slot: dict) -> str:
    summary = slot.get("summary") or ""
    known = slot.get("known") or []
    missing = slot.get("missing") or []
    known_text = "；".join(
        f"{item.get('label')}:{item.get('value')}"
        for item in known
        if isinstance(item, dict) and item.get("label") and item.get("value")
    )
    questions = "；".join(
        item.get("question", "")
        for item in missing
        if isinstance(item, dict) and item.get("question")
    )
    parts = [part for part in [summary, f"已知参数：{known_text}" if known_text else "", questions] if part]
    return "待确认参数：" + "；".join(parts) if parts else "待确认参数"


# In-memory session store for hot multi-turn conversations.
# DB chat history is the source of truth for cold starts / multi-replica traffic.
_sessions: dict[str, dict] = {}


async def get_session_context(session_id: str, user_id: str = "") -> dict:
    if session_id not in _sessions:
        _sessions[session_id] = {
            "conversation": await _load_session_conversation(session_id, user_id),
            "last_intent": None,
            "last_results": None,
        }
    return _sessions[session_id]


async def _load_session_conversation(session_id: str, user_id: str) -> list[dict]:
    if not user_id:
        return []
    try:
        return await chat_history_service.get_recent_agent_context(
            session_id=session_id,
            user_id=user_id,
            limit=6,
        )
    except Exception as e:
        logger.warning("Failed to load DB-backed conversation context: %s", e)
        return []


async def handle_message(
    session_id: str,
    user_message: str,
    user_id: str = "",
    image_base64: str = "",
) -> AsyncGenerator[str, None]:
    """Main agent orchestration: create external comparison draft via SSE."""
    # Immediately acknowledge receipt so the UI shows activity
    yield "event: thinking\ndata: 正在理解需求...\n\n"

    ctx = await get_session_context(session_id, user_id)

    # Build conversation context for Claude (keep last 6 turns)
    conv_messages = ctx["conversation"][-6:]

    effective_user_id = user_id or session_id
    memory_context = ""
    try:
        memory_context = await memory_service.get_user_context(effective_user_id, limit=3)
        if memory_context:
            logger.info(f"Memory context loaded for user {effective_user_id[:8]}")
    except Exception as e:
        logger.warning(f"Memory retrieval failed (non-fatal): {e}")

    try:
        result = await comparison_draft_service.create_draft_from_message(
            user_id=user_id,
            session_id=session_id,
            message=user_message,
            conversation_context=conv_messages,
            memory_context=memory_context,
        )
    except Exception as e:
        logger.error(f"Comparison draft creation failed: {e}", exc_info=True)
        yield "event: error\ndata: 抱歉，我暂时无法处理该比价需求，请换个方式描述。\n\n"
        return

    parsed = result.get("parsedIntent") or {}
    ctx["last_intent"] = parsed

    slot_clarification = result.get("slotClarification")
    if slot_clarification:
        yield "event: slot_clarification\ndata: " + json.dumps(slot_clarification, ensure_ascii=False) + "\n\n"
        text = "请先通过上方卡片确认关键参数，确认后我再查询京东工业品和震坤行。"
        yield f"event: text\ndata: {json.dumps(text, ensure_ascii=False)}\n\n"
        ctx["conversation"].append({"role": "user", "content": user_message})
        ctx["conversation"].append({"role": "assistant", "content": _slot_context_summary(slot_clarification)})
        yield "event: done\ndata: \n\n"
        return

    if not result.get("shouldCreateDraft"):
        guidance = result.get("guidance") or "请补充产品名称、规格或采购约束。"
        yield f"event: text\ndata: {json.dumps(guidance, ensure_ascii=False)}\n\n"
        ctx["conversation"].append({"role": "user", "content": user_message})
        ctx["conversation"].append({"role": "assistant", "content": guidance})
        yield "event: done\ndata: \n\n"
        return

    draft = result["draft"]
    yield "event: comparison_draft\ndata: " + json.dumps(draft, ensure_ascii=False, default=str) + "\n\n"
    product_type = (
        draft.get("structure", {}).get("specification", {}).get("productType")
        or draft.get("structure", {}).get("category", {}).get("l3")
        or "该产品"
    )
    text = f"已整理「{product_type}」的比价结构，请确认后开始查询京东工业品和震坤行。"
    yield f"event: text\ndata: {json.dumps(text, ensure_ascii=False)}\n\n"

    ctx["conversation"].append({"role": "user", "content": user_message})
    ctx["conversation"].append({"role": "assistant", "content": f"[已创建比价草稿: {product_type}]"})

    asyncio.ensure_future(
        memory_service.save_session_summary(
            user_id=effective_user_id,
            user_message=user_message,
            intent=parsed,
            results=[],
            response_mode="comparison_draft",
            query_type=parsed.get("query_type", "comparison"),
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
