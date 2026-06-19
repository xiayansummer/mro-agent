# 对话内比价结果精炼 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 识别"对已有比价结果的指令"(排序/取前N、品牌、价位、平台),在已采集 offers 上操作并新出结果消息,不重建比价。

**Architecture:** `handle_message` 在新建比价前插一条确定性早分支:`parse_refinement`(纯函数)命中 → `get_latest_session_offers` 取本会话最近结果 → `apply_refinement` 复用 ranker 原语过滤排序 → 新 SSE 事件 `refined_offers` → 前端复用 `OfferRow` 渲染。落 `t_chat_message.refined_offers` 新列可回看。

**Tech Stack:** FastAPI / SQLAlchemy(async, raw SQL via `text()`)/ MySQL / pytest + pytest-asyncio / React + Vite(TS)。

**Spec:** `docs/superpowers/specs/2026-06-19-comparison-result-refinement-design.md`

---

## 文件结构

| 动作 | 文件 | 职责 |
|---|---|---|
| 新建 | `backend/app/services/comparison_refine_service.py` | `parse_refinement`(纯)+ `apply_refinement`(纯)+ `build_label` |
| 新建 | `backend/tests/test_comparison_refine_service.py` | 上述纯函数测试 |
| 改 | `backend/app/services/comparison_task_service.py` | 加 `get_latest_session_offers` |
| 改 | `backend/tests/test_comparison_task_service.py` | 加 `get_latest_session_offers` 测试 |
| 改 | `backend/app/services/agent.py` | `handle_message` 加精炼早分支 |
| 改 | `backend/tests/test_chat_comparison_capture.py` | 加 handle_message 分支 + 捕获测试 |
| 新建 | `backend/migrations/007_add_refined_offers_to_chat_message.sql` | 加 `refined_offers` JSON 列 |
| 改 | `backend/app/routers/chat.py` | `_capturing_stream` 捕获 `refined_offers` |
| 改 | `backend/app/services/chat_history_service.py` | `save_turn` / `get_session` 加 `refined_offers` |
| 新建 | `frontend/src/components/OfferRow.tsx` | 从 `ComparisonTaskCard` 抽出的可复用单条 offer 行 |
| 新建 | `frontend/src/components/RefinedOffersCard.tsx` | 精炼结果卡片(复用 `OfferRow`) |
| 改 | `frontend/src/components/ComparisonTaskCard.tsx` | 改用抽出的 `OfferRow` |
| 改 | `frontend/src/services/api.ts` / `types/index.ts` / `components/ChatWindow.tsx` / `components/MessageBubble.tsx` | `onRefinedOffers` 事件 + `refinedOffers` 字段 + 渲染 |

---

## Task 1: `parse_refinement` 确定性解析(纯函数)

**Files:**
- Create: `backend/app/services/comparison_refine_service.py`
- Test: `backend/tests/test_comparison_refine_service.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_comparison_refine_service.py
from app.services.comparison_refine_service import parse_refinement


def test_sort_asc_with_topn_chinese_numeral():
    cmd = parse_refinement("能不能选出价格最低的五个")
    assert cmd is not None
    assert cmd["sort"] == "asc"
    assert cmd["limit"] == 5
    assert cmd["platform"] is None and cmd["brandKeep"] is None


def test_sort_asc_arabic_topn():
    cmd = parse_refinement("最便宜的3个")
    assert cmd["sort"] == "asc" and cmd["limit"] == 3


def test_sort_desc():
    cmd = parse_refinement("按价格从高到低排序")
    assert cmd["sort"] == "desc" and cmd["limit"] is None


def test_brand_keep():
    cmd = parse_refinement("只看3M")
    assert cmd["brandKeep"] == "3M" and cmd["brandDrop"] is None


def test_brand_drop():
    cmd = parse_refinement("排除霍尼韦尔")
    assert cmd["brandDrop"] == "霍尼韦尔"


def test_platform_drop_negation():
    cmd = parse_refinement("去掉震坤行的")   # 去掉 zkh = 只看 jd(仅两平台)
    assert cmd["platform"] == "jd"


def test_price_max():
    cmd = parse_refinement("50元以下的")
    assert cmd["priceMax"] == 50.0 and cmd["priceMin"] is None


def test_price_range():
    cmd = parse_refinement("20到50元之间")
    assert cmd["priceMin"] == 20.0 and cmd["priceMax"] == 50.0


def test_platform_filter():
    cmd = parse_refinement("只看京东工业品")
    assert cmd["platform"] == "jd"


def test_composition_platform_sort_limit():
    cmd = parse_refinement("京东上最便宜的3个")
    assert cmd["platform"] == "jd" and cmd["sort"] == "asc" and cmd["limit"] == 3


def test_label_present():
    cmd = parse_refinement("最便宜的5个")
    assert isinstance(cmd["label"], str) and cmd["label"]


# —— 否定样本:必须回落新品路径(None) ——
def test_new_product_plain_returns_none():
    assert parse_refinement("防尘口罩") is None


def test_new_product_with_brand_and_spec_returns_none():
    assert parse_refinement("美和2吨手拉葫芦") is None


def test_operator_plus_product_noun_returns_none():
    # "最便宜的电钻":含新商品名词残留 → 不劫持,回落新品
    assert parse_refinement("最便宜的电钻") is None


def test_empty_and_greeting_returns_none():
    assert parse_refinement("") is None
    assert parse_refinement("你好") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_comparison_refine_service.py -q`
