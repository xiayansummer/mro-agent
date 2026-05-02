# Slot-Chip Clarification + Search Robustness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the markdown 5-dim clarification table with structured chip cards (mirroring JD Industrial), and add brand-alias dictionary + brand-only fallback search to fix the multi-round brand-search bug (TOHO ↔ 美和).

**Architecture:** Backend `intent_parser` switches output schema from a `clarification_question` markdown string to a structured `slot_clarification` JSON ({summary, known, missing}). New SSE event of the same name streams the JSON to frontend. New React `SlotClarificationCard` renders chips with tag-pill input. Search robustness handled by `data/*.json` config + LLM-prompt injection + post-parse safety-net normalization. Brand-only queries hit a new `search_brand_clusters` function that runs `GROUP BY l3_category_name` directly on the DB.

**Tech Stack:** FastAPI / SQLAlchemy async / MySQL (via `app.db.mysql.AsyncSessionLocal`) / pytest / React + TypeScript + Vite / SSE streaming.

**Spec:** `docs/superpowers/specs/2026-05-01-slot-chip-clarification-design.md` (commit `cb07112`)

---

## File Structure

### Backend (Python)

**Created:**
- `backend/data/brand_aliases.json` — canonical brand → aliases map
- `backend/data/category_synonyms.json` — synonym → standard L1/L2 map
- `backend/app/services/normalization.py` — load + safety-net normalize functions (≤80 lines)
- `backend/migrations/003_add_slot_clarification.sql` — DB schema migration
- `backend/tests/test_normalization.py` — unit tests

**Modified:**
- `backend/app/services/intent_parser.py` — drop `clarification_question` from output schema, add `slot_clarification`, system-prompt updates for slot rules + brand/category examples, post-parse normalize call
- `backend/app/services/sku_search.py` — add `search_brand_clusters(session, brand)` returning `[(l3_name, count)]`
- `backend/app/services/agent.py` — brand-only fallback branch; emit `slot_clarification` SSE event; multi-round counter
- `backend/app/services/response_gen.py` — simplify `generate_guided_selection_stream`, remove markdown-table injection
- `backend/app/services/chat_history_service.py` — persist + load `slot_clarification` column; auto-mark prior message `submitted=true`
- `backend/app/routers/chat.py` — capture `slot_clarification` SSE event for persistence

### Frontend (TypeScript / React)

**Created:**
- `frontend/src/components/SlotClarificationCard.tsx` — chip card component (≤200 lines)

**Modified:**
- `frontend/src/types/index.ts` — `SlotClarification`, `SlotMissing` types added to `ChatMessage`
- `frontend/src/services/api.ts` — `onSlotClarification` callback in `SSECallbacks`; parse new event
- `frontend/src/components/ChatWindow.tsx` — wire `onSlotClarification`; submit-from-card flow
- `frontend/src/components/MessageBubble.tsx` — render `SlotClarificationCard` when `message.slotClarification` set
- `frontend/src/services/chatHistory.ts` — pass through `slotClarification` field on session detail load

---

## Phase 1: Brand/Category Data + Safety-Net Normalization

### Task 1: Create brand alias data file

**Files:**
- Create: `backend/data/brand_aliases.json`

- [ ] **Step 1: Create the JSON file**

```json
{
  "美和": ["TOHO", "美和TOHO", "美和toho", "TOHO美和", "东星"],
  "NOK": ["耐欧凯", "恩欧凯", "nok"],
  "SKF": ["斯凯孚", "skf"],
  "Festo": ["费斯托", "festo"],
  "SMC": ["速码客", "smc"],
  "Parker": ["派克", "parker"],
  "科德宝": ["Freudenberg", "freudenberg", "科德宝"],
  "博世": ["BOSCH", "bosch", "Bosch"],
  "施耐德": ["Schneider", "schneider"],
  "西门子": ["Siemens", "siemens", "SIEMENS"]
}
```

Note: the canonical (key) form must match how the brand is stored in `t_item_sample.brand_name`. Verify against DB if uncertain. The list above covers the highest-traffic 10 brands; expand based on user feedback.

- [ ] **Step 2: Commit**

```bash
git add backend/data/brand_aliases.json
git commit -m "feat: add brand alias data file"
```

---

### Task 2: Create category synonym data file

**Files:**
- Create: `backend/data/category_synonyms.json`

- [ ] **Step 1: Create the JSON file**

```json
{
  "搬运": "物料搬运 存储包装",
  "搬运产品": "物料搬运 存储包装",
  "起重": "起重工具及设备",
  "紧固": "紧固密封 框架结构",
  "工具": "工具 工具耗材",
  "存储": "物料搬运 存储包装",
  "密封": "紧固密封 框架结构"
}
```

Values must match L1 names from `intent_parser.py` system prompt (the L1 list at line ~26).

- [ ] **Step 2: Commit**

```bash
git add backend/data/category_synonyms.json
git commit -m "feat: add category synonym data file"
```

---

### Task 3: Normalization module with TDD

**Files:**
- Create: `backend/app/services/normalization.py`
- Test: `backend/tests/test_normalization.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_normalization.py`:

```python
from app.services.normalization import (
    load_brand_aliases,
    load_category_synonyms,
    normalize_brand,
    normalize_category,
    build_brand_examples_prompt,
    build_category_examples_prompt,
)


def test_load_brand_aliases_returns_dict():
    aliases = load_brand_aliases()
    assert isinstance(aliases, dict)
    assert "美和" in aliases
    assert "TOHO" in aliases["美和"]


def test_normalize_brand_canonical_unchanged():
    assert normalize_brand("美和") == "美和"


def test_normalize_brand_alias_to_canonical():
    assert normalize_brand("TOHO") == "美和"
    assert normalize_brand("美和TOHO") == "美和"
    assert normalize_brand("toho") == "美和"  # case-insensitive


def test_normalize_brand_unknown_unchanged():
    assert normalize_brand("不存在的牌子") == "不存在的牌子"


def test_normalize_brand_none_returns_none():
    assert normalize_brand(None) is None
    assert normalize_brand("") == ""


def test_normalize_category_canonical_unchanged():
    assert normalize_category("物料搬运 存储包装") == "物料搬运 存储包装"


def test_normalize_category_synonym_mapped():
    assert normalize_category("搬运") == "物料搬运 存储包装"
    assert normalize_category("搬运产品") == "物料搬运 存储包装"


def test_normalize_category_no_substring_pollution():
    """'电动工具' must NOT become '电动工具 工具耗材' — substring danger zone."""
    # The function only matches whole-string equality, never substring
    assert normalize_category("电动工具") == "电动工具"
    assert normalize_category("我要搬运车") == "我要搬运车"


def test_brand_examples_prompt_contains_canonical_and_aliases():
    prompt = build_brand_examples_prompt()
    assert "美和" in prompt
    assert "TOHO" in prompt
    assert "→" in prompt or "←" in prompt


def test_category_examples_prompt_contains_synonyms():
    prompt = build_category_examples_prompt()
    assert "搬运" in prompt
    assert "物料搬运" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_normalization.py -v
```

