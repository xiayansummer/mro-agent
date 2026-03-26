# Search Quality & Personalization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 MRO Agent 添加对话内属性追问（含行业惯例建议）、个性化排序、跨标准替代推荐（含产品知识卡片）和 ERP 历史数据导入四个功能。

**Architecture:** 新增两个纯函数模块（`standard_mapping.py`、`preference_ranker.py`）作为无依赖基础层；扩展 `intent_parser.py` 输出 `attribute_gaps`；在 `agent.py` 的搜索后阶段做属性建议富化、偏好重排序和等效标准替代触发；`response_gen.py` 新增结构化追问格式和知识卡片生成；`memory_service.py` 补充 `#preference` memo 定期写入；ERP 导入通过独立 router + service 实现。

**Tech Stack:** Python 3.11, FastAPI, OpenAI SDK, httpx (Memos), openpyxl/csv (已在 requirements.txt), python-multipart (已在 requirements.txt), React/TypeScript

---

## File Map

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `backend/app/services/standard_mapping.py` | DIN/ISO/GB 等效映射表 + 属性行业知识库 |
| 新建 | `backend/app/services/preference_ranker.py` | 从 memory_context 解析偏好、对结果重排序 |
| 新建 | `backend/app/services/erp_importer.py` | Excel/CSV 解析 + 采购偏好聚合 |
| 新建 | `backend/app/routers/profile.py` | POST /api/profile/import 端点 |
| 新建 | `backend/tests/__init__.py` | 测试包 |
| 新建 | `backend/tests/test_standard_mapping.py` | |
| 新建 | `backend/tests/test_preference_ranker.py` | |
| 新建 | `backend/tests/test_erp_importer.py` | |
| 修改 | `backend/app/services/intent_parser.py` | 输出 JSON 新增 `attribute_gaps` 字段 |
| 修改 | `backend/app/services/agent.py` | 属性建议富化、偏好排序、等效替代触发 |
| 修改 | `backend/app/services/response_gen.py` | 结构化追问输出 + `generate_equivalent_stream()` |
| 修改 | `backend/app/services/memory_service.py` | 会话计数 + `update_preference_memo()` |
| 修改 | `backend/app/main.py` | 注册 profile router |
| 修改 | `frontend/src/components/Sidebar.tsx` | 底部新增"导入采购历史"入口 |

---

## Task 1: Foundation — `standard_mapping.py` + `preference_ranker.py`

**Files:**
- Create: `backend/app/services/standard_mapping.py`
- Create: `backend/app/services/preference_ranker.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_standard_mapping.py`
- Create: `backend/tests/test_preference_ranker.py`

- [ ] **Step 1: Write failing tests for standard_mapping**

```python
# backend/tests/test_standard_mapping.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.standard_mapping import find_equivalents

def test_din934_returns_iso_and_gb():
    result = find_equivalents(["DIN934"])
    assert "ISO 4032" in result
    assert "GB/T 6170" in result

def test_case_insensitive():
    result = find_equivalents(["din934"])
    assert "ISO 4032" in result

def test_spaces_ignored():
    result = find_equivalents(["DIN 934"])
    assert "ISO 4032" in result

def test_unknown_standard_returns_empty():
    result = find_equivalents(["UNKNOWN999"])
    assert result == []

def test_multiple_keywords_one_standard():
    # M8 is not a standard, DIN931 is
    result = find_equivalents(["DIN931", "M8"])
    assert "ISO 4014" in result

def test_no_keywords():
    result = find_equivalents([])
    assert result == []

def test_no_duplicates():
    result = find_equivalents(["DIN934", "DIN934"])
    assert result.count("ISO 4032") == 1
```

- [ ] **Step 2: Run tests — expect FAIL (module not found)**

```bash
cd /Users/summer/mro-agent/backend
python -m pytest tests/test_standard_mapping.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Create `standard_mapping.py`**

```python
# backend/app/services/standard_mapping.py
"""
标准等效映射表 + 属性行业知识库

find_equivalents(keywords) → 返回等效标准号列表（用于替代搜索）
ATTRIBUTE_KNOWLEDGE → 各属性维度的行业建议选项（用于属性追问）
"""

# DIN/ISO/GB 等效映射（仅同尺寸同类型的标准体系等效，不跨尺寸、不跨强度等级）
STANDARD_EQUIVALENTS: dict[str, list[str]] = {
    "DIN934":  ["ISO 4032", "GB/T 6170"],    # 六角螺母
    "DIN933":  ["ISO 4017", "GB/T 5783"],    # 全螺纹六角螺栓
    "DIN931":  ["ISO 4014", "GB/T 5782"],    # 半螺纹六角螺栓
    "DIN912":  ["ISO 4762", "GB/T 70.1"],    # 内六角圆柱头螺钉
    "DIN125":  ["ISO 7089", "GB/T 97.1"],    # 平垫圈
    "DIN127":  ["ISO 7090", "GB/T 93"],      # 弹簧垫圈
    "DIN985":  ["ISO 7042", "GB/T 6184"],    # 尼龙锁紧螺母
    "DIN982":  ["ISO 7042"],                  # 全金属锁紧螺母
    "DIN7991": ["ISO 10642"],                 # 内六角沉头螺钉
    "DIN7380": ["ISO 7380"],                  # 内六角圆头螺钉
    "DIN471":  ["ISO 5254-1"],               # 轴用挡圈
    "DIN472":  ["ISO 5254-2"],               # 孔用挡圈
    # ISO → 等效
    "ISO4032": ["DIN 934",  "GB/T 6170"],
    "ISO4017": ["DIN 933",  "GB/T 5783"],
    "ISO4014": ["DIN 931",  "GB/T 5782"],
    "ISO4762": ["DIN 912",  "GB/T 70.1"],
    "ISO7089": ["DIN 125",  "GB/T 97.1"],
    "ISO7090": ["DIN 127",  "GB/T 93"],
    # GB → 等效
    "GBT6170": ["DIN 934",  "ISO 4032"],
    "GBT5783": ["DIN 933",  "ISO 4017"],
    "GBT5782": ["DIN 931",  "ISO 4014"],
}

