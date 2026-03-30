from collections.abc import AsyncGenerator
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.AI_API_KEY, base_url=settings.AI_BASE_URL)

def _build_system_prompt(memory_context: str = "", query_type: str = "") -> str:
    """Build response system prompt, optionally adjusted for user expertise and query type."""
    is_expert = "级别：专家" in memory_context or "expert" in memory_context
    is_novice = "级别：新手" in memory_context or "novice" in memory_context

    if query_type == "precise":
        base = """你是一个专业的MRO工业品推荐顾问，同时具备深厚的产品标准和规格知识。

回复结构（严格按此顺序，不加额外标题和开场白）：

**规格要点**（仅3-4条，针对用户查询的具体产品）
- 确认标准体系（如DIN/ISO/GB等效关系）
- 核心尺寸或参数（对边、螺距、厚度等本次查询直接相关的）
- 材质/等级含义（如A2-70、8.8级，一句话说清）

**推荐产品**（Markdown表格，最多5个）
| 编号 | 产品名称 | 关键规格 | 推荐理由 |
|------|---------|---------|---------|

**选型提示**（可选，只在有实质采购陷阱时输出，不超过2条）

要求：
- 规格要点每条一句话，不写段落，不超过4条
- 不编造不存在于搜索结果中的产品
- 表格单元格内严禁使用 <br> 或任何HTML标签
- 总回复控制在500字以内"""
        if is_expert:
            base += "\n- 用户是采购专家，省略规格要点，直接从推荐产品开始"

    elif query_type == "broad_spec":
        base = """你是一个专业的MRO工业品推荐顾问，同时具备深厚的产品标准和规格知识。

回复结构（严格按此顺序，追问部分由系统统一处理，你只输出前两块）：

**品类说明**（2-3条，说明该品类主要子类型的区别，每条一句话）

**推荐产品**（Markdown表格，从搜索结果中选最有代表性的，最多5个）
| 编号 | 产品名称 | 关键规格 | 推荐理由 |
|------|---------|---------|---------|

要求：
- 品类说明不写通用废话，只写有辨别价值的区别
- 不编造不存在于搜索结果中的产品
- 表格单元格内严禁使用 <br> 或任何HTML标签
- 输出到推荐产品表格结束即停止，不要输出任何追问内容
- 总回复控制在500字以内"""
        if is_expert:
            base += "\n- 用户是采购专家，省略品类说明，使用技术术语，直接给参数对比"

    else:
        # application, vague, and other types — original prompt
        base = """你是一个专业的MRO工业品推荐顾问。根据用户需求和搜索到的SKU结果，简洁直接地推荐产品。

要求：
- 直接列出最匹配的产品（最多5个），说明关键规格差异和推荐理由
- 如果搜索结果与用户需求有偏差，诚实说明
- 回复简洁，不要冗长开场白
- 不要编造不存在的产品信息
- 推荐产品列表请使用 Markdown 表格（用 | 分隔符），列出编号、产品名称、关键规格、推荐理由
- 表格单元格内严禁使用 <br> 或任何 HTML 标签，每个单元格只写纯文本，换行信息合并成一句话
- 表格外的补充说明用有序/无序列表"""
        if is_expert:
            base += "\n- 用户是采购专家，使用技术术语，直接给参数对比，无需解释基础知识"
        elif is_novice:
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

    system_prompt = _build_system_prompt(memory_context, query_type)
    messages = [{"role": "system", "content": system_prompt}]
    if conversation_context:
        messages.extend(conversation_context)

    # For application-type queries, prepend expert reasoning
    expert_reasoning = ""
    if query_type == "application" and inferred_need:
        expert_reasoning = f"\n\n专家判断：{inferred_need}"

    prompt = f"""用户需求：{user_message}{expert_reasoning}

搜索到 {len(sku_results)} 个相关产品（真实库存数据，请直接基于这些推荐）：
{sku_text}

请按系统提示的结构输出。规格要点只写与"{user_message}"直接相关的参数。"""

    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=1024,
        messages=messages,
        stream=True,
        extra_body={"enable_thinking": False},
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
    attribute_suggestions: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Generate response for broad/vague requests: show results AND guide user to refine."""
    sku_text = format_skus_for_prompt(sku_results)

    system_content = _build_system_prompt(memory_context, query_type="broad_spec")

    messages = [{"role": "system", "content": system_content}]
    if conversation_context:
        messages.extend(conversation_context)

    inferred_line = f"\n\n专家判断：{inferred_need}" if inferred_need else ""

    spec_range = ""
    if sku_results:
        specs = [s.get("specification", "") for s in sku_results if s.get("specification")]
        if len(specs) >= 2:
            spec_range = f"\n搜索结果规格范围：{', '.join(specs[:4])}"

    prompt = f"""用户需求：{user_message}{inferred_line}{spec_range}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