Expected: ImportError or ModuleNotFoundError on `app.services.normalization`.

- [ ] **Step 3: Implement normalization.py**

Create `backend/app/services/normalization.py`:

```python
"""Brand and category name normalization.

Normalization is two-layered:
1. LLM prompt-level: aliases injected as examples so the LLM tends to
   output canonical names directly.
2. Field-level safety net: post-parse exact-match lookup on the LLM's
   extracted brand/category fields. NEVER apply to raw query text — that
   would risk substring corruption (e.g. "电动工具" → "电动工具耗材").
"""
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA_DIR = Path(__file__).parent.parent.parent / "data"


@lru_cache(maxsize=1)
def load_brand_aliases() -> dict[str, list[str]]:
    with (_DATA_DIR / "brand_aliases.json").open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def load_category_synonyms() -> dict[str, str]:
    with (_DATA_DIR / "category_synonyms.json").open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _build_alias_to_canonical() -> dict[str, str]:
    """Reverse map: lowercased alias → canonical brand."""
    out: dict[str, str] = {}
    for canonical, aliases in load_brand_aliases().items():
        out[canonical.lower()] = canonical
        for alias in aliases:
            out[alias.lower()] = canonical
    return out


def normalize_brand(brand: Optional[str]) -> Optional[str]:
    """Map any alias (case-insensitive, exact whole string) to the canonical brand."""
    if not brand:
        return brand
    return _build_alias_to_canonical().get(brand.lower(), brand)


def normalize_category(category: Optional[str]) -> Optional[str]:
    """Map a synonym (exact whole-string match) to standard L1/L2 name."""
    if not category:
        return category
    return load_category_synonyms().get(category, category)


def build_brand_examples_prompt() -> str:
    """Render the brand-alias section to inject into intent_parser system prompt."""
    lines = ["常见品牌别名（请直接输出标准名作为 brand 字段值）:"]
    for canonical, aliases in load_brand_aliases().items():
        if aliases:
            lines.append(f"- {canonical} ← {' / '.join(aliases)}")
    return "\n".join(lines)


def build_category_examples_prompt() -> str:
    """Render the category-synonym section to inject into intent_parser system prompt."""
    lines = ["常见品类同义（请直接归一到标准 L1/L2 名）:"]
    for syn, std in load_category_synonyms().items():
        lines.append(f"- {syn} → {std}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_normalization.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/normalization.py backend/tests/test_normalization.py
git commit -m "feat: add brand/category normalization module with safety-net lookup"
```

---

## Phase 2: intent_parser Schema Change

### Task 4: Update intent_parser system prompt

**Files:**
- Modify: `backend/app/services/intent_parser.py`

The current prompt at lines 319-380 has the 5-dim markdown table rules and lines 394-407 the JSON output schema. We need to:
1. Replace the 5-dim markdown table section with `slot_clarification` JSON spec.
2. Add the brand alias and category synonym example sections (rendered at module load).
3. Change the JSON output schema: drop `clarification_question` field, add `slot_clarification` field.

- [ ] **Step 1: Read existing prompt structure**

```bash
sed -n '315,410p' backend/app/services/intent_parser.py
```

Confirm the markdown-table section starts around line 319 and ends before the output schema near line 383.

- [ ] **Step 2: Replace the markdown-table section with slot_clarification rules**

Find the block starting with `## clarification_question 结构化追问规则（5字段框架）` and ending just before `## 用户专业程度自适应规则` (around line 369). Replace that entire block with:

```
## slot_clarification 结构化追问规则

当 need_clarification=true 时，你必须输出 slot_clarification 字段（一个 JSON 对象），用于驱动前端 chip 卡 UI。结构如下：

{
  "summary": "自然语言完整句，每轮重新生成，累积消化对话历史中已确认的所有信息",
  "known": [
    { "label": "中文字段名", "value": "已确认的值" }
  ],
  "missing": [
    {
      "key": "英文小写下划线（如 material / size_range / scenario）",
      "icon": "emoji（参考下方表）",
      "question": "中文问题（自然语言）",
      "options": ["选项1", "选项2", "选项3", "选项4"]
    }
  ]
}

字段细则：

**summary**：
- 必须是一句完整的中文自然语言（不是 bullet）
- 每轮根据完整 chat history 重新合成，把所有已确认参数都消化进去
- 例：第 1 轮 "需要采购 PVC 水管"；第 2 轮（已知场景=给水输送）变为 "需要采购给水输送场景的 50mm PVC 水管"

**known[]**：
- 列出**对话上下文中所有已确认的参数**（不只是本轮 user message）
- 包括用户最初输入提供的、和历次 chip 选择确认的字段
- {label, value} 形式，label 是中文字段名（如 "商品类型"、"规格"、"品牌"），value 是具体值
- 长度不限，1-N 视场景而定
- **品类切换规则**：仅当本轮 user message 提出与历史明确不同的新品类时，丢弃旧品类的衍生参数（保留通用维度如品牌、采购数量）

**missing[]**：
- 待补充维度，长度 2-4 个为佳
- key 由你自由命名，全小写下划线，简短英文（如 material / slip_level / size_range / scenario）
- icon 选 emoji，常用映射：
  - 🏭 应用场景 / 工业场景
  - ⚙️ 类型/连接方式/功能
  - 🔧 材质 / 工艺
  - 📏 尺寸 / 规格
  - 💧 介质 / 工况
  - 🏷️ 品牌
  - 📦 品类（用于 brand-only fallback）
- question 是中文自然语言问句
- options 是候选 chip 文本数组（3-5 个为佳），**纯品类/参数名，不带 (N) 等后缀**

**各 query_type 的侧重：**

- **broad_spec**（如"M8螺栓"）：known 列已知规格，missing 问缺失的 1-3 个维度
- **vague**（如"密封圈"）：known 几乎为空，missing 列出主流类型/材质等帮用户定位
- **application**（如"管道密封用什么"）：summary 用 inferred_need 表达推断，missing 问关键应用参数（介质/管径/工况）

**示例（query="50pvc水管"）：**

{
  "summary": "需要采购 PVC 水管",
  "known": [
    { "label": "商品类型", "value": "PVC水管" },
    { "label": "规格", "value": "50mm" }
  ],
  "missing": [
    {
      "key": "scenario",
      "icon": "🏭",
      "question": "用于什么场景？",
      "options": ["给水输送", "排水排污", "农业灌溉", "其他用途"]
    },
    {
      "key": "connection",
      "icon": "⚙️",
      "question": "需要哪种连接方式？",
      "options": ["承插式", "法兰连接", "螺纹连接", "卡箍连接"]
    },
    {
      "key": "length",
      "icon": "📏",
      "question": "管材长度？",
      "options": ["4米/根", "6米/根", "10米/根", "定制长度"]
    }
  ]
}
```