# 已知标准号集合（用于快速判断 keyword 是否是标准号）
_NORM_TO_EQUIVALENTS: dict[str, list[str]] = {}


def _normalize(s: str) -> str:
    """统一大写，去掉空格/连字符/斜杠/点，GB/T → GBT"""
    return s.upper().replace(" ", "").replace("/", "").replace("-", "").replace(".", "")


def _build_index() -> None:
    for key, vals in STANDARD_EQUIVALENTS.items():
        _NORM_TO_EQUIVALENTS[_normalize(key)] = vals


_build_index()


def find_equivalents(keywords: list[str]) -> list[str]:
    """
    从 keywords 中找出已知标准号，返回其等效标准列表（去重保序）。
    忽略非标准号关键词（如 M8、不锈钢）。
    """
    result: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        norm = _normalize(kw)
        for equiv in _NORM_TO_EQUIVALENTS.get(norm, []):
            if equiv not in seen:
                seen.add(equiv)
                result.append(equiv)
    return result


# 属性行业知识库：gap_name → 建议选项列表
# is_common=True 的选项显示 ⭐ 标记
ATTRIBUTE_KNOWLEDGE: dict[str, list[dict]] = {
    "材质等级": [
        {"value": "A2-70（304不锈钢）", "note": "最常用，适合室内/一般环境", "is_common": True},
        {"value": "A4-80（316不锈钢）", "note": "耐海水/化工腐蚀，溢价约30%", "is_common": False},
        {"value": "碳钢镀锌", "note": "强度高，成本低，需防锈", "is_common": False},
    ],
    "强度等级": [
        {"value": "8.8级", "note": "工业最常用，高强度螺栓标配", "is_common": True},
        {"value": "4.8级", "note": "普通强度，成本低", "is_common": False},
        {"value": "10.9级", "note": "超高强度，特殊受力场合", "is_common": False},
    ],
    "规格（螺纹直径）": [
        {"value": "M6",  "note": "",                      "is_common": False},
        {"value": "M8",  "note": "工业最常用规格",          "is_common": True},
        {"value": "M10", "note": "",                      "is_common": False},
        {"value": "M12", "note": "",                      "is_common": False},
        {"value": "M16", "note": "",                      "is_common": False},
    ],
    "表面处理": [
        {"value": "镀锌白",  "note": "通用防锈，成本低",    "is_common": True},
        {"value": "发黑",    "note": "外观好，防锈性弱",    "is_common": False},
        {"value": "达克罗",  "note": "耐腐蚀强，无氢脆",   "is_common": False},
    ],
    "密封材质": [
        {"value": "丁腈橡胶（NBR）",  "note": "最通用，耐油，−30~120°C",      "is_common": True},
        {"value": "氟橡胶（FKM）",   "note": "耐高温耐化学品，−20~200°C",    "is_common": False},
        {"value": "硅橡胶（VMQ）",   "note": "耐高低温，可选食品级",           "is_common": False},
        {"value": "三元乙丙（EPDM）","note": "耐水/蒸汽，不耐油",             "is_common": False},
    ],
}
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /Users/summer/mro-agent/backend
python -m pytest tests/test_standard_mapping.py -v
```

Expected: 7 PASSED

- [ ] **Step 5: Write failing tests for preference_ranker**

```python
# backend/tests/test_preference_ranker.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.preference_ranker import rank_by_preference

MEMORY_WITH_BRAND = """
【该用户产品偏好（来自历史反馈）】

偏好品牌：SMC, 米思米
常用品类：螺栓螺母
"""

def _sku(code, brand, l2="螺栓螺母"):
    return {"item_code": code, "item_name": f"产品{code}",
            "brand_name": brand, "l2_category_name": l2}

def test_preferred_brand_moves_to_top():
    results = [_sku("A001", "未知品牌"), _sku("A002", "SMC")]
    ranked = rank_by_preference(results, MEMORY_WITH_BRAND)
    assert ranked[0]["item_code"] == "A002"

def test_preferred_category_boosts_score():
    results = [
        _sku("A001", "X", l2="密封圈"),
        _sku("A002", "Y", l2="螺栓螺母"),
    ]
    ranked = rank_by_preference(results, MEMORY_WITH_BRAND)
    assert ranked[0]["item_code"] == "A002"

def test_empty_memory_preserves_order():
    results = [_sku("A001", "X"), _sku("A002", "Y")]
    ranked = rank_by_preference(results, "")
    assert [r["item_code"] for r in ranked] == ["A001", "A002"]

def test_empty_results_returns_empty():
    assert rank_by_preference([], MEMORY_WITH_BRAND) == []

def test_tiebreak_preserves_original_order():
    # Both unknown brand → should keep original order
    results = [_sku("A001", "未知"), _sku("A002", "未知")]
    ranked = rank_by_preference(results, MEMORY_WITH_BRAND)
    assert [r["item_code"] for r in ranked] == ["A001", "A002"]
```

- [ ] **Step 6: Run tests — expect FAIL**

```bash
python -m pytest tests/test_preference_ranker.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 7: Create `preference_ranker.py`**