Expected: FAIL（`ModuleNotFoundError` / `parse_refinement` 不存在）

- [ ] **Step 3: 实现 `parse_refinement`**

```python
# backend/app/services/comparison_refine_service.py
"""对话内"比价结果精炼":把对已有结果的指令解析成结构化操作,并在已采集 offers 上执行。

parse_refinement / apply_refinement 都是纯函数,无 IO,便于单测。
保守原则:只有明确命中精炼操作符、且去掉操作符后无新商品名词残留,才返回命令;
否则返回 None,由 handle_message 回落"新建比价"路径——绝不劫持新比价。
"""
import re
from typing import Optional

_CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

_ASC = ("最便宜", "价格最低", "最低价", "价格从低到高", "便宜的", "低价", "价低")
_DESC = ("最贵", "价格最高", "最高价", "价格从高到低", "贵的", "高价")
_PLATFORM = (("京东工业品", "jd"), ("京东", "jd"), ("jd", "jd"),
             ("震坤行", "zkh"), ("zkh", "zkh"))

# 去掉操作符后,残留里属于"命令/连接/数量"的词不算新商品名词
_STOP = ("能不能", "可不可以", "可以", "帮我", "帮", "请", "选出", "挑出", "挑", "给我",
         "只看", "只要", "要", "去掉", "排除", "不要", "除了", "前", "取", "留", "按",
         "排序", "排", "之间", "之内", "以内", "以下", "以上", "左右", "的", "个", "元",
         "块", "这些", "结果", "里", "中", "和", "与", "一下", "看看", "想", "我")

_NUM_RE = r"(\d+(?:\.\d+)?|[一两二三四五六七八九十]+)"


def _to_int(tok: str) -> Optional[int]:
    if tok.isdigit():
        return int(tok)
    if tok in _CN_NUM:
        return _CN_NUM[tok]
    # 简单两位中文(如 十五)不在 v1 范围;返回 None
    return None


def _to_float(tok: str) -> Optional[float]:
    try:
        return float(tok)
    except ValueError:
        n = _to_int(tok)
        return float(n) if n is not None else None


def parse_refinement(message: str) -> Optional[dict]:
    text = (message or "").strip()
    if not text:
        return None
    work = text
    cmd = {"platform": None, "brandKeep": None, "brandDrop": None,
           "priceMin": None, "priceMax": None, "sort": None, "limit": None, "label": ""}
    matched = False

    def strip(span: str):
        nonlocal work
        work = work.replace(span, " ", 1)

    # 平台(先判否定:"去掉/不要/排除 震坤行"=只看另一平台;仅两平台)
    _neg_plat = re.search(r"(去掉|不要|排除|除了)\s*(京东工业品|京东|震坤行)", work)
    if _neg_plat:
        cmd["platform"] = "zkh" if "京东" in _neg_plat.group(2) else "jd"
        strip(_neg_plat.group(0)); matched = True
    else:
        for kw, plat in _PLATFORM:
            if kw in work:
                cmd["platform"] = plat
                strip(kw)
                matched = True
                break

    # 价位:区间 / 上限 / 下限
    m = re.search(_NUM_RE + r"\s*[-到~至]\s*" + _NUM_RE + r"\s*元?", work)
    if m:
        a, b = _to_float(m.group(1)), _to_float(m.group(2))
        if a is not None and b is not None:
            cmd["priceMin"], cmd["priceMax"] = min(a, b), max(a, b)
            strip(m.group(0)); matched = True
    if cmd["priceMax"] is None:
        m = re.search(_NUM_RE + r"\s*元?\s*(以下|以内)|低于\s*" + _NUM_RE + r"|不超过\s*" + _NUM_RE, work)
        if m:
            tok = next((g for g in m.groups() if g), None)
            cmd["priceMax"] = _to_float(tok) if tok else None
            if cmd["priceMax"] is not None:
                strip(m.group(0)); matched = True
    if cmd["priceMin"] is None:
        m = re.search(_NUM_RE + r"\s*元?\s*以上|高于\s*" + _NUM_RE + r"|超过\s*" + _NUM_RE, work)
        if m:
            tok = next((g for g in m.groups() if g), None)
            cmd["priceMin"] = _to_float(tok) if tok else None
            if cmd["priceMin"] is not None:
                strip(m.group(0)); matched = True

    # 排序
    for kw in _ASC:
        if kw in work:
            cmd["sort"] = "asc"; strip(kw); matched = True; break
    if cmd["sort"] is None:
        for kw in _DESC:
            if kw in work:
                cmd["sort"] = "desc"; strip(kw); matched = True; break

    # 取前N: "前N(个)" 或 "N个"
    m = re.search(r"前\s*" + _NUM_RE + r"\s*个?|" + _NUM_RE + r"\s*个", work)
    if m:
        tok = next((g for g in m.groups() if g), None)
        n = _to_int(tok) if tok else None
        if n:
            cmd["limit"] = n; strip(m.group(0)); matched = True

    # 品牌:保留 / 剔除(平台已先消费,避免"只看京东"被当品牌)
    if cmd["brandKeep"] is None:
        m = re.search(r"(只看|只要|要)\s*([^\s,，。0-9]+?)(?:的|品牌)?(?:$|\s)", work)
        if m and m.group(2) not in {"", "京东", "震坤行"}:
            cmd["brandKeep"] = m.group(2); strip(m.group(0)); matched = True
    m = re.search(r"(去掉|排除|不要|除了)\s*([^\s,，。0-9]+)", work)
    if m and m.group(2):
        cmd["brandDrop"] = m.group(2); strip(m.group(0)); matched = True

    if not matched:
        return None

    # 保守残留检查:去掉操作符+品牌参数后,剩下若有"新商品名词"(≥2 连续 CJK 非停用词)→ None
    residue = work
    for w in _STOP:
        residue = residue.replace(w, " ")
    for b in (cmd["brandKeep"], cmd["brandDrop"]):
        if b:
            residue = residue.replace(b, " ")
    residue = re.sub(r"[0-9\.\-~到至,，。、!！?？:：\s]", "", residue)
    # 残留里若有连续 ≥2 个中文,视为新商品名词,放弃精炼(回落新品)
    if re.search(r"[一-鿿]{2,}", residue):
        return None

    cmd["label"] = build_label(cmd)
    return cmd
```