- [ ] **Step 3: Update the JSON output schema (drop clarification_question, add slot_clarification)**

Find the block (around line 394-407):

```
{
    "l1_category": "...",
    ...
    "need_clarification": false,
    "clarification_question": null,
    "attribute_gaps": [],
    "requirement_summary": null
}
```

Replace `"clarification_question": null,` with `"slot_clarification": null,`.

The schema should now end with:

```
{
    "l1_category": "紧固密封 框架结构 或 工具 工具耗材 或 物料搬运 存储包装 或null",
    "l2_category": "L2分类名或null",
    "l3_category": "L3分类名或null",
    "l4_category": null,
    "keywords": ["1-2个短词，实际出现在产品名称中"],
    "spec_keywords": ["规格/标准/材质/尺寸，如M8、40、DIN931、304、不锈钢"],
    "brand": "品牌名或null",
    "query_type": "precise | broad_spec | application | vague",
    "inferred_need": "专家推断一句话，或null",
    "need_clarification": false,
    "slot_clarification": null,
    "attribute_gaps": [],
    "requirement_summary": null
}
```

- [ ] **Step 4: Inject brand/category example prompts at module load**

At the top of `intent_parser.py`, after `from app.config import settings`, add:

```python
from app.services.normalization import (
    build_brand_examples_prompt,
    build_category_examples_prompt,
    normalize_brand,
    normalize_category,
)
```

Then, in the `SYSTEM_PROMPT` definition, add the rendered prompts. Find a clean insertion point (e.g. just before the `## slot_clarification 结构化追问规则` section) and append:

```python
SYSTEM_PROMPT = """你是一个资深的MRO（工业品）采购专家。你的任务是将用户的自然语言描述解析为结构化的搜索参数。
... (existing content) ...
""" + "\n\n" + build_brand_examples_prompt() + "\n\n" + build_category_examples_prompt()
```

(Concatenate them after the closing triple-quote so both reference data files inform the prompt.)

- [ ] **Step 5: Restart backend manually and confirm prompt loads**

```bash
cd backend && python -c "from app.services.intent_parser import SYSTEM_PROMPT; print('美和' in SYSTEM_PROMPT, '搬运' in SYSTEM_PROMPT)"
```

Expected: `True True`

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/intent_parser.py
git commit -m "feat(intent_parser): replace clarification_question markdown with slot_clarification JSON schema; inject brand/category alias examples"
```

---

### Task 5: Add post-parse safety-net normalization in intent_parser

**Files:**
- Modify: `backend/app/services/intent_parser.py` (the `parse_intent` function)

- [ ] **Step 1: Locate parse_intent**

```bash
grep -n "def parse_intent\|def _parse" backend/app/services/intent_parser.py
```

- [ ] **Step 2: Add safety-net normalization right before the function returns**

Find where `parse_intent` parses the LLM JSON response and returns the dict. Just before the `return parsed` line, add:

```python
    # Safety-net normalization (in case LLM output non-canonical names)
    parsed["brand"] = normalize_brand(parsed.get("brand"))
    parsed["l1_category"] = normalize_category(parsed.get("l1_category"))
    parsed["l2_category"] = normalize_category(parsed.get("l2_category"))
```

(Already imported at top in Task 4.)

- [ ] **Step 3: Verify by ad-hoc test**

Write a short verification script (do not commit it):

```bash
cd backend && python -c "
import asyncio
from app.services.intent_parser import parse_intent
async def t():
    r = await parse_intent('TOHO 葫芦 1吨', [], '', '')
    print('brand=', r.get('brand'))
asyncio.run(t())
"
```

Expected: `brand= 美和` (normalized from TOHO).

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/intent_parser.py
git commit -m "feat(intent_parser): post-parse safety-net normalize brand and L1/L2 category fields"
```

---

## Phase 3: Brand-only Fallback Search

### Task 6: Add search_brand_clusters to sku_search.py

**Files:**
- Modify: `backend/app/services/sku_search.py`
- Test: `backend/tests/test_brand_clusters.py` (create)

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_brand_clusters.py`:

```python
"""Tests the SQL building logic of search_brand_clusters.

We don't hit a real DB here — we mock AsyncSession and assert the SQL
shape and parameters. Real DB integration is verified manually during
Phase 8 deployment.
"""
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.services.sku_search import search_brand_clusters


@pytest.mark.asyncio
async def test_search_brand_clusters_groups_by_l3():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("手拉葫芦", 8),
        ("电动葫芦", 3),
        ("钢丝绳", 12),
    ]
    mock_session.execute.return_value = mock_result

    clusters = await search_brand_clusters(mock_session, "美和")

    # SQL must use GROUP BY (verified by inspecting the call)
    sql_text = str(mock_session.execute.call_args[0][0])
    assert "GROUP BY" in sql_text.upper()
    assert "ORDER BY" in sql_text.upper()
    assert "l3_category_name" in sql_text

    # Brand parameter should be passed
    params = mock_session.execute.call_args[0][1]
    assert params == {"brand": "美和"}

    # Returns list of (l3_name, count) tuples in order from DB
    assert clusters == [("手拉葫芦", 8), ("电动葫芦", 3), ("钢丝绳", 12)]