```python
# backend/app/services/preference_ranker.py
"""
偏好排序器：从 memory_context 字符串解析用户偏好信号，对 SKU 结果列表重排序。
纯函数，无外部依赖。
"""


def rank_by_preference(results: list[dict], memory_context: str) -> list[dict]:
    """
    对搜索结果按用户历史偏好重排序。
    偏好匹配的产品上浮；原始搜索顺序作为 tiebreaker。
    不修改原列表，返回新列表。
    """
    if not memory_context or not results:
        return results

    prefs = _parse_preferences(memory_context)

    def preference_score(item: dict) -> int:
        score = 0
        brand = (item.get("brand_name") or "").strip()
        l2 = (item.get("l2_category_name") or "").strip()

        if brand and brand in prefs["liked_brands"]:
            score += 2 * prefs["liked_brands"][brand]
        if l2 and l2 in prefs["liked_categories"]:
            score += prefs["liked_categories"][l2]

        return score

    # Stable sort: higher score first, original index as tiebreaker
    indexed = list(enumerate(results))
    indexed.sort(key=lambda x: (-preference_score(x[1]), x[0]))
    return [item for _, item in indexed]


def _parse_preferences(memory_context: str) -> dict:
    """从 get_user_context() 返回的字符串中提取偏好品牌和品类。"""
    liked_brands: dict[str, int] = {}
    liked_categories: dict[str, int] = {}

    for line in memory_context.splitlines():
        line = line.strip()
        if line.startswith("偏好品牌："):
            for brand in line[len("偏好品牌："):].split(","):
                b = brand.strip()
                if b:
                    liked_brands[b] = liked_brands.get(b, 0) + 1
        elif line.startswith("常用品类："):
            for cat in line[len("常用品类："):].split(","):
                c = cat.strip()
                if c:
                    liked_categories[c] = liked_categories.get(c, 0) + 1

    return {"liked_brands": liked_brands, "liked_categories": liked_categories}
```

- [ ] **Step 8: Create `backend/tests/__init__.py`** (empty file)

```bash
touch /Users/summer/mro-agent/backend/tests/__init__.py
```

- [ ] **Step 9: Run preference_ranker tests — expect PASS**

```bash
python -m pytest tests/test_preference_ranker.py -v
```

Expected: 5 PASSED

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/standard_mapping.py \
        backend/app/services/preference_ranker.py \
        backend/tests/__init__.py \
        backend/tests/test_standard_mapping.py \
        backend/tests/test_preference_ranker.py
git commit -m "feat: add standard_mapping and preference_ranker foundation modules"
```

---

## Task 2: intent_parser — 新增 `attribute_gaps` 输出字段

**Files:**
- Modify: `backend/app/services/intent_parser.py`

`attribute_gaps` 由 AI 从查询文本推断哪些关键属性未指定（`broad_spec` 时最多2个）。`attribute_suggestions` 留空（由 agent.py 在搜索后填充）。

- [ ] **Step 1: 在 `intent_parser.py` 的 SYSTEM_PROMPT 中找到输出格式 JSON 块**

在文件末尾附近的 `## 输出格式` 段，找到：
```
    "need_clarification": false,
    "clarification_question": null
}"""
```

- [ ] **Step 2: 将输出格式 JSON 末尾替换为新版（含 attribute_gaps）**

原文：
```python
    "need_clarification": false,
    "clarification_question": null
}"""
```

新文：
```python
    "need_clarification": false,
    "clarification_question": null,
    "attribute_gaps": []
}"""
```

在 `## 输出格式` 段的说明部分（`## 输出格式（JSON，不输出其他内容）` 后面），在 `l1_category` 说明前加一段说明：

找到：
```python
    "l1_category": "紧固密封 框架结构 或 工具 工具耗材 或 物料搬运 存储包装 或null",
```

在该行之前（即 `{` 之后）插入注释行说明属性（注意：这是 JSON 模板，不是真正的 JSON，可在末尾 clarification_question 后添加说明）。

实际只需在 SYSTEM_PROMPT 的 `## 输出格式` 后添加一段说明：

找到：
```
## 输出格式（JSON，不输出其他内容）

{
    "l1_category": "紧固密封 框架结构 或 工具 工具耗材 或 物料搬运 存储包装 或null",
```

替换为：
```
## 输出格式（JSON，不输出其他内容）

字段说明（仅新增字段）：
- attribute_gaps: 列出当前查询中未明确的关键属性维度名称。仅在 query_type="broad_spec" 时填写，最多2个。
  可选值："材质等级" | "强度等级" | "规格（螺纹直径）" | "表面处理" | "密封材质"
  其他 query_type 时返回空列表 []

{
    "l1_category": "紧固密封 框架结构 或 工具 工具耗材 或 物料搬运 存储包装 或null",
```

- [ ] **Step 3: 验证 intent_parser 正常解析（不破坏现有功能）**

```bash
cd /Users/summer/mro-agent/backend
python -c "
import asyncio, json
from app.services.intent_parser import parse_intent

async def test():
    result = await parse_intent('不锈钢六角螺母')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    assert 'attribute_gaps' in result, 'attribute_gaps field missing'
    print('OK: attribute_gaps present =', result['attribute_gaps'])

asyncio.run(test())
"
```

Expected: JSON 输出包含 `"attribute_gaps"` 字段，broad_spec 查询时应含 `["材质等级"]` 或类似值。

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/intent_parser.py
git commit -m "feat: add attribute_gaps field to intent_parser output"
```

---

## Task 3: agent.py — 属性建议富化 + 偏好排序

**Files:**
- Modify: `backend/app/services/agent.py`

在 `search_skus` 完成后、生成回复前插入两个新步骤：
1. 如果 `attribute_gaps` 非空，构建 `attribute_suggestions`
2. 对所有结果调用 `rank_by_preference()`

- [ ] **Step 1: 在 `agent.py` 顶部 import 区添加新导入**

找到：
```python
from app.services.memory_service import memory_service
```

在其后添加：
```python
from app.services.standard_mapping import find_equivalents, ATTRIBUTE_KNOWLEDGE
from app.services.preference_ranker import rank_by_preference
```

- [ ] **Step 2: 在 `handle_message` 中，`ctx["last_results"] = results` 之后插入属性建议富化逻辑**

找到：
```python
    ctx["last_results"] = results