（`build_label` 在 Task 2 实现；本步可先放一个占位 `def build_label(cmd): return ""` 以便测试通过，Task 2 再替换。）

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_comparison_refine_service.py -q`
Expected: PASS（全部 14 个）。若个别否定样本未过,调 `_STOP`/正则直至全绿（否定样本是契约,**不可**放宽到误判新品）。

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/comparison_refine_service.py backend/tests/test_comparison_refine_service.py
git commit -m "feat(refine): parse_refinement 确定性解析精炼指令(纯函数)"
```

---

## Task 2: `apply_refinement` + `build_label`(纯函数)

**Files:**
- Modify: `backend/app/services/comparison_refine_service.py`
- Test: `backend/tests/test_comparison_refine_service.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_comparison_refine_service.py
from app.services.comparison_refine_service import apply_refinement, build_label

def _offers():
    return [
        {"id": "a", "platform": "jd",  "title": "3M 防尘口罩 9001", "brand": "3M",   "priceValue": 30.0, "unitComparable": True},
        {"id": "b", "platform": "jd",  "title": "霍尼韦尔 口罩",     "brand": "霍尼韦尔", "priceValue": 12.0, "unitComparable": True},
        {"id": "c", "platform": "zkh", "title": "3M 口罩 KN95",     "brand": "3M",   "priceValue": 45.0, "unitComparable": True},
        {"id": "d", "platform": "zkh", "title": "无名口罩",         "brand": None,   "priceValue": None, "unitComparable": False},
    ]

def test_apply_sort_asc_limit():
    cmd = {"platform": None, "brandKeep": None, "brandDrop": None, "priceMin": None,
           "priceMax": None, "sort": "asc", "limit": 2, "label": ""}
    out = apply_refinement(_offers(), cmd)
    assert [o["id"] for o in out] == ["b", "a"]   # 12 < 30,无价的 d 排末尾被 limit 截掉

def test_apply_platform_then_sort():
    cmd = {"platform": "jd", "brandKeep": None, "brandDrop": None, "priceMin": None,
           "priceMax": None, "sort": "asc", "limit": None, "label": ""}
    out = apply_refinement(_offers(), cmd)
    assert [o["id"] for o in out] == ["b", "a"]   # 只剩 jd 的 a,b,按价升序

def test_apply_brand_keep():
    cmd = {"platform": None, "brandKeep": "3M", "brandDrop": None, "priceMin": None,
           "priceMax": None, "sort": None, "limit": None, "label": ""}
    out = apply_refinement(_offers(), cmd)
    assert {o["id"] for o in out} == {"a", "c"}

def test_apply_price_max_excludes_none():
    cmd = {"platform": None, "brandKeep": None, "brandDrop": None, "priceMin": None,
           "priceMax": 40.0, "sort": None, "limit": None, "label": ""}
    out = apply_refinement(_offers(), cmd)
    assert {o["id"] for o in out} == {"a", "b"}   # ≤40,无价 d 被剔除

def test_apply_empty_result():
    cmd = {"platform": None, "brandKeep": "西门子", "brandDrop": None, "priceMin": None,
           "priceMax": None, "sort": None, "limit": None, "label": ""}
    assert apply_refinement(_offers(), cmd) == []

def test_build_label_composes():
    cmd = {"platform": "jd", "brandKeep": None, "brandDrop": None, "priceMin": None,
           "priceMax": 50.0, "sort": "asc", "limit": 3, "label": ""}
    label = build_label(cmd)
    assert "京东" in label and "50" in label and ("最低" in label or "便宜" in label)
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_comparison_refine_service.py -k "apply or build_label" -q`
Expected: FAIL（`apply_refinement` / `build_label` 未实现或为占位）

