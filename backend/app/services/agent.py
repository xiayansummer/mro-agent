import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import AsyncGenerator

from app.services import chat_history_service, comparison_draft_service, comparison_refine_service, comparison_task_service
from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)

# 内存会话上限:防止 _sessions 字典与单会话 conversation 无界增长(慢速内存泄漏)。
_MAX_SESSIONS = 500
_MAX_CONVERSATION = 12

# Hold strong refs to fire-and-forget tasks so the GC can't collect them mid-flight.
_background_tasks: set = set()


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


# 同一会话反复追问的阈值:本轮之前已追问 ≥ 此值,就主动引导开新会话。
_REPEAT_CLARIFY_THRESHOLD = 1


def _slot_followup_text(conversation: list[dict]) -> str:
    """slot 追问时回给用户的提示文案。

    多轮"无缝追问"会概率性地把历史尝试的品牌/规格累积进检索结构(LLM 非确定,已复现),
    让用户陷在"追问→继续→又追问/搜空"的循环里出不来。这里数本会话此前已追问过几次
    (以"待确认参数"开头的 assistant 历史),反复追问(≥阈值)时主动引导用户用追问卡片上的
    「🔄 重新描述需求」开新会话、清空被污染的上下文——这是跳出污染循环的确定性出口。
    """
    prior_clarify = sum(
        1
        for m in conversation
        if m.get("role") == "assistant"
        and str(m.get("content", "")).startswith("待确认参数")
    )
    if prior_clarify >= _REPEAT_CLARIFY_THRESHOLD:
        return (
            "几轮下来还没锁定合适的产品，可能受了前面对话信息的干扰。"
            "建议点下方「🔄 重新描述需求」开个新会话，把品类、规格、品牌、数量一次说清，这样检索最准。"
        )
    return "请先通过上方卡片确认关键参数，确认后我再查询京东工业品和震坤行。"


# In-memory session store for hot multi-turn conversations.
# DB chat history is the source of truth for cold starts / multi-replica traffic.
# 用 OrderedDict 做 LRU:超过 _MAX_SESSIONS 淘汰最久未用的,防无界增长。
_sessions: "OrderedDict[str, dict]" = OrderedDict()


async def get_session_context(session_id: str, user_id: str = "") -> dict:
    ctx = _sessions.get(session_id)
    if ctx is None:
        ctx = {
            "conversation": await _load_session_conversation(session_id, user_id),
            "last_intent": None,
            "last_results": None,
        }
        _sessions[session_id] = ctx
        while len(_sessions) > _MAX_SESSIONS:
            _sessions.popitem(last=False)  # 淘汰最久未访问的会话
    else:
        _sessions.move_to_end(session_id)
        # 裁剪单会话历史,避免长会话 conversation 无界累积
        conv = ctx["conversation"]
        if len(conv) > _MAX_CONVERSATION:
            ctx["conversation"] = conv[-_MAX_CONVERSATION:]
    return ctx


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
    skip_clarification: bool = False,
) -> AsyncGenerator[str, None]:
    """Main agent orchestration: create external comparison draft via SSE."""
    # Immediately acknowledge receipt so the UI shows activity
    yield "event: thinking\ndata: 正在理解需求...\n\n"

    ctx = await get_session_context(session_id, user_id)

    # —— 精炼早分支:对已有比价结果的指令,不走新建比价 ——
    refine_cmd = comparison_refine_service.parse_refinement(user_message)
    if refine_cmd is not None:
        offers = await comparison_task_service.get_latest_session_offers(session_id, user_id)
        if not offers:
            guide = "您还没有可精炼的比价结果,先发起一次比价、出结果后我再帮您挑。"
            yield f"event: text\ndata: {json.dumps(guide, ensure_ascii=False)}\n\n"
            ctx["conversation"].append({"role": "user", "content": user_message})
            ctx["conversation"].append({"role": "assistant", "content": guide})
            yield "event: done\ndata: \n\n"
            return
        refined = comparison_refine_service.apply_refinement(offers, refine_cmd)
        source_pt = ""  # 可选:来源商品名,v1 留空(operationLabel 已含上下文,前端卡片不依赖它)
        if not refined:
            msg = "当前比价结果里没有符合条件的商品。"
            yield f"event: text\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n"
            ctx["conversation"].append({"role": "user", "content": user_message})
            ctx["conversation"].append({"role": "assistant", "content": msg})
            yield "event: done\ndata: \n\n"
            return
        payload = {"sourceProductType": source_pt, "operationLabel": refine_cmd["label"], "offers": refined}
        yield "event: refined_offers\ndata: " + json.dumps(payload, ensure_ascii=False, default=str) + "\n\n"
        intro = f"为您{refine_cmd['label']}:"
        yield f"event: text\ndata: {json.dumps(intro, ensure_ascii=False)}\n\n"
        ctx["conversation"].append({"role": "user", "content": user_message})
        ctx["conversation"].append({"role": "assistant", "content": f"[精炼结果: {refine_cmd['label']},{len(refined)} 条]"})
        yield "event: done\ndata: \n\n"
        return

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
            image_base64=image_base64,
            skip_clarification=skip_clarification,
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
        # 反复追问时引导开新会话(此处 ctx["conversation"] 尚未含本轮,数的是此前的追问次数)
        text = _slot_followup_text(ctx["conversation"])
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

    _task = asyncio.ensure_future(
        memory_service.save_session_summary(
            user_id=effective_user_id,
            user_message=user_message,
            intent=parsed,
            results=[],
            response_mode="comparison_draft",
            query_type=parsed.get("query_type", "comparison"),
        )
    )
    _background_tasks.add(_task)
    _task.add_done_callback(_background_tasks.discard)

    yield "event: done\ndata: \n\n"