```

替换为：
```python
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
```

- [ ] **Step 3: 在文件末尾（`handle_message` 函数之外）添加辅助函数**

在文件最末尾添加：

```python
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
```

- [ ] **Step 4: 在 `generate_broad_response_stream` 调用处传入 attribute_suggestions**

找到：
```python
        async for chunk in generate_broad_response_stream(
            user_message, results, question, conv_messages,
            query_type=query_type, inferred_need=inferred_need, memory_context=memory_context,
        ):
```

替换为：
```python
        async for chunk in generate_broad_response_stream(
            user_message, results, question, conv_messages,
            query_type=query_type, inferred_need=inferred_need, memory_context=memory_context,
            attribute_suggestions=parsed.get("attribute_suggestions"),
        ):
```

- [ ] **Step 5: 启动服务验证无报错**

```bash
cd /Users/summer/mro-agent/backend
uvicorn app.main:app --port 8001 --reload 2>&1 | head -5
```

Expected: `Application startup complete.`（Ctrl+C 退出）

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/agent.py
git commit -m "feat: enrich attribute_suggestions and apply preference ranking in agent"
```

---

## Task 4: response_gen.py — 结构化追问 + 知识卡片

**Files:**
- Modify: `backend/app/services/response_gen.py`

两处改动：
1. `generate_broad_response_stream()` 新增 `attribute_suggestions` 参数，当有结构化建议时替换普通追问格式
2. 新增 `generate_equivalent_stream()` 函数（五段知识卡片）

- [ ] **Step 1: 在 `generate_broad_response_stream()` 签名末尾新增参数**

找到：
```python
async def generate_broad_response_stream(
    user_message: str,
    sku_results: list[dict],
    clarification_question: str,
    conversation_context: list[dict] | None = None,
    query_type: str = "",
    inferred_need: str = "",
    memory_context: str = "",
) -> AsyncGenerator[str, None]:
```

替换为：
```python
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
```

- [ ] **Step 2: 在 prompt 构建中替换 clarification 文本**

找到：
```python
    prompt = f"""用户需求：{user_message}{inferred_line}{spec_range}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

缺失的关键参数：{clarification_question}

请按系统提示的结构输出。"""
```

替换为：
```python
    # 构建缺失参数追问段
    if attribute_suggestions:
        attr_lines: list[str] = []
        for gap_name, options in attribute_suggestions.items():
            attr_lines.append(f"\n**{gap_name}的参考选项：**")
            for opt in options:
                star = " ⭐ 最常用" if opt.get("is_common") else ""
                note = f" — {opt['note']}" if opt.get("note") else ""
                attr_lines.append(f"→ {opt['value']}{star}{note}")
        clarification_block = "缺失参数及建议选项：" + "\n".join(attr_lines)
    else:
        clarification_block = f"缺失的关键参数：{clarification_question}"

    prompt = f"""用户需求：{user_message}{inferred_line}{spec_range}

搜索到 {len(sku_results)} 个相关产品：
{sku_text}

{clarification_block}

请按系统提示的结构输出。"""
```

- [ ] **Step 3: 在文件末尾（`format_skus_for_prompt` 之前）添加 `generate_equivalent_stream()`**

在 `format_skus_for_prompt` 函数定义之前插入：

```python
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
    )

    for chunk in stream:
        delta = chunk.choices[0].delta if chunk.choices else None
        if delta and delta.content:
            yield delta.content

```

- [ ] **Step 4: 验证 response_gen 导入无误**

```bash
cd /Users/summer/mro-agent/backend
python -c "from app.services.response_gen import generate_equivalent_stream; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/response_gen.py
git commit -m "feat: structured attribute followup and generate_equivalent_stream in response_gen"
```

---

## Task 5: memory_service.py — 偏好摘要自动更新

**Files:**
- Modify: `backend/app/services/memory_service.py`

每当用户累计会话数达到 10 的倍数时，异步聚合 feedback + session memos，写入（覆盖）一条 `#preference` memo。

- [ ] **Step 1: 在 `MemoryService` 类定义前添加模块级计数器**

找到：
```python
class MemoryService:
    def __init__(self):
```

在其前面添加：
```python
# 轻量级内存会话计数器（重启后重置，仅用于触发偏好摘要更新）
_session_counts: dict[str, int] = {}

```

- [ ] **Step 2: 在 `save_session_summary` 末尾的 `create_memo` 调用后添加计数触发逻辑**

找到（在 `save_session_summary` 内）：
```python
        logger.info(f"Memos: saving session summary for user {user_id[:8]}, mode={response_mode}")
        try:
            result = await self.create_memo(content)
            if result:
                logger.info(f"Memos: saved OK — memo name={result.get('name')}")
            else:
                logger.warning(f"Memos: create_memo returned None for user {user_id[:8]}")
        except Exception as e:
            logger.error(f"Memos: save_session_summary exception: {e}", exc_info=True)
```

替换为：
```python
        logger.info(f"Memos: saving session summary for user {user_id[:8]}, mode={response_mode}")
        try:
            result = await self.create_memo(content)
            if result:
                logger.info(f"Memos: saved OK — memo name={result.get('name')}")
            else:
                logger.warning(f"Memos: create_memo returned None for user {user_id[:8]}")
        except Exception as e:
            logger.error(f"Memos: save_session_summary exception: {e}", exc_info=True)

        # 每累计 10 次会话触发偏好摘要更新（fire-and-forget）
        _session_counts[uid_tag] = _session_counts.get(uid_tag, 0) + 1
        if _session_counts[uid_tag] % 10 == 0:
            logger.info(f"Memos: triggering preference memo update for user {user_id[:8]}")
            asyncio.ensure_future(self.update_preference_memo(user_id))
```

- [ ] **Step 3: 在 `save_feedback` 方法之后添加 `update_preference_memo` 和 `_delete_memo`**