- [ ] **Step 3: 实现 `apply_refinement` + `build_label`**

```python
# 追加/替换到 comparison_refine_service.py(替换 Task1 的 build_label 占位)
from app.services.comparison_ranker import text_matches_brand

_PLAT_CN = {"jd": "京东工业品", "zkh": "震坤行"}


def _brand_text(offer: dict) -> str:
    return f"{offer.get('title') or ''} {offer.get('brand') or ''}"


def apply_refinement(offers: list[dict], cmd: dict) -> list[dict]:
    out = list(offers)
    if cmd.get("platform"):
        out = [o for o in out if o.get("platform") == cmd["platform"]]
    if cmd.get("brandKeep"):
        out = [o for o in out if text_matches_brand(_brand_text(o), cmd["brandKeep"])]
    if cmd.get("brandDrop"):
        out = [o for o in out if not text_matches_brand(_brand_text(o), cmd["brandDrop"])]
    if cmd.get("priceMax") is not None:
        out = [o for o in out if o.get("priceValue") is not None and o["priceValue"] <= cmd["priceMax"]]
    if cmd.get("priceMin") is not None:
        out = [o for o in out if o.get("priceValue") is not None and o["priceValue"] >= cmd["priceMin"]]
    if cmd.get("sort") in ("asc", "desc"):
        # 无价(None)统一排末尾;asc 升序、desc 降序
        big = float("inf")
        out.sort(key=lambda o: (o.get("priceValue") is None,
                                (o.get("priceValue") if o.get("priceValue") is not None else big)
                                * (1 if cmd["sort"] == "asc" else -1)))
    if cmd.get("limit"):
        out = out[: cmd["limit"]]
    return out


def build_label(cmd: dict) -> str:
    parts = []
    if cmd.get("platform"):
        parts.append(_PLAT_CN[cmd["platform"]])
    if cmd.get("brandKeep"):
        parts.append(f"只看{cmd['brandKeep']}")
    if cmd.get("brandDrop"):
        parts.append(f"去掉{cmd['brandDrop']}")
    if cmd.get("priceMin") is not None and cmd.get("priceMax") is not None:
        parts.append(f"{cmd['priceMin']:g}–{cmd['priceMax']:g}元")
    elif cmd.get("priceMax") is not None:
        parts.append(f"≤{cmd['priceMax']:g}元")
    elif cmd.get("priceMin") is not None:
        parts.append(f"≥{cmd['priceMin']:g}元")
    if cmd.get("sort") == "asc":
        parts.append("按价格最低" + (f"取前{cmd['limit']}" if cmd.get("limit") else "排序"))
    elif cmd.get("sort") == "desc":
        parts.append("按价格最高" + (f"取前{cmd['limit']}" if cmd.get("limit") else "排序"))
    elif cmd.get("limit"):
        parts.append(f"取前{cmd['limit']}")
    return "、".join(parts) or "筛选"
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_comparison_refine_service.py -q`
Expected: PASS（Task1 + Task2 全部）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/comparison_refine_service.py backend/tests/test_comparison_refine_service.py
git commit -m "feat(refine): apply_refinement 在已采集 offers 上过滤/排序/取前N + build_label"
```

---

## Task 3: `get_latest_session_offers`(数据来源)

**Files:**
- Modify: `backend/app/services/comparison_task_service.py`（在 `get_latest_task_for_draft` 之后新增函数）
- Test: `backend/tests/test_comparison_task_service.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_comparison_task_service.py
@pytest.mark.asyncio
async def test_get_latest_session_offers_flattens_items(monkeypatch):
    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params):
            assert "chat_session_id" in str(statement)
            return FakeResult(("task-1",))
    monkeypatch.setattr(comparison_task_service, "AsyncSessionLocal", S)
    monkeypatch.setattr(comparison_task_service, "_require_db_user_id", lambda u: 7)

    async def fake_get_task(task_id, user_id):
        assert task_id == "task-1"
        return {"id": "task-1", "subtasks": [
            {"platform": "jd",  "items": [{"id": "a", "priceValue": 1}]},
            {"platform": "zkh", "items": [{"id": "b", "priceValue": 2}]},
        ]}
    monkeypatch.setattr(comparison_task_service, "get_task", fake_get_task)

    offers = await comparison_task_service.get_latest_session_offers("sess-1", "u7")
    assert [o["id"] for o in offers] == ["a", "b"]