@pytest.mark.asyncio
async def test_search_brand_clusters_empty_brand_returns_empty():
    mock_session = AsyncMock()
    clusters = await search_brand_clusters(mock_session, "")
    assert clusters == []
    mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_search_brand_clusters_no_results():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result

    clusters = await search_brand_clusters(mock_session, "未知品牌")
    assert clusters == []
```

If `pytest-asyncio` isn't installed, add to `requirements.txt` and install:

```bash
echo "pytest-asyncio==0.23.0" >> backend/requirements.txt
cd backend && pip install pytest-asyncio==0.23.0
```

Also make sure `backend/tests/conftest.py` (if exists) has `asyncio_mode = "auto"` or use the `@pytest.mark.asyncio` decorator as shown.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && pytest tests/test_brand_clusters.py -v
```

Expected: ImportError on `search_brand_clusters`.

- [ ] **Step 3: Implement search_brand_clusters**

Add to `backend/app/services/sku_search.py` (at the end of the file):

```python
async def search_brand_clusters(
    session: AsyncSession,
    brand: str,
    limit: int = 10,
) -> list[tuple[str, int]]:
    """Brand-only fallback: return [(l3_category_name, sku_count), ...] for the brand.

    Performs DB-side GROUP BY to avoid LIMIT-truncation skew. The first
    sample of N rows could all belong to one L3, masking the brand's
    other categories — that's why we aggregate in SQL, not memory.
    """
    if not brand:
        return []
    result = await session.execute(
        text(
            """
            SELECT l3_category_name, COUNT(*) AS cnt
            FROM t_item_sample
            WHERE brand_name = :brand
              AND l3_category_name IS NOT NULL
            GROUP BY l3_category_name
            ORDER BY cnt DESC
            LIMIT :lim
            """
        ),
        {"brand": brand, "lim": limit},
    )
    return [(row[0], int(row[1])) for row in result.fetchall()]
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_brand_clusters.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/sku_search.py backend/tests/test_brand_clusters.py backend/requirements.txt
git commit -m "feat(sku_search): add search_brand_clusters for brand-only fallback"
```

---

## Phase 4: agent.py Orchestration

### Task 7: Wire brand-only fallback in agent.py

**Files:**
- Modify: `backend/app/services/agent.py`

- [ ] **Step 1: Add brand-only branch right after parse_intent**

Locate the place in `handle_message` where `parsed` has been set and `query_type` extracted (around line 71-72). After the existing `ctx["last_intent"] = parsed` line, add a brand-only fallback check:

```python
    # ── Brand-only fallback ────────────────────────────────────────────
    # If user gave only a brand and no category, list the brand's L3 categories
    # via DB GROUP BY and let the user pick via chip card.
    if (
        parsed.get("brand")
        and not parsed.get("l1_category")
        and not parsed.get("l2_category")
        and not parsed.get("l3_category")
        and parsed.get("query_type") in ("vague", "broad_spec")
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
                f"已为您整理 {parsed['brand']} 品牌的商品分布，请选择具体品类 ↑"
            ) + "\n\n"
            yield "event: done\ndata: \n\n"
            return
```

- [ ] **Step 2: Manually verify import is correct**

The function returns early, so the rest of `handle_message` is bypassed when brand-only fires. No other changes needed in this task.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent.py
git commit -m "feat(agent): brand-only fallback emits slot_clarification with L3 cluster chips"
```

---

### Task 8: Multi-round counter in agent.py

**Files:**
- Modify: `backend/app/services/agent.py`

- [ ] **Step 1: Add counter helper at top of file**

Right after the imports, add:

```python
from app.db.mysql import AsyncSessionLocal as _CounterSessionLocal
from sqlalchemy import text as _text


async def _slot_round_count(session_id: str) -> int:
    """Count prior assistant messages in this session that contained a slot_clarification."""
    async with _CounterSessionLocal() as s:
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
```

(The new column `slot_clarification` is added in Phase 5 / Task 11. The COUNT query will return 0 before that migration runs, which is correct behavior.)

- [ ] **Step 2: Use the counter to gate slot_clarification emission**

Find the existing `is_guided` block (around line 149-150). Currently:

```python
    is_guided = need_clarification and query_type == "vague"
```

Replace the downstream logic so that if `_slot_round_count(session_id) >= 3`, we **skip** any further `slot_clarification` emission and force a search instead. After the `is_guided` line, add:

```python
    rounds_so_far = await _slot_round_count(session_id)
    force_search = rounds_so_far >= 3
    if force_search:
        # 3-round hard cap: stop asking, search with whatever we have
        need_clarification = False
        is_guided = False
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent.py
git commit -m "feat(agent): enforce 3-round slot_clarification cap via DB counter"
```

---

### Task 9: Emit slot_clarification SSE event for normal need_clarification path

**Files:**
- Modify: `backend/app/services/agent.py`

- [ ] **Step 1: Locate the existing guided/clarification emission point**

Search for `generate_guided_selection_stream` calls in `agent.py`. The current flow yields the markdown table via that helper. We'll prepend a `slot_clarification` SSE event when the LLM output a `slot_clarification` field.

- [ ] **Step 2: Emit the event before the existing text stream**

Right before any call to `generate_guided_selection_stream` or `generate_clarification_stream`, add:

```python
    if parsed.get("slot_clarification") and not force_search:
        slot_payload = parsed["slot_clarification"]
        yield "event: slot_clarification\ndata: " + json.dumps(slot_payload, ensure_ascii=False) + "\n\n"
```

This should be placed inside the `is_guided or application_no_results` branch in `handle_message`, just before the loop that yields text from `generate_guided_selection_stream`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/agent.py
git commit -m "feat(agent): emit slot_clarification SSE event from intent_parser output"
```

---

### Task 10: Simplify response_gen.generate_guided_selection_stream

**Files:**
- Modify: `backend/app/services/response_gen.py`