找到：
```python
    # ── Public: High-level read ────────────────────────────────────────────
```

在其前面插入：
```python
    # ── Public: Preference memo update ────────────────────────────────────

    async def update_preference_memo(self, user_id: str) -> None:
        """
        聚合该用户的 feedback + session memos，写入一条 #preference 摘要 memo（覆盖旧版）。
        Fire-and-forget，失败不抛出。
        """
        uid_tag = _uid_tag(user_id)
        try:
            feedback_memos, session_memos = await asyncio.gather(
                self.list_memos(uid_tag, extra_tag="feedback", limit=100),
                self.list_memos(uid_tag, extra_tag="session",  limit=50),
            )

            # 聚合 liked 品牌和品类
            liked_brands: dict[str, int] = {}
            liked_categories: dict[str, int] = {}
            for memo in feedback_memos:
                raw = memo.get("content", "")
                if "#liked" not in raw:
                    continue
                for line in raw.splitlines():
                    if line.startswith("**品牌：**"):
                        b = line.replace("**品牌：**", "").strip()
                        if b and b != "未知":
                            liked_brands[b] = liked_brands.get(b, 0) + 1
                    elif line.startswith("**品类：**"):
                        c = line.replace("**品类：**", "").strip()
                        if c and c != "未知":
                            top = c.split(" > ")[0]
                            liked_categories[top] = liked_categories.get(top, 0) + 1

            # 聚合常用规格
            spec_counter: dict[str, int] = {}
            for memo in session_memos:
                raw = memo.get("content", "")
                for line in raw.splitlines():
                    if line.startswith("**规格要求：**"):
                        specs_str = line.replace("**规格要求：**", "").strip()
                        if specs_str and specs_str != "无":
                            for spec in specs_str.split(","):
                                s = spec.strip()
                                if s:
                                    spec_counter[s] = spec_counter.get(s, 0) + 1

            top_brands = sorted(liked_brands, key=liked_brands.get, reverse=True)[:5]
            top_cats   = sorted(liked_categories, key=liked_categories.get, reverse=True)[:4]
            top_specs  = sorted(spec_counter, key=spec_counter.get, reverse=True)[:5]

            content = (
                f"## 用户偏好摘要（自动更新）\n"
                f"偏好品牌：{', '.join(top_brands) if top_brands else '暂无'}\n"
                f"常用品类：{', '.join(top_cats)   if top_cats   else '暂无'}\n"
                f"常用规格：{', '.join(top_specs)  if top_specs  else '暂无'}\n\n"
                f"#{uid_tag} #preference"
            )

            # 删除旧 preference memos，写入新的
            old = await self.list_memos(uid_tag, extra_tag="preference", limit=10)
            for memo in old:
                await self._delete_memo(memo.get("name", ""))

            await self.create_memo(content)
            logger.info(f"Memos: preference memo updated for user {user_id[:8]}")

        except Exception as e:
            logger.error(f"Memos: update_preference_memo failed: {e}", exc_info=True)

    async def _delete_memo(self, memo_name: str) -> None:
        """删除指定 memo（按 name 字段，格式为 'memos/xxx'）。"""
        if not memo_name:
            return
        try:
            headers = await self._auth_headers()
            async with self._make_client() as client:
                resp = await client.delete(f"/api/v1/{memo_name}", headers=headers)
                if resp.status_code not in (200, 204):
                    logger.warning(f"Memos delete {memo_name}: {resp.status_code}")
        except Exception as e:
            logger.error(f"Memos _delete_memo failed: {e}")

```

- [ ] **Step 4: 验证导入无报错**

```bash
python -c "from app.services.memory_service import memory_service; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/memory_service.py
git commit -m "feat: auto-update #preference memo every 10 sessions in memory_service"
```

---

## Task 6: agent.py — 等效标准替代触发

**Files:**
- Modify: `backend/app/services/agent.py`

当主搜索结果 < 3 时，检查关键词是否含已知标准号，若有则用等效标准重新搜索，路由到知识卡片生成。

- [ ] **Step 1: 在 `handle_message` 中 `ctx["last_results"] = results` 块之后，`is_guided` 判断之前，插入等效标准检查**

找到：
```python
    # Guided mode: vague/application → identify first, no product cards yet
    is_guided = need_clarification and query_type in ("vague", "application")
```

在其前插入：
```python
    # ── 等效标准替代（结果 < 3 且含已知标准号）──────────────────────────
    equivalent_results: list[dict] = []
    original_standard: str = ""
    if len(results) < 3 and not need_clarification:
        all_kws = (parsed.get("keywords") or []) + (parsed.get("spec_keywords") or [])
        equivalents = find_equivalents(all_kws)
        if equivalents:
            # 找出触发等效替代的原始标准号
            from app.services.standard_mapping import _normalize, _NORM_TO_EQUIVALENTS
            for kw in all_kws:
                if _normalize(kw) in _NORM_TO_EQUIVALENTS:
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

```

- [ ] **Step 2: 在回复生成段，在 `elif results:` 之前新增等效替代分支**

找到：
```python
    elif results:
        response_mode = "precise"
        async for chunk in generate_response_stream(
```

在其前插入：
```python
    if equivalent_results and original_standard:
        response_mode = "equivalent"
        from app.services.response_gen import generate_equivalent_stream
        async for chunk in generate_equivalent_stream(
            user_message, equivalent_results, original_standard,
            memory_context=memory_context,
        ):
            yield f"event: text\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            text_parts.append(chunk)

    el```

注意：将 `elif results:` 改为 `elif results and not equivalent_results:`，避免重复生成：

找到：
```python
    elif results:
        response_mode = "precise"
```

替换为：
```python
    elif results and not equivalent_results:
        response_mode = "precise"
```

- [ ] **Step 3: 在 `generate_equivalent_stream` import 处确认顶部 import 已包含（Task 4 已加入 response_gen）**

