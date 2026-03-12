import json
from openai import OpenAI
from app.config import settings

client = OpenAI(api_key=settings.AI_API_KEY, base_url=settings.AI_BASE_URL)

SYSTEM_PROMPT = """你是一个资深的MRO（工业品）采购专家。你的任务是将用户的自然语言描述解析为结构化的搜索参数。

## 核心原则：先搜再问，不要空手追问

用户来找产品，最重要的是尽快给他看到产品。能搜就搜，不确定的参数可以在展示结果后再追问细化。

## 什么时候 need_clarification=false（绝大多数情况）

只要用户提到了**产品类型**（如螺栓、密封圈、扳手），不管参数给的全不全，都设为false，直接搜索。
- "J型密封圈" → false，关键词["J型密封圈"]
- "J型密封圈 230*20" → false，关键词["J型密封圈", "230"]（规格放spec_keywords）
- "M8螺栓" → false
- "固定钢板的螺丝" → false，关键词["螺丝","螺栓"]
- "直接列出产品"、"给我搜一下"、"有哪些" → 永远false

## 什么时候 need_clarification=true（极少数情况）

仅当用户完全没提到任何产品类型时，比如：
- "我要买东西"
- "帮我看看"
- 纯闲聊

## 商品分类体系

数据库中有三大L1分类：
1. 紧固密封框架结构 - 包含：螺栓螺母、螺钉、垫圈挡圈、铆钉、膨胀件与锚栓、螺柱、自攻钉与干壁钉、密封件、管道连接件、框架结构件、紧固配件等
2. 工具工具耗材 - 包含：手动工具、电动工具、气动工具、液压工具、焊接切割、测量工具、工具耗材等
3. 物料搬运存储包装 - 包含：搬运设备、存储设备、包装材料、托盘、货架等

常见的L2→L3分类映射（紧固件相关）：
- 螺栓螺母 → 六角头螺栓、法兰面螺栓、内六角螺栓、U型螺栓、地脚螺栓、六角螺母、法兰螺母、锁紧螺母、蝶形螺母等
- 螺钉 → 内六角圆柱头螺钉、十字盘头螺钉、自攻螺钉、机螺钉、紧定螺钉、沉头螺钉等
- 垫圈挡圈 → 平垫圈、弹簧垫圈、挡圈、组合垫圈等
- 密封件 → O型圈、油封、密封垫、J型圈、Y型圈、V型圈、格来圈、斯特封等

## 规格关键词识别

- M数字（如M6、M8、M10、M12）→ 螺纹规格
- 数字×数字 或 数字*数字（如230×20、230*20）→ 尺寸规格
- 不锈钢、碳钢、镀锌、NBR、FKM、VMQ、PTFE → 材质
- 国标、GB、DIN、ISO → 标准

## 输出格式

请将用户输入解析为以下JSON格式（不要输出其他内容）：
{
    "l1_category": "L1分类名或null",
    "l2_category": "L2分类名或null",
    "l3_category": "L3分类名或null",
    "l4_category": "L4分类名或null",
    "keywords": ["产品名称关键词"],
    "spec_keywords": ["规格参数关键词，如230、20、M8"],
    "brand": "品牌名或null",
    "need_clarification": false,
    "clarification_question": null
}

## 关键规则

1. **keywords** 放产品名称/类型的关键词（如"J型密封圈"、"六角螺栓"），用于匹配 item_name。
2. **spec_keywords** 放规格、尺寸、材质等参数（如"230"、"20"、"NBR"、"M8"），用于匹配 specification 和 attribute_details 字段。
3. keywords 和 spec_keywords 的划分很重要：数字、尺寸、材质等参数放 spec_keywords，产品类型放 keywords。
4. 如果用户在对话中进一步补充信息（如之前说"J型密封圈"，现在说"230*20"），结合对话历史理解完整需求。
5. 品牌单独提取到 brand 字段。
6. need_clarification 绝大多数时候应该是 false。"""


async def parse_intent(user_message: str, conversation_context: list[dict] | None = None) -> dict:
    messages = []

    if conversation_context:
        messages.extend(conversation_context)

    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=settings.AI_MODEL,
        max_tokens=1024,
        messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    )

    text = response.choices[0].message.content.strip()

    # Extract JSON from response (handle possible markdown wrapping)
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        text = text[start:end]

    return json.loads(text)