The function currently injects the markdown clarification table verbatim (lines 168-169 and 187-189). Now that chip card rendering is taken over by the frontend, the function only needs to emit a short text leadership/intro line.

- [ ] **Step 1: Locate the function**

```bash
grep -n "def generate_guided_selection_stream" backend/app/services/response_gen.py
```

- [ ] **Step 2: Replace markdown injection with one-line guidance**

Find the implementation. Replace the body that builds `inferred_line + clarification_question + content` markdown with simply yielding a short text:

```python
async def generate_guided_selection_stream(
    user_message: str,
    parsed: dict,
    clarification_question: str = "",   # kept for backwards compat, unused
    *,
    inferred_need: str = "",
):
    """Now just emits a short intro line. Chip card UI takes over the actual display."""
    if inferred_need:
        yield f"event: text\ndata: {json.dumps(inferred_need)}\n\n"
        yield f"event: text\ndata: {json.dumps(chr(10) + chr(10))}\n\n"
    yield f"event: text\ndata: {json.dumps('已为您整理已知信息和待确认参数 ↑')}\n\n"
```

(`json.dumps(...)` ensures the SSE `data:` line is properly JSON-quoted, matching the existing SSE format. `chr(10)` = newline.)

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/response_gen.py
git commit -m "refactor(response_gen): drop markdown clarification table; chip card takes over"
```

---

## Phase 5: DB Migration + Chat History Persistence

### Task 11: Database migration

**Files:**
- Create: `backend/migrations/003_add_slot_clarification.sql`

- [ ] **Step 1: Verify MySQL version on prod**

```bash
ssh root@39.107.14.53 'mysql -h127.0.0.1 -P3307 -uroot -p"mymro@2026!" -e "SELECT VERSION();"'
```

Expected: 5.7+ (so JSON type is supported). If < 5.7, change column type to `MEDIUMTEXT` in the SQL below.

- [ ] **Step 2: Create migration file**

```sql
-- 003_add_slot_clarification.sql
-- Add slot_clarification JSON column to t_chat_message for chip card persistence.

ALTER TABLE t_chat_message
ADD COLUMN slot_clarification JSON NULL
AFTER competitor_results;
```

- [ ] **Step 3: Apply migration to local dev DB (if any) and prod**

```bash
ssh root@39.107.14.53 'mysql -h127.0.0.1 -P3307 -uroot -p"mymro@2026!" mro < -' < backend/migrations/003_add_slot_clarification.sql
```

Or via tunneled local mysql client if dev DB exists. Verify:

```bash
ssh root@39.107.14.53 'mysql -h127.0.0.1 -P3307 -uroot -p"mymro@2026!" mro -e "DESCRIBE t_chat_message;"'
```

Expected: a new `slot_clarification` row of type `json` is listed.

- [ ] **Step 4: Commit**

```bash
git add backend/migrations/003_add_slot_clarification.sql
git commit -m "feat(db): add t_chat_message.slot_clarification JSON column"
```

---

### Task 12: chat_history_service persist + load slot_clarification

**Files:**
- Modify: `backend/app/services/chat_history_service.py`

- [ ] **Step 1: Add slot_clarification to save_turn signature and INSERT**

Modify `save_turn` (around line 130). Add a new parameter `slot_clarification: Optional[dict] = None` after `competitor_results`:

```python
async def save_turn(
    session_id: str,
    user_id: str,
    user_message: str,
    image_b64: str,
    assistant_text: str,
    sku_results: Optional[list],
    competitor_results: Optional[list],
    slot_clarification: Optional[dict] = None,
) -> None:
```

In the assistant-message INSERT (around line 186-197), expand to include `slot_clarification`:

```python
            await s.execute(
                text(
                    "INSERT INTO t_chat_message (session_id, role, content, sku_results, competitor_results, slot_clarification) "
                    "VALUES (:sid, 'assistant', :content, :sku, :comp, :slot)"
                ),
                {
                    "sid": session_id,
                    "content": assistant_text,
                    "sku": json.dumps(sku_results, ensure_ascii=False) if sku_results else None,
                    "comp": json.dumps(competitor_results, ensure_ascii=False) if competitor_results else None,
                    "slot": json.dumps(slot_clarification, ensure_ascii=False) if slot_clarification else None,
                },
            )
```

- [ ] **Step 2: Mark prior slot_clarification as submitted when a new user message arrives**

In `save_turn`, after the user-message INSERT but before the assistant INSERT, add a step that auto-flips the most recent prior assistant `slot_clarification.submitted` to `true`:

```python
            # Auto-mark the prior slot_clarification (if any) as submitted —
            # the user has effectively answered by sending this new message.
            await s.execute(
                text(
                    "UPDATE t_chat_message "
                    "SET slot_clarification = JSON_SET(slot_clarification, '$.submitted', CAST('true' AS JSON)) "
                    "WHERE session_id = :sid "
                    "AND role = 'assistant' "
                    "AND slot_clarification IS NOT NULL "
                    "AND JSON_EXTRACT(slot_clarification, '$.submitted') IS NULL "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"sid": session_id},
            )
```

- [ ] **Step 3: Update get_session to read slot_clarification**

In `get_session` (around line 68-72), expand the SELECT and the row-to-message conversion (around line 79):

```python
        msgs_r = await s.execute(
            text(
                "SELECT id, role, content, image_data, sku_results, competitor_results, slot_clarification "
                "FROM t_chat_message WHERE session_id = :sid ORDER BY id"
            ),
            {"sid": session_id},
        )
        messages = []
        for m in msgs_r.fetchall():
            sku_results = json.loads(m[4]) if m[4] else None
            comp_results = json.loads(m[5]) if m[5] else None
            slot_clar = json.loads(m[6]) if m[6] else None
            messages.append({
                "id": str(m[0]),
                "role": m[1],
                "content": m[2],
                "imageUrl": m[3],
                "skuResults": sku_results,
                "competitorResults": comp_results,
                "slotClarification": slot_clar,
            })
```

(Adapt the existing dict-build to add the new field. The loop body already lives at lines ~75-95; show the field added in same style.)

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/chat_history_service.py
git commit -m "feat(chat_history): persist + load slot_clarification, auto-mark prior submitted"
```

---

### Task 13: Capture slot_clarification SSE event in routers/chat.py