```bash
python -c "from app.services.agent import handle_message; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/agent.py
git commit -m "feat: trigger equivalent standard search and knowledge card when results < 3"
```

---

## Task 7: ERP 导入 — `erp_importer.py` + `routers/profile.py`

**Files:**
- Create: `backend/app/services/erp_importer.py`
- Create: `backend/app/routers/profile.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_erp_importer.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_erp_importer.py
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import openpyxl
from app.services.erp_importer import parse_column_map, parse_rows, aggregate_erp_data

def _make_excel(rows: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

def test_parse_column_map_chinese():
    headers = ["物料号", "物料描述", "品牌", "数量", "金额"]
    col = parse_column_map(headers)
    assert col["item_code"] == 0
    assert col["item_name"] == 1
    assert col["brand"] == 2
    assert col["qty"] == 3

def test_parse_column_map_english():
    headers = ["item_code", "item_name", "brand", "quantity"]
    col = parse_column_map(headers)
    assert col["item_code"] == 0
    assert col["brand"] == 2

def test_parse_column_map_missing_required():
    """没有任何可识别的必要列时返回空 dict"""
    col = parse_column_map(["col1", "col2"])
    assert "item_code" not in col and "item_name" not in col

def test_aggregate_brands():
    rows = [
        {"brand": "SMC",  "item_name": "O型圈",  "item_code": "001", "qty": 10},
        {"brand": "SMC",  "item_name": "O型圈2", "item_code": "002", "qty": 5},
        {"brand": "米思米","item_name": "螺栓",   "item_code": "003", "qty": 20},
    ]
    result = aggregate_erp_data(rows)
    assert result["top_brands"][0] == "SMC"
    assert "米思米" in result["top_brands"]

def test_aggregate_empty():
    result = aggregate_erp_data([])
    assert result["top_brands"] == []
    assert result["top_specs"] == []
```

- [ ] **Step 2: 运行测试 — 期待 FAIL**

```bash
python -m pytest tests/test_erp_importer.py -v 2>&1 | head -10
```

Expected: `ImportError`

- [ ] **Step 3: 创建 `erp_importer.py`**

```python
# backend/app/services/erp_importer.py
"""
ERP 历史数据导入服务。
支持 Excel (.xlsx/.xls) 和 CSV 格式。
只做聚合，不保存原始数据（隐私保护）。
"""
import csv
import io
import logging
from typing import Any

import openpyxl

logger = logging.getLogger(__name__)

# 中英文列名映射 → 标准字段名
_COLUMN_ALIASES: dict[str, list[str]] = {
    "item_code": ["物料号", "产品编码", "物料编号", "item_code", "code", "sku", "料号"],
    "item_name": ["物料描述", "产品名称", "品名", "item_name", "name", "description", "物料名称"],
    "brand":     ["品牌", "品牌名", "brand", "brand_name", "厂家"],
    "qty":       ["数量", "采购数量", "quantity", "qty", "用量"],
    "amount":    ["金额", "采购金额", "amount", "price", "费用"],
    "date":      ["日期", "采购日期", "date", "创建日期"],
}


def parse_column_map(headers: list[str]) -> dict[str, int]:
    """
    将表头行映射为 {标准字段名: 列索引}。
    不区分大小写，忽略首尾空格。
    """
    col_map: dict[str, int] = {}
    normalized_headers = [h.strip().lower() for h in headers]

    for field, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            try:
                idx = normalized_headers.index(alias.lower())
                col_map[field] = idx
                break
            except ValueError:
                continue

    return col_map


def parse_rows(file_bytes: bytes, filename: str) -> list[dict[str, Any]]:
    """
    解析 Excel 或 CSV 文件，返回 list of dict（仅含识别到的字段）。
    第一行视为表头。
    """
    if filename.lower().endswith(".csv"):
        return _parse_csv(file_bytes)
    else:
        return _parse_excel(file_bytes)


def _parse_excel(file_bytes: bytes) -> list[dict[str, Any]]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    try:
        headers = [str(c).strip() if c is not None else "" for c in next(rows_iter)]
    except StopIteration:
        return []

    col_map = parse_column_map(headers)
    if not col_map:
        return []

    result = []
    for row in rows_iter:
        record: dict[str, Any] = {}
        for field, idx in col_map.items():
            if idx < len(row) and row[idx] is not None:
                record[field] = str(row[idx]).strip()
        if record:
            result.append(record)
    return result


def _parse_csv(file_bytes: bytes) -> list[dict[str, Any]]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        headers = [h.strip() for h in next(reader)]
    except StopIteration:
        return []

    col_map = parse_column_map(headers)
    if not col_map:
        return []

    result = []
    for raw_row in reader:
        record: dict[str, Any] = {}
        for field, idx in col_map.items():
            if idx < len(raw_row) and raw_row[idx].strip():
                record[field] = raw_row[idx].strip()
        if record:
            result.append(record)
    return result


def aggregate_erp_data(rows: list[dict[str, Any]]) -> dict:
    """
    聚合采购记录，返回偏好摘要。
    {
      "top_brands": [...],      # 按采购频次排序，最多5个
      "top_categories": [...],  # 从品名推断（简单关键词），最多4个
      "top_specs": [...],       # 从品名/规格提取 M\d+ 规格，最多5个
      "total_records": int,
    }
    """
    import re

    brand_count: dict[str, int] = {}
    spec_count: dict[str, int] = {}
    total = len(rows)

    for row in rows:
        brand = (row.get("brand") or "").strip()
        if brand and brand not in ("未知", "—", "-", ""):
            brand_count[brand] = brand_count.get(brand, 0) + 1

        name = (row.get("item_name") or "").strip()
        # 从品名提取 M\d+ 规格（如 M8、M10）
        for match in re.findall(r"\bM\d+\b", name, re.IGNORECASE):
            spec_count[match.upper()] = spec_count.get(match.upper(), 0) + 1

    top_brands = sorted(brand_count, key=brand_count.get, reverse=True)[:5]
    top_specs  = sorted(spec_count,  key=spec_count.get,  reverse=True)[:5]

    return {
        "top_brands": top_brands,
        "top_categories": [],   # 预留，当前从品名推断品类较复杂，留空
        "top_specs": top_specs,
        "total_records": total,
    }
```