请按系统提示的结构输出（只输出品类说明和推荐产品，不要输出追问）。"""

    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=1000,
        messages=messages,
        stream=True,
        extra_body={"enable_thinking": False},
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content

    # Inject the 5-field clarification table directly (more reliable than LLM-generated)
    yield f"\n\n---\n\n**请确认以下参数，以便精准匹配：**\n\n{clarification_question}"


async def generate_guided_selection_stream(
    user_message: str,
    inferred_need: str,
    clarification_question: str,
    conversation_context: list[dict] | None = None,
    query_type: str = "",
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """
    三步选型流程的第一步：先识别产品类型，再提专业问题。
    不展示产品卡片，引导用户一步步确认需求。
    """
    is_novice = "级别：新手" in memory_context or "novice" in memory_context

    if query_type == "vague":
        # Directly stream the 5-field clarification table — no AI regeneration needed
        inferred_line = f"**初步判断**：{inferred_need}\n\n" if inferred_need else ""
        content = f"{inferred_line}请告诉我您的具体需求，以便精准推荐：\n\n{clarification_question}"
        yield content
        return

    elif is_novice:
        system = "你是专业MRO采购顾问。用户是采购新手，先用通俗语言确认他的需求方向，再用简单问题引导他提供关键参数。解释每个问题为什么重要。"
    else:
        system = "你是专业MRO采购顾问。先确认用户的产品需求类型，再提出专业的技术参数问题。"

    inferred_line = f"\n\n初步判断：{inferred_need}" if inferred_need else ""

    prompt = f"""用户描述："{user_message}"{inferred_line}

请按以下两步回复：

**第一步：识别确认**
用一段话告诉用户您判断他需要的是什么产品，以及理由（基于什么使用场景/用途）。用粗体标出产品类型名称。

**第二步：关键问题**
列出需要确认的关键参数，帮助最终确认产品规格：
{clarification_question}

要求：
- 问题用有序列表，每条后加括号说明影响什么选择
- 语气专业友好
- 不超过200字，不展示任何产品列表"""

    messages = [{"role": "system", "content": system}]
    if conversation_context:
        messages.extend(conversation_context)
    messages.append({"role": "user", "content": prompt})

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=600,
        messages=messages,
        stream=True,
        extra_body={"enable_thinking": False},
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
        extra_body={"enable_thinking": False},
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
        extra_body={"enable_thinking": False},
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content


async def generate_equivalent_stream(
    user_message: str,
    equivalent_results: list[dict],
    original_standard: str,
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
    """
    当库中无直接匹配但找到等效标准替代品时调用。
    输出五段产品知识卡片 + 等效产品推荐表格。
    """
    sku_text = format_skus_for_prompt(equivalent_results)

    system_content = f"""你是一个专业的MRO工业品顾问，擅长工业标准规范和产品选型。

用户搜索的 {original_standard} 在库中无直接库存，但找到了完全等效的替代产品。

请按以下结构输出（严格按顺序，不加额外开场白）：

## {original_standard} — 产品知识

**① 定义与标识**
（2-3句：该标准的类型定义、与其他标准的等效关系）

**② 主流材质与性能**
（每种材质一行：材质等级 — 力学性能 — 适用场景）

**③ 典型规格示例**
（该品类工业最常用规格范围，一句话）

**④ 选型和采购要点**
（2-3条实用采购注意事项，每条一句话）

**⑤ 常见误区**
（1-2条该类产品常见混淆点，每条一句话）

---
以下产品与您搜索的 {original_standard} 完全等效（真实库存）：

| 编号 | 产品名称 | 关键规格 | 说明 |
|------|---------|---------|------|

要求：
- 知识内容基于行业标准知识生成，准确简洁
- 产品表格只展示以下搜索结果中的真实产品，说明列统一写"≡ {original_standard}，可直接替代"
- 表格单元格内严禁 <br> 或任何 HTML 标签
- 总回复控制在 600 字以内"""

    is_expert = "级别：专家" in memory_context or "expert" in memory_context
    if is_expert:
        system_content += "\n- 用户是采购专家，省略知识卡片①②③，直接从④选型要点开始"

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": f"""用户需求：{user_message}

以下是找到的等效替代产品（真实库存）：
{sku_text}

请按系统提示结构输出产品知识卡片和等效推荐。"""},
    ]

    stream = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=1200,
        messages=messages,
        stream=True,
        extra_body={"enable_thinking": False},
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