**Files:**
- Modify: `backend/app/routers/chat.py`

The existing `_capturing_stream` accumulates `text`, `sku_results`, `competitor_results` from SSE events (lines 48-77). Add a fourth: `slot_clarification`.

- [ ] **Step 1: Add slot_clarification accumulator**

In `_capturing_stream` (around line 48), add `slot_clarification: Optional[dict] = None` to the local vars at the top of the function. Inside the SSE-parse loop (line 60-77), add a new branch:

```python
                    elif pending_event == "slot_clarification":
                        try:
                            slot_clarification = json.loads(data)
                        except Exception:
                            pass
```

In the `finally` block (line 78-92), pass it to `save_turn`:

```python
        asyncio.ensure_future(
            chat_history_service.save_turn(
                session_id=session_id,
                user_id=user_id,
                user_message=user_message,
                image_b64=image_b64,
                assistant_text=assistant_text,
                sku_results=sku_results,
                competitor_results=competitor_results,
                slot_clarification=slot_clarification,
            )
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/chat.py
git commit -m "feat(chat router): capture slot_clarification SSE event for persistence"
```

---

## Phase 6: Frontend Types + Chip Card Component

### Task 14: Add SlotClarification types

**Files:**
- Modify: `frontend/src/types/index.ts`

- [ ] **Step 1: Add types**

At the end of the file (after existing exports), add:

```typescript
export interface SlotMissing {
  key: string;
  icon: string;
  question: string;
  options: string[];
}

export interface SlotKnown {
  label: string;
  value: string;
}

export interface SlotClarification {
  summary: string;
  known: SlotKnown[];
  missing: SlotMissing[];
  submitted?: boolean;  // server sets to true after the user has answered
}
```

Then, in the existing `ChatMessage` interface (currently around line 31-40), add a new optional field:

```typescript
export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;
  skuResults?: SkuItem[];
  competitorResults?: CompetitorItem[];
  isStreaming?: boolean;
  thinkingStatus?: string;
  slotClarification?: SlotClarification;   // <-- add this line
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/types/index.ts
git commit -m "feat(types): add SlotClarification, SlotMissing, SlotKnown types"
```

---

### Task 15: SlotClarificationCard component

**Files:**
- Create: `frontend/src/components/SlotClarificationCard.tsx`

- [ ] **Step 1: Create the component**

```tsx
import { useState } from "react";
import { SlotClarification } from "../types";

interface Props {
  slot: SlotClarification;
  disabled?: boolean;       // true when submitted (read-only)
  onSubmit: (composedText: string) => void;
}

/** Strip trailing "(N)" count suffix from chip text before submission. */
function cleanChipText(s: string): string {
  return s.replace(/\s*\(\d+\)$/, "");
}

export default function SlotClarificationCard({ slot, disabled = false, onSubmit }: Props) {
  // selected: { dimension key → chosen option text }
  const [selected, setSelected] = useState<Record<string, string>>({});
  const [freeText, setFreeText] = useState("");

  const isLocked = disabled || !!slot.submitted;

  const handleChipClick = (dimKey: string, option: string) => {
    if (isLocked) return;
    setSelected(prev => {
      // Same-dim single select: if clicking the already-selected, deselect; else replace
      if (prev[dimKey] === option) {
        const next = { ...prev };
        delete next[dimKey];
        return next;
      }
      return { ...prev, [dimKey]: option };
    });
  };

  const handleRemoveTag = (dimKey: string) => {
    if (isLocked) return;
    setSelected(prev => {
      const next = { ...prev };
      delete next[dimKey];
      return next;
    });
  };

  const handleSubmit = () => {
    if (isLocked) return;
    const tagTexts = Object.values(selected).map(cleanChipText);
    const composed = [...tagTexts, freeText.trim()].filter(Boolean).join(" ");
    if (!composed) return;
    onSubmit(composed);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  const cardStyle: React.CSSProperties = {
    background: "var(--surface)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: 14,
    fontSize: 14,
    opacity: isLocked ? 0.85 : 1,
  };

  const chipBase: React.CSSProperties = {
    display: "inline-block",
    padding: "5px 12px",
    margin: "3px 6px 3px 0",
    borderRadius: 16,
    border: "1px solid var(--border)",
    fontSize: 13,
    cursor: isLocked ? "default" : "pointer",
    userSelect: "none",
    background: "transparent",
    color: "var(--text-primary)",
    transition: "all 0.15s",
  };

  const chipSelected: React.CSSProperties = {
    ...chipBase,
    background: "rgba(124, 58, 237, 0.15)",
    borderColor: "var(--accent, #7c3aed)",
    color: "var(--accent, #7c3aed)",
    fontWeight: 500,
  };

  const tagPill: React.CSSProperties = {
    display: "inline-flex",
    alignItems: "center",
    gap: 4,
    padding: "3px 6px 3px 10px",
    margin: "2px 4px 2px 0",
    borderRadius: 14,
    background: "rgba(124, 58, 237, 0.12)",
    color: "var(--accent, #7c3aed)",
    fontSize: 12,
  };

  return (
    <div style={cardStyle}>
      {/* Summary */}
      <div style={{ marginBottom: 8 }}>
        <span style={{ fontWeight: 600 }}>需求概述: </span>
        <span>{slot.summary}</span>
      </div>

      {/* Known params */}
      {slot.known.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>已知参数:</div>
          <ul style={{ margin: 0, paddingLeft: 20, color: "var(--text-secondary)" }}>
            {slot.known.map((k, i) => (
              <li key={i}>
                <span style={{ color: "var(--text-muted)" }}>{k.label}: </span>
                <span>{k.value}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Missing dimensions: each as chip group */}
      {slot.missing.map(dim => (
        <div key={dim.key} style={{ marginBottom: 10 }}>
          <div style={{ marginBottom: 4 }}>
            <span style={{ marginRight: 6 }}>{dim.icon}</span>
            <span>{dim.question}</span>
          </div>
          <div>
            {dim.options.map(opt => (
              <span
                key={opt}
                style={selected[dim.key] === opt ? chipSelected : chipBase}
                onClick={() => handleChipClick(dim.key, opt)}
              >
                {opt}
              </span>
            ))}
          </div>
        </div>
      ))}

      {/* Tag pill area + input — only when not locked */}
      {!isLocked && (
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10, marginTop: 8 }}>
          {Object.keys(selected).length > 0 && (
            <div style={{ marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: "var(--text-muted)", marginRight: 6 }}>已选:</span>
              {Object.entries(selected).map(([key, val]) => (
                <span key={key} style={tagPill}>
                  {cleanChipText(val)}
                  <button
                    onClick={() => handleRemoveTag(key)}
                    style={{
                      background: "none", border: "none", color: "inherit",
                      cursor: "pointer", padding: "0 4px", fontSize: 14,
                    }}
                    aria-label="移除"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={freeText}
              onChange={e => setFreeText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="自由补充（如长度 50mm、急用…）"
              style={{
                flex: 1,
                padding: "6px 10px",
                border: "1px solid var(--border)",
                borderRadius: 6,
                background: "var(--bg)",
                color: "var(--text-primary)",
                fontSize: 13,
                outline: "none",
              }}
            />
            <button
              onClick={handleSubmit}
              disabled={Object.keys(selected).length === 0 && !freeText.trim()}
              style={{
                padding: "6px 14px",
                border: "none",
                borderRadius: 6,
                background: "var(--accent, #7c3aed)",
                color: "#fff",
                cursor: "pointer",
                fontSize: 13,
                opacity: (Object.keys(selected).length === 0 && !freeText.trim()) ? 0.5 : 1,
              }}
            >
              提交
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/SlotClarificationCard.tsx
git commit -m "feat(frontend): add SlotClarificationCard chip card component"
```