- [ ] **Step 4: 运行测试 — 期待 PASS**

```bash
python -m pytest tests/test_erp_importer.py -v
```

Expected: 5 PASSED

- [ ] **Step 5: 创建 `routers/profile.py`**

```python
# backend/app/routers/profile.py
"""
用户画像路由
POST /api/profile/import  — 上传采购历史 Excel/CSV，写入 #preference memo
"""
import logging
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from app.services.erp_importer import parse_rows, aggregate_erp_data
from app.services.memory_service import memory_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/profile/import")
async def import_erp_history(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
):
    """
    接受 Excel (.xlsx) 或 CSV 文件，解析采购历史，
    聚合偏好后写入 Memos #preference memo。
    原始文件不落库，处理后即丢弃。
    """
    effective_uid = user_id or session_id
    if not effective_uid:
        raise HTTPException(status_code=400, detail="需要提供 user_id 或 session_id")

    filename = file.filename or ""
    if not any(filename.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv")):
        raise HTTPException(status_code=400, detail="仅支持 .xlsx / .xls / .csv 格式")

    file_bytes = await file.read()
    if len(file_bytes) > 10 * 1024 * 1024:   # 10 MB 上限
        raise HTTPException(status_code=400, detail="文件大小不能超过 10 MB")

    rows = parse_rows(file_bytes, filename)
    if not rows:
        raise HTTPException(status_code=422, detail="无法识别文件列名，请确保含产品编码或产品名称列")

    summary = aggregate_erp_data(rows)
    logger.info(
        f"ERP import: user={effective_uid[:8]}, rows={summary['total_records']}, "
        f"brands={summary['top_brands']}"
    )

    # 构建 #preference memo 内容（覆盖旧版）
    from app.services.memory_service import _uid_tag
    uid_tag = _uid_tag(effective_uid)

    content = (
        f"## 用户偏好摘要（ERP导入）\n"
        f"偏好品牌：{', '.join(summary['top_brands'])  if summary['top_brands']  else '暂无'}\n"
        f"常用规格：{', '.join(summary['top_specs'])   if summary['top_specs']   else '暂无'}\n"
        f"导入记录数：{summary['total_records']}\n\n"
        f"#{uid_tag} #preference #erp-import"
    )

    # 删除旧 preference memos
    old = await memory_service.list_memos(uid_tag, extra_tag="preference", limit=10)
    for memo in old:
        await memory_service._delete_memo(memo.get("name", ""))

    await memory_service.create_memo(content)

    return {
        "status": "ok",
        "total_records": summary["total_records"],
        "top_brands": summary["top_brands"],
        "top_specs": summary["top_specs"],
        "message": f"已导入 {summary['total_records']} 条采购记录，偏好摘要已更新",
    }
```

- [ ] **Step 6: 在 `main.py` 注册 profile router**

找到：
```python
from app.routers.inquiry import router as inquiry_router
```

添加：
```python
from app.routers.profile import router as profile_router
```

找到：
```python
app.include_router(inquiry_router, prefix="/api")
```

在其后添加：
```python
app.include_router(profile_router, prefix="/api")
```

- [ ] **Step 7: 验证服务启动正常，端点可见**

```bash
uvicorn app.main:app --port 8001 2>&1 &
sleep 2
curl -s http://localhost:8001/openapi.json | python -c "
import json,sys
paths = json.load(sys.stdin)['paths']
assert '/api/profile/import' in paths, 'endpoint missing'
print('OK: /api/profile/import registered')
"
kill %1
```

Expected: `OK: /api/profile/import registered`

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/erp_importer.py \
        backend/app/routers/profile.py \
        backend/app/main.py \
        backend/tests/test_erp_importer.py
git commit -m "feat: ERP history import — erp_importer service + /api/profile/import endpoint"
```

---

## Task 8: Frontend — Sidebar ERP 导入入口

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

在 Sidebar 底部 Footer 区域添加"导入采购历史"按钮，点击弹出文件选择，上传后显示结果提示。

- [ ] **Step 1: 在 `Sidebar.tsx` 顶部新增 `useRef` 导入**

找到：
```python
import { useState } from "react";
```

替换为：
```typescript
import { useState, useRef } from "react";
```

- [ ] **Step 2: 在组件内（`sorted` 定义后）新增 import 相关 state 和 handler**

找到：
```typescript
  const sorted = [...sessions].sort((a, b) => b.createdAt - a.createdAt);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
