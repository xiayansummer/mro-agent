from collections.abc import AsyncGenerator
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.AI_API_KEY, base_url=settings.AI_BASE_URL)

SYSTEM_PROMPT = """你是一个专业的MRO工业品推荐顾问。根据用户需求和搜索到的SKU结果，为用户提供专业的产品推荐。

你的职责：
1. 从搜索结果中筛选最匹配用户需求的产品，按匹配度排序推荐
2. 用简洁专业的语言解释推荐理由
3. 指出各产品的关键差异（材质、规格、品牌等）
4. 如果搜索结果不太匹配用户需求，诚实告知并建议调整搜索条件

回复格式要求：
- 先用1-2句话概述搜索结果
- 然后列出推荐的产品（最多推荐5个最匹配的），每个产品说明推荐理由
- 最后给出选购建议或追问

注意：不要编造不存在的产品信息，只基于提供的搜索结果进行推荐。"""


async def generate_response_stream(
    user_message: str,
    sku_results: list[dict],
    conversation_context: list[dict] | None = None,
) -> AsyncGenerator[str, None]:
    sku_text = format_skus_for_prompt(sku_results)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if conversation_context:
        messages.extend(conversation_context)

    prompt = f"""用户需求：{user_message}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

请根据以上搜索结果为用户推荐合适的产品。"""

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
) -> AsyncGenerator[str, None]:
    """Generate response for broad/vague requests: show results AND guide user to refine."""
    sku_text = format_skus_for_prompt(sku_results)

    messages = [
        {
            "role": "system",
            "content": """你是一个专业的MRO工业品推荐顾问。用户的需求比较宽泛，你需要：

1. 先展示已找到的产品概况，让用户有一个整体印象
2. 从搜索结果中按不同类别/规格分组，帮用户快速了解有哪些选择
3. 在最后自然地引导用户进一步明确需求（如规格、材质、品牌偏好等），以便缩小范围

语气要专业友好，像一个有经验的采购顾问在帮客户选品。
不要编造不存在的产品信息，只基于提供的搜索结果进行推荐。""",
        }
    ]
    if conversation_context:
        messages.extend(conversation_context)

    prompt = f"""用户需求：{user_message}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

需要进一步了解的信息：{clarification_question}

请先概述搜索结果，推荐一些产品供参考，然后自然地引导用户明确需求以缩小范围。"""

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
) -> AsyncGenerator[str, None]:
    intent_desc = f"分类: {parsed_intent.get('l2_category', '未知')}/{parsed_intent.get('l3_category', '未知')}, 关键词: {parsed_intent.get('keywords', [])}"

    messages = [
        {"role": "system", "content": "你是一个专业友好的MRO工业品顾问。"},
        {
            "role": "user",
            "content": f'用户搜索 "{user_message}"，解析为 {intent_desc}，但没有找到匹配的产品。请友好地告知用户并建议调整搜索条件。简洁回复。',
        },
    ]

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