---

## Phase 7: Frontend Wiring

### Task 16: Add onSlotClarification SSE callback in api.ts

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: Add to SSECallbacks interface**

In the `SSECallbacks` interface (around line 31-38), add:

```typescript
export interface SSECallbacks {
  onText: (text: string) => void;
  onSkuResults: (results: SkuItem[]) => void;
  onCompetitorResults: (results: CompetitorItem[]) => void;
  onSlotClarification: (slot: SlotClarification) => void;   // <-- new
  onThinking: (msg: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}
```

Add `SlotClarification` to imports at top of file:

```typescript
import { SkuItem, CompetitorItem, SlotClarification } from "../types";
```

- [ ] **Step 2: Handle the new event in the SSE switch**

In `handleEvent` (around line 78-112), add a new case:

```typescript
      case "slot_clarification":
        try {
          callbacks.onSlotClarification(JSON.parse(data));
        } catch (e) {
          console.error("Failed to parse slot_clarification:", e);
        }
        break;
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/api.ts
git commit -m "feat(api): add onSlotClarification SSE callback"
```

---

### Task 17: Wire onSlotClarification in ChatWindow.tsx

**Files:**
- Modify: `frontend/src/components/ChatWindow.tsx`

- [ ] **Step 1: Add the callback handler**

In `handleSend` (around line 59-100), find the `onSkuResults` callback and add a parallel `onSlotClarification`:

```typescript
        onSlotClarification: (slot) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, slotClarification: slot } : m
          );
          updateMessages(next);
        },
```

- [ ] **Step 2: Add a way for cards to submit back into the conversation**

The chip card's `onSubmit(composedText)` callback needs to trigger a new send. Add a method on `ChatWindow` that can be called by cards:

The simplest way: pass `handleSend` down to `MessageBubble`, which passes it to `SlotClarificationCard`. Add a prop on `MessageBubble`:

```typescript
// In MessageBubble.tsx Props (Task 18 will add it):
onChipSubmit?: (text: string) => void;
```

For ChatWindow.tsx, modify the JSX render of `<MessageBubble>` to pass:

```tsx
<MessageBubble
  key={msg.id}
  message={msg}
  isFirst={i === 0}
  sessionId={sessionId}
  onChipSubmit={(text) => handleSend(text)}
/>
```

