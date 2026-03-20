from collections.abc import AsyncGenerator
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.AI_API_KEY, base_url=settings.AI_BASE_URL)

def _build_system_prompt(memory_context: str = "") -> str:
    """Build response system prompt, optionally adjusted for user expertise."""
    base = """你是一个专业的MRO工业品推荐顾问。根据用户需求和搜索到的SKU结果，简洁直接地推荐产品。

要求：
- 直接列出最匹配的产品（最多5个），说明关键规格差异和推荐理由
- 如果搜索结果与用户需求有偏差，诚实说明
- 回复简洁，不要冗长开场白
- 不要编造不存在的产品信息"""

    if "级别：专家" in memory_context or "expert" in memory_context:
        base += "\n- 用户是采购专家，使用技术术语，直接给参数对比，无需解释基础知识"
    elif "级别：新手" in memory_context or "novice" in memory_context:
        base += "\n- 用户是采购新手，推荐时简要说明每种产品的适用场景，帮助其理解选择依据"

    return base


async def generate_response_stream(
    user_message: str,
    sku_results: list[dict],
    conversation_context: list[dict] | None = None,
    query_type: str = "",
    inferred_need: str = "",
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    sku_text = format_skus_for_prompt(sku_results)

    system_prompt = _build_system_prompt(memory_context)
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_context:
        messages.extend(conversation_context)

    # For application-type queries, prepend expert reasoning
    expert_reasoning = ""
    if query_type == "application" and inferred_need:
        expert_reasoning = f"\n\n专家判断：{inferred_need}"

    prompt = f"""用户需求：{user_message}{expert_reasoning}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

请根据以上搜索结果为用户推荐合适的产品。{"如果是用途场景查询，先一句话说明您的推断依据，再列出推荐产品。" if query_type == "application" else ""}"""

    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=2048,
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def generate_broad_response_stream(
    user_message: str,
    sku_results: list[dict],
    clarification_question: str,
    conversation_context: list[dict] | None = None,
    query_type: str = "",
    inferred_need: str = "",
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """Generate response for broad/vague requests: show results AND guide user to refine."""
    sku_text = format_skus_for_prompt(sku_results)

    is_novice = "级别：新手" in memory_context or "novice" in memory_context
    is_expert = "级别：专家" in memory_context or "expert" in memory_context

    if query_type == "application":
        guidance = """用户描述的是使用场景，你需要：
1. 先用一句话说出你作为采购顾问的专业判断（用户需要什么产品及原因）
2. 展示已搜索到的相关产品，简要分组介绍
3. 最后提出关键追问参数，帮助精确匹配"""
    elif is_novice:
        guidance = """用户是采购新手，需求比较宽泛，你需要：
1. 先用通俗语言介绍搜索到的产品有哪几种类型
2. 说明每种类型的典型使用场景，帮助用户理解
3. 引导用户回答关键参数以精确筛选"""
    else:
        guidance = """用户的需求比较宽泛，你需要：
1. 先展示已找到的产品概况，从搜索结果中按规格/材质分组
2. 直接提出需要补充的关键参数"""

    system_content = f"""你是一个资深MRO采购顾问。{guidance}

语气要专业友好。不要编造不存在的产品信息，只基于提供的搜索结果推荐。"""

    if is_expert:
        system_content += "\n用户是采购专家，使用技术术语，直接给参数对比。"

    messages = [{"role": "system", "content": system_content}]
    if conversation_context:
        messages.extend(conversation_context)

    inferred_line = f"\n\n专家判断：{inferred_need}" if inferred_need else ""
    prompt = f"""用户需求：{user_message}{inferred_line}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

需要进一步了解：{clarification_question}

请按要求组织回复。"""

    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=2048,
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def generate_clarification_stream(
    user_message: str,
    clarification_question: str,
    conversation_context: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    messages = [
        {"role": "system", "content": "你是一个专业友好的MRO工业品顾问，帮助用户找到合适的产品。"}
    ]
    if conversation_context:
        messages.extend(conversation_context)

    prompt = f"""用户说："{user_message}"

你需要追问以下信息来更精确地搜索产品：{clarification_question}

请用自然、友好的语气向用户追问，同时展示你的专业性。简洁回复，不超过3-4句话。"""

    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=512,
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def generate_no_results_stream(
    user_message: str,
    parsed_intent: dict,
    alternatives: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    # Build parsed params summary
    keywords = parsed_intent.get("keywords") or []
    spec_keywords = parsed_intent.get("spec_keywords") or []
    brand = parsed_intent.get("brand") or ""
    l2 = parsed_intent.get("l2_category") or ""
    l3 = parsed_intent.get("l3_category") or ""

    params_parts = []
    if l2 or l3:
        params_parts.append(f"品类: {'/'.join(p for p in [l2, l3] if p)}")
    if keywords:
        params_parts.append(f"产品: {', '.join(keywords)}")
    if spec_keywords:
        params_parts.append(f"规格: {', '.join(spec_keywords)}")
    if brand:
        params_parts.append(f"品牌: {brand}")
    params_desc = "；".join(params_parts) if params_parts else "未能识别具体需求"

    if alternatives:
        alt_text = format_skus_for_prompt(alternatives)
        prompt = f"""用户搜索："{user_message}"

解析参数：{params_desc}

库中暂无完全匹配该规格的产品。以下是相近品类的产品，供参考选型：

{alt_text}

请：
1. 简要说明未能精确匹配的原因（规格不在库中、标准差异等）
2. 基于以上近似产品推荐1-3个最接近的选项，说明与用户需求的差异
3. 如有必要，建议用户提供替代规格或标准"""
    else:
        prompt = f"""用户搜索："{user_message}"

解析参数：{params_desc}

库中暂无匹配产品。请：
1. 简要列出以上解析参数，确认理解是否正确
2. 建议用户尝试相近规格或标准（如 M8×25 或 M8×35 替代 M8×30，DIN933 替代 DIN931 等）
3. 邀请用户提供更多信息"""

    messages = [
        {"role": "system", "content": "你是一个专业的MRO工业品顾问，擅长紧固件选型。回复简洁专业。"},
        {"role": "user", "content": prompt},
    ]

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=600,
        messages=messages,
        stream=True,
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


def format_skus_for_prompt(skus: list[dict]) -> str:
    lines = []
    for i, sku in enumerate(skus, 1):
        parts = [
            f"[{i}] 编码: {sku['item_code']}",
            f"    名称: {sku['item_name']}",
            f"    品牌: {sku.get('brand_name') or '未知'}",
            f"    分类: {sku.get('l2_category_name', '')}/{sku.get('l3_category_name', '')}/{sku.get('l4_category_name', '')}",
        ]
        if sku.get("specification"):
            parts.append(f"    规格: {sku['specification']}")
        if sku.get("attribute_details"):
            attrs = sku["attribute_details"][:200]
            parts.append(f"    属性: {attrs}")
        # Append file type summary
        files = sku.get("files", [])
        if files:
            from collections import Counter
            type_counts = Counter(f["file_type_label"] for f in files)
            summary = ", ".join(f"{label}({cnt})" for label, cnt in type_counts.items())
            parts.append(f"    文件: {summary}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)