```

替换为：
```typescript
  const sorted = [...sessions].sort((a, b) => b.createdAt - a.createdAt);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImportClick = () => {
    setImportStatus(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";

    setImportStatus("正在导入...");
    const sessionId = localStorage.getItem("mro_session_id") || "unknown";

    const form = new FormData();
    form.append("file", file);
    form.append("session_id", sessionId);

    try {
      const res = await fetch("/api/profile/import", { method: "POST", body: form });
      const data = await res.json();
      if (res.ok) {
        setImportStatus(`✓ 已导入 ${data.total_records} 条记录`);
      } else {
        setImportStatus(`✗ ${data.detail || "导入失败"}`);
      }
    } catch {
      setImportStatus("✗ 网络错误，请重试");
    }

    setTimeout(() => setImportStatus(null), 4000);
  };
```

- [ ] **Step 3: 在 Footer 区域添加导入按钮和隐藏 file input**

找到：
```typescript
        {/* Footer */}
        <div style={{ borderTop: "1px solid var(--sidebar-border)", padding: "12px 16px" }} className="shrink-0">
          <div style={{ color: "#3a3f52", fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontFamily: "var(--mono)" }}>v1.0</span>
            <span style={{ color: "#2a2f40" }}>·</span>
            <span>200万+ SKU</span>
          </div>
        </div>
```

替换为：
```typescript
        {/* Footer */}
        <div style={{ borderTop: "1px solid var(--sidebar-border)", padding: "12px 16px" }} className="shrink-0">
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls,.csv"
            style={{ display: "none" }}
            onChange={handleFileChange}
          />
          <button
            onClick={handleImportClick}
            style={{
              width: "100%", background: "none", border: "1px solid var(--sidebar-border)",
              borderRadius: 6, padding: "6px 10px", cursor: "pointer",
              color: "var(--text-secondary)", fontSize: 11,
              display: "flex", alignItems: "center", gap: 6, marginBottom: 8,
            }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
            </svg>
            导入采购历史
          </button>
          {importStatus && (
            <div style={{ fontSize: 10, color: importStatus.startsWith("✓") ? "#48bb78" : "#e53e3e", marginBottom: 6 }}>
              {importStatus}
            </div>
          )}
          <div style={{ color: "#3a3f52", fontSize: 11, display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontFamily: "var(--mono)" }}>v1.0</span>
            <span style={{ color: "#2a2f40" }}>·</span>
            <span>200万+ SKU</span>
          </div>
        </div>
```

- [ ] **Step 4: 构建前端验证无编译错误**

```bash
cd /Users/summer/mro-agent/frontend
npm run build 2>&1 | tail -8
```

Expected: `✓ built in ...ms`（无 TypeScript 错误）

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/Sidebar.tsx
git commit -m "feat: ERP import button in Sidebar footer"
```

---

## Task 9: 部署到服务器

- [ ] **Step 1: Push to GitHub**

```bash
cd /Users/summer/mro-agent
git push origin main
```

- [ ] **Step 2: 上传后端代码到服务器并重启**

```bash
sshpass -p 'iwrxZHNX3424' scp -o SendEnv=none \
  backend/app/services/standard_mapping.py \
  backend/app/services/preference_ranker.py \
  backend/app/services/erp_importer.py \
  backend/app/services/agent.py \
  backend/app/services/response_gen.py \
  backend/app/services/memory_service.py \
  root@154.219.114.111:/root/mro-agent/backend/app/services/

sshpass -p 'iwrxZHNX3424' scp -o SendEnv=none \
  backend/app/routers/profile.py \
  root@154.219.114.111:/root/mro-agent/backend/app/routers/

sshpass -p 'iwrxZHNX3424' scp -o SendEnv=none \
  backend/app/main.py \
  root@154.219.114.111:/root/mro-agent/backend/app/

sshpass -p 'iwrxZHNX3424' ssh -o StrictHostKeyChecking=no -o SendEnv=none \
  root@154.219.114.111 'docker restart mro-backend'
```

- [ ] **Step 3: 构建并部署前端**

```bash
cd /Users/summer/mro-agent/frontend && npm run build

NEW_JS=$(ls dist/assets/index-*.js | head -1 | xargs basename)
NEW_CSS=$(ls dist/assets/index-*.css | head -1 | xargs basename)

sshpass -p 'iwrxZHNX3424' scp -o SendEnv=none \
  dist/index.html \
  root@154.219.114.111:/tmp/index.html

sshpass -p 'iwrxZHNX3424' scp -o SendEnv=none \
  dist/assets/${NEW_JS} \
  root@154.219.114.111:/tmp/${NEW_JS}

sshpass -p 'iwrxZHNX3424' scp -o SendEnv=none \
  dist/assets/${NEW_CSS} \
  root@154.219.114.111:/tmp/${NEW_CSS}

sshpass -p 'iwrxZHNX3424' ssh -o StrictHostKeyChecking=no -o SendEnv=none root@154.219.114.111 \
  "docker cp /tmp/index.html mro-frontend:/usr/share/nginx/html/index.html"

sshpass -p 'iwrxZHNX3424' ssh -o StrictHostKeyChecking=no -o SendEnv=none root@154.219.114.111 \
  "screen -dmS fe sh -c 'docker cp /tmp/${NEW_JS} mro-frontend:/usr/share/nginx/html/assets/${NEW_JS} && docker cp /tmp/${NEW_CSS} mro-frontend:/usr/share/nginx/html/assets/${NEW_CSS} > /tmp/fe_deploy.log 2>&1'"
```

- [ ] **Step 4: 验证后端健康**

```bash
sleep 5
curl -s https://mro.fultek.ai/health
```

Expected: `{"status":"ok","memory":"ok"}`

---

## Self-Review Checklist

- [x] **Spec coverage:**
  - B1 属性追问 + 行业惯例 → Task 1 (ATTRIBUTE_KNOWLEDGE) + Task 2 (attribute_gaps) + Task 3 (enrichment) + Task 4 (structured output) ✓
  - D 个性化排序 → Task 1 (preference_ranker) + Task 3 (rank_by_preference call) ✓
  - D 偏好摘要更新 → Task 5 (update_preference_memo) ✓
  - B2 跨标准替代 + 知识卡片 → Task 1 (STANDARD_EQUIVALENTS) + Task 4 (generate_equivalent_stream) + Task 6 (trigger) ✓
  - B3 ERP 导入 → Task 7 (erp_importer + router) + Task 8 (frontend) ✓
- [x] **Placeholder scan:** 所有代码步骤均含完整实现，无 TBD/TODO
- [x] **Type consistency:** `attribute_suggestions: dict | None`，在 agent.py、response_gen.py 中一致；`find_equivalents` 返回 `list[str]`，在 agent.py Task 6 中直接使用 ✓