(Find the existing `<MessageBubble>` in ChatWindow's return JSX.)

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ChatWindow.tsx
git commit -m "feat(ChatWindow): wire onSlotClarification + chip submit callback"
```

---

### Task 18: Render SlotClarificationCard in MessageBubble.tsx

**Files:**
- Modify: `frontend/src/components/MessageBubble.tsx`

- [ ] **Step 1: Add prop + import**

At the top of the file:

```typescript
import SlotClarificationCard from "./SlotClarificationCard";
```

Update Props interface (around line 7-11):

```typescript
interface Props {
  message: ChatMessage;
  isFirst?: boolean;
  sessionId?: string;
  onChipSubmit?: (text: string) => void;
}
```

Update function signature:

```typescript
export default function MessageBubble({ message, isFirst, sessionId, onChipSubmit }: Props) {
```

- [ ] **Step 2: Render SlotClarificationCard above text content**

In the assistant-message JSX (after line 67 `// Assistant message`), find the section that renders SKU results / competitor results / text content. Add a new conditional block right BEFORE the SKU results block:

```tsx
        {/* Slot clarification chip card */}
        {message.slotClarification && (
          <div style={{ marginBottom: 12 }}>
            <SlotClarificationCard
              slot={message.slotClarification}
              disabled={!!message.slotClarification.submitted}
              onSubmit={(text) => onChipSubmit?.(text)}
            />
          </div>
        )}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/MessageBubble.tsx
git commit -m "feat(MessageBubble): render SlotClarificationCard when present"
```

---

### Task 19: Pass slotClarification through chatHistory.ts

**Files:**
- Modify: `frontend/src/services/chatHistory.ts`

- [ ] **Step 1: Update detailToSession**

In `detailToSession` (around line 63-70), the message mapping should preserve `slotClarification`:

```typescript
export function detailToSession(d: SessionDetail): ChatSession {
  return {
    id: d.id,
    title: d.title,
    createdAt: d.createdAt,
    messages: d.messages.map(m => ({
      ...m,
      isStreaming: false,
      slotClarification: (m as any).slotClarification,
    })),
  };
}
```

(The `(m as any)` is used because the server returns it but the existing `ChatMessage` type derived from API may not yet match. Cast safely since server-side dictates the field.)

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/chatHistory.ts
git commit -m "feat(chatHistory): preserve slotClarification on session load"
```

---

## Phase 8: Verification + Deployment

### Task 20: Local end-to-end smoke test

**Files:**
- (None modified — this is verification only)

- [ ] **Step 1: Build frontend**

```bash
cd frontend && npm run build
```

Expected: build succeeds, no TypeScript errors.

- [ ] **Step 2: Start backend locally (or via docker)**

```bash
cd backend && docker compose up -d backend
docker compose logs -f backend &
```

Wait for "Application startup complete".

- [ ] **Step 3: Test PVC pipe scenario**

In a browser, open `http://localhost:3000` (or prod URL after deploy), log in, and send: `50pvc水管`

Expected:
- A chip card appears with "需求概述: 需要采购 PVC 水管", known: [商品类型: PVC水管, 规格: 50mm], and 2-3 missing dimensions (场景 / 连接方式 / 长度)
- Click "给水输送" → tag pill appears in the input area
- Click "承插式" → second tag pill appears
- Type "急用 5 根" in free text input
- Press Enter → composed message "给水输送 承插式 急用 5 根" is sent as next user message

- [ ] **Step 4: Test brand-only fallback**

Send: `美和`

Expected:
- A chip card appears: "美和品牌下找到 N 类商品", known: [品牌: 美和], missing: [{品类 chips like "手拉葫芦 (8)", "电动葫芦 (3)", ...}]
- Click "手拉葫芦 (8)" + submit
- Next assistant message returns SKU results from 美和品牌的手拉葫芦
- The composed message must NOT contain "(8)" — only "手拉葫芦"

- [ ] **Step 5: Test alias normalization**

Send: `TOHO 葫芦 1吨`

Expected: SKU results return showing 美和/TOHO 手拉葫芦 products. (The alias TOHO was normalized to 美和 before search.)

- [ ] **Step 6: Test 3-round cap**

Send a series of vague queries forcing 3 chip rounds, e.g.:
1. `工具`
2. (click some chips, submit)
3. (click some chips, submit again — third assistant turn)
4. After the 4th user message, expect SKU search results, NOT another chip card

- [ ] **Step 7: Test page reload preserves submitted state**

After completing Step 3, refresh the page and re-open the conversation. The chip card from earlier should appear in read-only mode (no input box, chips not clickable).

- [ ] **Step 8: If all tests pass**

No commit. Move to Task 21.

---

### Task 21: Deploy to production

**Files:**
- (No file changes — deployment only)

- [ ] **Step 1: Push all commits**

```bash
git push origin main
```

- [ ] **Step 2: SSH to prod and pull + rebuild**

```bash
ssh root@39.107.14.53 'cd /root/mro-agent && git pull origin main && docker compose up -d --build --force-recreate'
```

- [ ] **Step 3: Confirm migration ran (if not auto)**

If the prod backend uses an explicit migration runner, confirm it picked up `003_add_slot_clarification.sql`. If migrations are manual:

```bash
ssh root@39.107.14.53 'mysql -h127.0.0.1 -P3307 -uroot -p"mymro@2026!" mro < /root/mro-agent/backend/migrations/003_add_slot_clarification.sql'
```

(May fail with "Duplicate column" if already applied in Task 11 Step 3 — that's safe to ignore.)

- [ ] **Step 4: Verify prod**

Browser: open `https://mro.fultek.ai`, log in, run the same 5 scenarios from Task 20.

- [ ] **Step 5: Monitor logs for errors during first hour**

```bash
ssh root@39.107.14.53 'cd /root/mro-agent && docker compose logs --tail=200 backend'
```

Watch for: `slot_clarification`, `normalize_brand`, JSON parse errors.

---

### Task 22: Document in repo + update memory

**Files:**
- Modify: `docs/产品手册.md`

- [ ] **Step 1: Add a brief section to product manual about chip追问**

Find the section in 产品手册.md that mentions clarification (probably under "智能对话" or similar). Add or update:

```markdown
### 参数追问 chip 卡

当系统对您的需求理解不充分时，会以 chip 卡的形式列出已知参数和待确认维度。您可以：
- 点击任意 chip 选项，被选中的项会以 tag 形式回显在卡片底部
- 同维度内单选（再点同一个会取消，点别的会替换）
- 在输入框补充自由文本（如"长度 50mm、急用 5 件"）
- 点击"提交"或按回车将所选 chip + 自由文本一起发送
```

- [ ] **Step 2: Rebuild PDF**

```bash
cd docs && python build_pdf.py
```

Verify `frontend/public/manual.pdf` is updated.

- [ ] **Step 3: Commit**

```bash
git add docs/产品手册.md frontend/public/manual.pdf
git commit -m "docs: document chip clarification card in product manual"
git push origin main
```

- [ ] **Step 4: Re-deploy to push manual update**

```bash
ssh root@39.107.14.53 'cd /root/mro-agent && git pull origin main && docker compose up -d --build frontend'
```

---

## Self-Review Checklist (executed before plan handoff)

| Spec section | Covered by |
|---|---|
| 4.1 Data contract (slot_clarification SSE) | Task 4, 9 |
| 4.2 Brand-only fallback payload | Task 7 |
| 4.3 Frontend ChatMessage type | Task 14 |
| 5.1-5.3 SlotClarificationCard UI + interactions | Task 15 |
| 6.1 brand_aliases.json | Task 1 |
| 6.2 category_synonyms.json | Task 2 |
| 6.3 intent_parser prompt + post-parse normalize | Task 4, 5 |
| 6.4 No agent.py preprocessing replace | Task 4, 5 (intent_parser handles it) |
| 6.5 search_brand_clusters DB GROUP BY | Task 6 |
| 7. Multi-round 3-cap | Task 8 |
| 8. DB migration JSON column | Task 11 |
| 9. Old markdown compat | Task 18 (renders only when slotClarification present, else falls through to existing markdown render) |
| 10. End-to-end data flow | Task 20 (smoke tests) |
| 12. Risk: LLM JSON malformed | Task 4 (post-parse safety net), 13 (silent skip if parse fails) |
| 12. Risk: substring corruption | Task 5 (no string.replace ever; only field-level lookup) |
| 12. Risk: (N) suffix pollution | Task 15 (cleanChipText regex strip) |

No placeholders found. Code samples are concrete. Type names are consistent across tasks. File paths are absolute.

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-01-slot-chip-clarification.md`.