@pytest.mark.asyncio
async def test_get_latest_session_offers_none_when_no_task(monkeypatch):
    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params): return FakeResult(None)
    monkeypatch.setattr(comparison_task_service, "AsyncSessionLocal", S)
    monkeypatch.setattr(comparison_task_service, "_require_db_user_id", lambda u: 7)
    assert await comparison_task_service.get_latest_session_offers("sess-x", "u7") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_comparison_task_service.py -k get_latest_session_offers -q`
Expected: FAIL（`get_latest_session_offers` 不存在）

- [ ] **Step 3: 实现**

```python
# backend/app/services/comparison_task_service.py —— 在 get_latest_task_for_draft 之后新增
async def get_latest_session_offers(session_id: str, user_id: str) -> Optional[list[dict]]:
    """本会话最近一个比价 task 的全部 offers(跨平台拍平),无 task/无 offers → None。

    精炼指令的操作对象:不重新抓取,直接复用已采集结果(含 disliked 过滤,在 get_task 内)。
    """
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT t.id FROM comparison_tasks t
                JOIN comparison_drafts d ON t.draft_id = d.id
                WHERE d.chat_session_id = :sid AND t.user_id = :uid
                ORDER BY t.created_at DESC, t.id DESC
                LIMIT 1
                """
            ),
            {"sid": session_id, "uid": db_user_id},
        )
        row = result.fetchone()
    if not row:
        return None
    task = await get_task(row[0], user_id)
    if not task:
        return None
    offers = [item for st in task.get("subtasks", []) for item in (st.get("items") or [])]
    return offers or None
```

注:`_require_db_user_id` 已存在于本模块(`get_latest_task_for_draft` 在用),`get_latest_session_offers` 沿用它保持一致。

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_comparison_task_service.py -k get_latest_session_offers -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/comparison_task_service.py backend/tests/test_comparison_task_service.py
git commit -m "feat(refine): get_latest_session_offers 取本会话最近比价结果"
```

---

## Task 4: `handle_message` 精炼早分支(路由 + SSE)

**Files:**
- Modify: `backend/app/services/agent.py`（`handle_message` 内,`create_draft_from_message` 调用之前）
- Test: `backend/tests/test_chat_comparison_capture.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/test_chat_comparison_capture.py
import json
import pytest
from app.services import agent


async def _collect(gen):
    return "".join([c async for c in gen])


@pytest.mark.asyncio
async def test_handle_message_emits_refined_offers_when_results_exist(monkeypatch):
    monkeypatch.setattr(agent.comparison_refine_service, "parse_refinement",
                        lambda m: {"sort": "asc", "limit": 1, "platform": None, "brandKeep": None,
                                   "brandDrop": None, "priceMin": None, "priceMax": None, "label": "按价格最低取前1"})
    async def fake_offers(sid, uid):
        return [{"id": "b", "priceValue": 1, "title": "便宜货"}, {"id": "a", "priceValue": 9, "title": "贵货"}]
    monkeypatch.setattr(agent.comparison_task_service, "get_latest_session_offers", fake_offers)
    monkeypatch.setattr(agent, "get_session_context", _fake_ctx())

    out = await _collect(agent.handle_message("s1", "最便宜的1个", "u1"))
    assert "event: refined_offers" in out
    assert "便宜货" in out and "event: done" in out


@pytest.mark.asyncio
async def test_handle_message_guides_when_no_results(monkeypatch):
    monkeypatch.setattr(agent.comparison_refine_service, "parse_refinement",
                        lambda m: {"sort": "asc", "limit": 5, "label": "x", "platform": None,
                                   "brandKeep": None, "brandDrop": None, "priceMin": None, "priceMax": None})
    async def no_offers(sid, uid): return None
    monkeypatch.setattr(agent.comparison_task_service, "get_latest_session_offers", no_offers)
    monkeypatch.setattr(agent, "get_session_context", _fake_ctx())

    out = await _collect(agent.handle_message("s1", "最便宜的5个", "u1"))
    assert "event: refined_offers" not in out
    assert "比价结果" in out  # 引导文案


@pytest.mark.asyncio
async def test_handle_message_falls_through_when_not_refinement(monkeypatch):
    monkeypatch.setattr(agent.comparison_refine_service, "parse_refinement", lambda m: None)
    called = {"draft": False}
    async def fake_create(**kw):
        called["draft"] = True
        return {"parsedIntent": {}, "shouldCreateDraft": False, "guidance": "请补充产品名称"}
    monkeypatch.setattr(agent.comparison_draft_service, "create_draft_from_message", fake_create)
    monkeypatch.setattr(agent, "get_session_context", _fake_ctx())

    out = await _collect(agent.handle_message("s1", "防尘口罩", "u1"))
    assert called["draft"] is True  # 非精炼 → 走原路径
```

并在该测试文件顶部加一个共享小工具(若尚无):
```python
def _fake_ctx():
    async def ctx(session_id, user_id):
        return {"conversation": [], "last_intent": None}
    return ctx
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_chat_comparison_capture.py -k handle_message -q`
Expected: FAIL（`agent.comparison_refine_service` 未导入 / 无早分支）

- [ ] **Step 3: 实现早分支**

在 `agent.py` 顶部 import 区加:
```python
from app.services import comparison_refine_service, comparison_task_service
```
在 `handle_message` 中 `ctx = await get_session_context(...)` 之后、`create_draft_from_message` 之前插入:
```python
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
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_chat_comparison_capture.py -k handle_message -q`
Expected: PASS

- [ ] **Step 5: 跑全后端回归**

Run: `cd backend && python -m pytest -q`
Expected: PASS（包括既有 ~170 个;若旧测试 mock 了 `get_session_context` 形状不同,按其约定微调)

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/agent.py backend/tests/test_chat_comparison_capture.py
git commit -m "feat(refine): handle_message 精炼早分支(命中→在已有结果上操作/无结果引导)"
```

---

## Task 5: 持久化(迁移 + save_turn + 捕获 + get_session)

**Files:**
- Create: `backend/migrations/007_add_refined_offers_to_chat_message.sql`
- Modify: `backend/app/routers/chat.py`、`backend/app/services/chat_history_service.py`
- Test: `backend/tests/test_chat_comparison_capture.py`

- [ ] **Step 1: 写迁移**

```sql
-- backend/migrations/007_add_refined_offers_to_chat_message.sql
-- MRO Agent — 给聊天消息加"精炼结果"列,与 comparison_draft 平行,供回看历史时还原精炼结果卡片
-- Apply: mysql -h <host> -P <port> -u root -p <db> < 007_add_refined_offers_to_chat_message.sql
ALTER TABLE t_chat_message ADD COLUMN refined_offers JSON NULL;
```

- [ ] **Step 2: 写失败测试(捕获 + 落库参数)**

```python
# 追加到 tests/test_chat_comparison_capture.py
@pytest.mark.asyncio
async def test_capturing_stream_persists_refined_offers(monkeypatch):
    from app.routers import chat
    payload = {"sourceProductType": "防尘口罩", "operationLabel": "按价格最低取前1",
               "offers": [{"id": "b", "title": "便宜货", "priceValue": 1}]}

    async def fake_handle_message(*a, **k):
        yield "event: refined_offers\ndata: " + json.dumps(payload) + "\n\n"
        yield 'event: text\ndata: "为您按价格最低取前1:"\n\n'
        yield "event: done\ndata: \n\n"

    saved = {}
    async def fake_save_turn(**kwargs):
        saved.update(kwargs)
    def fake_ensure_future(coro):
        import asyncio as _a
        return _a.ensure_future(coro)

    monkeypatch.setattr(chat, "handle_message", fake_handle_message)
    monkeypatch.setattr(chat.chat_history_service, "save_turn", fake_save_turn)
    monkeypatch.setattr(chat.asyncio, "ensure_future", fake_ensure_future)

    chunks = [c async for c in chat._capturing_stream("u1", "s1", "最便宜的1个", "")]
    # 等待 fire-and-forget 落库
    import asyncio
    await asyncio.sleep(0.05)
    assert saved.get("refined_offers") == payload["offers"]
```

- [ ] **Step 3: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_chat_comparison_capture.py -k refined_offers -q`
Expected: FAIL（`save_turn` 未收到 `refined_offers`)

- [ ] **Step 4: 实现捕获 + 落库 + 读取**

`chat.py: _capturing_stream` —— 在累积区加 `refined_offers`:
```python
    refined_offers: Optional[list] = None
```
在事件解析 `elif pending_event == "comparison_draft":` 同级加:
```python
                    elif pending_event == "refined_offers":
                        try:
                            refined_offers = json.loads(data).get("offers")
                        except Exception:
                            pass
```
`finally` 里 `save_turn(...)` 调用补传:
```python
                refined_offers=refined_offers,
```

`chat_history_service.save_turn` —— 函数签名加参数:
```python
    refined_offers: Optional[list] = None,
```
助手消息 INSERT 改为带 `refined_offers` 列:
```python
                text(
                    "INSERT INTO t_chat_message (session_id, role, content, sku_results, competitor_results, slot_clarification, comparison_draft, refined_offers) "
                    "VALUES (:sid, 'assistant', :content, :sku, :comp, :slot, :draft, :refined)"
                ),
                {
                    ...,
                    "refined": json.dumps(refined_offers, ensure_ascii=False) if refined_offers else None,
                },
```
`get_session` —— SELECT 列表加 `refined_offers`,装配进消息:
```python
        # SELECT ... , comparison_draft, refined_offers FROM t_chat_message ...
        refined = json.loads(m[8]) if m[8] else None   # 索引随新增列 +1,以实际 SELECT 顺序为准
        messages.append({... , "refinedOffers": refined})
```

- [ ] **Step 5: 跑测试确认通过 + 全回归**

Run: `cd backend && python -m pytest -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/migrations/007_add_refined_offers_to_chat_message.sql backend/app/routers/chat.py backend/app/services/chat_history_service.py backend/tests/test_chat_comparison_capture.py
git commit -m "feat(refine): 持久化精炼结果(t_chat_message.refined_offers 列 + 捕获/落库/读取)"
```

---

## Task 6: 前端(抽 OfferRow + RefinedOffersCard + 接线)

**Files:**
- Create: `frontend/src/components/OfferRow.tsx`、`frontend/src/components/RefinedOffersCard.tsx`
- Modify: `frontend/src/components/ComparisonTaskCard.tsx`、`services/api.ts`、`types/index.ts`、`components/ChatWindow.tsx`、`components/MessageBubble.tsx`

> 前端无测试框架,本任务以 `tsc -b && vite build` 通过 + 线上实操为验收。

- [ ] **Step 1: 抽出 `OfferRow`**

把 `ComparisonTaskCard.tsx` 内现有的单条 offer 渲染(含"合适/不合适"投票)提取为 `OfferRow.tsx` 默认导出,props:`{ offer: ExternalOffer, sessionId: string, onRestore?: (id:string)=>void }`(与现用法一致)。`ComparisonTaskCard.tsx` 改为 `import OfferRow from "./OfferRow"` 并替换内联实现。先确认抽出后 `npm --prefix frontend run build` 通过、行为不变,提交:
```bash
git add frontend/src/components/OfferRow.tsx frontend/src/components/ComparisonTaskCard.tsx
git commit -m "refactor(ui): 抽出可复用 OfferRow"
```

- [ ] **Step 2: 类型 + API 事件**

`types/index.ts` 给 `ChatMessage` 加:
```ts
refinedOffers?: { sourceProductType: string; operationLabel: string; offers: ExternalOffer[]; note?: string };
```
`services/api.ts`:`SSECallbacks` 加 `onRefinedOffers?: (r: NonNullable<ChatMessage["refinedOffers"]>) => void;`,并在 `handleEvent` 加:
```ts
      case "refined_offers":
        try { callbacks.onRefinedOffers?.(JSON.parse(data)); } catch (e) { console.error("refined_offers parse", e); }
        break;
```

- [ ] **Step 3: ChatWindow 接线**

`ChatWindow.handleSend` 的回调对象里加:
```ts
        onRefinedOffers: (r) => {
          const next = messagesRef.current.map((m) =>
            m.id === assistantMsgId ? { ...m, refinedOffers: r } : m
          );
          updateMessages(next);
        },
```

- [ ] **Step 4: RefinedOffersCard + 渲染**

`RefinedOffersCard.tsx`:
```tsx
import OfferRow from "./OfferRow";
import { ChatMessage } from "../types";

type R = NonNullable<ChatMessage["refinedOffers"]>;
export default function RefinedOffersCard({ data, sessionId }: { data: R; sessionId: string }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: 12, marginTop: 8 }}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>{data.operationLabel}（{data.offers.length} 条）</div>
      {data.offers.map((o) => (<OfferRow key={o.id} offer={o} sessionId={sessionId} />))}
      {data.note && <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>{data.note}</div>}
    </div>
  );
}
```
`MessageBubble.tsx`:在渲染 `comparisonTask` 同处,消息含 `refinedOffers` 时渲染:
```tsx
{message.refinedOffers && <RefinedOffersCard data={message.refinedOffers} sessionId={sessionId} />}
```
(顶部 `import RefinedOffersCard from "./RefinedOffersCard";`)

- [ ] **Step 5: 构建验收 + 提交**

Run: `npm --prefix frontend run build`
Expected: 构建通过(无 TS 错误)
```bash
git add frontend/src
git commit -m "feat(refine): 前端精炼结果卡片 RefinedOffersCard + SSE 接线"
```

---

## Task 7: 部署 + 线上回归

- [ ] **Step 1: 应用迁移 007**（在后端 DB 上执行 `007_add_refined_offers_to_chat_message.sql`,用 backend/.env 的 DB 连接;若迁移无自动 runner,手动 `mysql ... < 007...sql`)
- [ ] **Step 2: 部署**（commit 推送 + 服务器 `git reset` + `docker compose up -d --build backend frontend`,按既有部署陷阱验证 HEAD/容器重建/容器内代码)
- [ ] **Step 3: 线上回归**（Playwright 或手动登录 13816702381 会话「防尘口罩」:发起一次比价出结果后,发"能不能选出价格最低的五个" → 应出精炼结果卡片、不再造垃圾草稿;再测"只看3M""京东上50元以下"组合;无结果会话发精炼句 → 出引导)

---

## 自检(Spec 覆盖)

| Spec 要求 | 对应任务 |
|---|---|
| 四种操作(排序/取前N/品牌/价位/平台) | Task 1(解析)+ Task 2(执行) |
| 确定性识别 + 保守原则不劫持 | Task 1(否定样本测试) |
| 门控"本会话有结果",无则引导 | Task 3 + Task 4 |
| 不重新抓取,复用已采集 offers + ranker 原语 | Task 2(text_matches_brand)+ Task 3(get_task) |
| 新消息 + 结果列表(复用 OfferRow) | Task 6 |
| 落 refined_offers 列可回看 | Task 5 |
| 顺带堵死垃圾草稿(精炼先于建草稿) | Task 4(falls_through 测试 + 早 return) |
| 边界:过滤空/无价/抽不出操作 | Task 2(空)+ Task 4(无结果引导) |
| 回归"防尘口罩"不再出垃圾草稿 | Task 1(回归测试)+ Task 7(线上) |

**v1 简化(与 Spec §9 的偏差,有意为之)**:Spec §9"命中精炼但抽不出具体操作 → 反问"在确定性解析下无该中间态——无操作符即 `parse_refinement` 返回 None、回落新品引导(不造垃圾草稿)。不引入"像精炼但说不清"的模糊门控(那正是当初 bug 的根),该反问留待 v1.1 按真实日志再评估。
