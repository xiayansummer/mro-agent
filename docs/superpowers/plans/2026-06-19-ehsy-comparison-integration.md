# 西域(ehsy)整合进比价 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把已有的西域(ehsy)服务端抓取并入比价结果——作第 3 个平台,后端在 `start_draft` 同步抓取、归一、排序、以 completed 子任务落库,jd/zkh 仍走扩展。

**Architecture:** 新建纯映射适配器 `ehsy_comparison_source`(ehsy dict→ExternalOffer dict,不排序);`start_draft` 在主事务提交 jd/zkh 后,用**独立 session**注入 ehsy 子任务(fetch→`rank_external_offers`→写 items_json+DONE),全程 try/except 隔离,西域故障绝不拖垮 jd/zkh。排序/disliked/精炼/前端复用现有平台无关逻辑。

**Tech Stack:** FastAPI / SQLAlchemy(async, raw SQL)/ MySQL / httpx(已有 ehsy 客户端)/ pytest+pytest-asyncio / React+Vite。

**Spec:** `docs/superpowers/specs/2026-06-19-ehsy-comparison-integration-design.md`

> 与 spec §5 的细化:适配器**只做 fetch+映射**(返回未排序 ExternalOffer dict),排序移到 `start_draft` 注入处,与 jd/zkh 写入路径 `submit_subtask_results` 对称。

---

## 文件结构

| 动作 | 文件 | 职责 |
|---|---|---|
| 新建 | `backend/app/services/ehsy_comparison_source.py` | `_to_external_offer`(纯映射)+ `fetch_ehsy_offers`(调 search_ehsy+映射,降级返回 []) |
| 新建 | `backend/tests/test_ehsy_comparison_source.py` | 上述测试 |
| 改 | `backend/app/models/comparison.py` | `Platform` 加 `"ehsy"`;`preferredPlatforms` 默认含 ehsy |
| 改 | `backend/app/services/comparison_task_service.py` | `start_draft` 取 structure_json + 过滤 ehsy 出扩展规格 + 调 `_inject_ehsy_subtask`;新增 `_inject_ehsy_subtask` + `_ehsy_search_term` |
| 改 | `backend/tests/test_comparison_task_service.py` | `_ehsy_search_term` + `_inject_ehsy_subtask` 测试 |
| 改 | `backend/app/services/comparison_refine_service.py` | `_PLATFORM` 加西域;`_PLAT_CN` 加 `ehsy:西域` |
| 改 | `backend/tests/test_comparison_refine_service.py` | "只看西域" 测试 |
| 改 | `frontend/src/types/index.ts` 等 | Platform 加 ehsy;`PLATFORM_LABELS` 加西域(顺带 dedup) |

---

## Task 1: Platform 类型 + 默认平台

**Files:**
- Modify: `backend/app/models/comparison.py`
- Test: `backend/tests/test_comparison_models.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 backend/tests/test_comparison_models.py
from app.models.comparison import ExternalOffer, ComparisonStructure


def test_platform_accepts_ehsy():
    o = ExternalOffer(
        id="ehsy-X1", platform="ehsy", title="3M 口罩", unitComparable=False,
        productUrl="https://www.ehsy.com/product-X1", rawRank=0, matchScore=0.0,
    )
    assert o.platform == "ehsy"


def test_structure_default_platforms_include_ehsy():
    s = ComparisonStructure()
    assert s.preferredPlatforms == ["jd", "zkh", "ehsy"]
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_comparison_models.py -k "ehsy or default_platforms" -q`
Expected: FAIL（`platform` 校验拒绝 "ehsy" / 默认不含 ehsy）

- [ ] **Step 3: 实现**

`comparison.py` 第 7 行:
```python
Platform = Literal["jd", "zkh", "ehsy"]
```
`ComparisonStructure.preferredPlatforms` 默认(原 `["jd", "zkh"]`):
```python
    preferredPlatforms: list[Platform] = Field(default_factory=lambda: ["jd", "zkh", "ehsy"])
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_comparison_models.py -q`
Expected: PASS（含新 2 个,旧测试不破）

- [ ] **Step 5: 提交**

```bash
git add backend/app/models/comparison.py backend/tests/test_comparison_models.py
git commit -m "feat(ehsy): Platform 加 ehsy + 默认平台含西域"
```

---

## Task 2: ehsy→ExternalOffer 归一适配器

**Files:**
- Create: `backend/app/services/ehsy_comparison_source.py`
- Test: `backend/tests/test_ehsy_comparison_source.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ehsy_comparison_source.py
import pytest
from app.services import ehsy_comparison_source as mod
from app.services.ehsy_comparison_source import _to_external_offer, fetch_ehsy_offers


def _raw():
    return {"name": "3M 防尘口罩，9501V+ 售卖规格：1只", "brand": "3M",
            "price": "4", "unit": "只", "sku": "CMN420",
            "url": "https://www.ehsy.com/product-CMN420", "delivery": "7个工作日", "source": "西域"}


def test_map_normal():
    o = _to_external_offer(_raw(), 0)
    assert o["platform"] == "ehsy"
    assert o["id"] == "ehsy-CMN420"
    assert o["platformSku"] == "CMN420"
    assert o["priceValue"] == 4.0
    assert o["unitComparable"] is False
    assert o["unitText"] == "只"
    assert o["deliveryText"] == "7个工作日"
    assert o["title"].startswith("3M")
    assert "¥4" in o["priceText"]


def test_map_missing_price():
    r = _raw(); r["price"] = None
    o = _to_external_offer(r, 1)
    assert o["priceValue"] is None
    assert o["priceText"] is None


def test_map_missing_sku_stable_id_and_url_fallback():
    r = _raw(); r["sku"] = None; r["url"] = None
    o1 = _to_external_offer(r, 0)
    o2 = _to_external_offer(r, 0)
    assert o1["id"] == o2["id"]           # 稳定(md5,非进程内 hash)
    assert o1["id"].startswith("ehsy-")
    assert o1["platformSku"] is None
    assert o1["productUrl"].startswith("https://www.ehsy.com")


def test_map_empty_name_dropped():
    r = _raw(); r["name"] = ""
    assert _to_external_offer(r, 0) is None


@pytest.mark.asyncio
async def test_fetch_maps_and_indexes(monkeypatch):
    async def fake_search(q, limit=8):
        return [_raw(), {**_raw(), "name": "安可护 口罩", "sku": "SFW179"}]
    monkeypatch.setattr(mod, "search_ehsy", fake_search)
    out = await fetch_ehsy_offers("防尘口罩")
    assert [o["rawRank"] for o in out] == [0, 1]
    assert {o["platformSku"] for o in out} == {"CMN420", "SFW179"}


@pytest.mark.asyncio
async def test_fetch_degrades_on_error(monkeypatch):
    async def boom(q, limit=8):
        raise RuntimeError("api down")
    monkeypatch.setattr(mod, "search_ehsy", boom)
    assert await fetch_ehsy_offers("x") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_ehsy_comparison_source.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现**

```python
# backend/app/services/ehsy_comparison_source.py
"""西域(ehsy)比价源适配器:把 search_ehsy 的原始结果映射成 ExternalOffer dict。

纯映射,不排序(排序在 start_draft 注入处用 rank_external_offers 做,与 jd/zkh 写入路径对称)。
出错优雅降级返回 []。
"""
import hashlib
import logging
from typing import Optional

from app.services.competitor_search import search_ehsy

logger = logging.getLogger(__name__)

_EHSY_SEARCH_FALLBACK = "https://www.ehsy.com/"


def _to_external_offer(p: dict, raw_rank: int) -> Optional[dict]:
    name = (p.get("name") or "").strip()
    if not name:
        return None
    sku = p.get("sku")
    raw_price = p.get("price")
    try:
        price_value = float(raw_price) if raw_price not in (None, "") else None
    except (ValueError, TypeError):
        price_value = None
    unit = p.get("unit")
    price_text = None
    if raw_price not in (None, ""):
        price_text = f"¥{raw_price}/{unit}" if unit else f"¥{raw_price}"
    offer_id = f"ehsy-{sku}" if sku else f"ehsy-{hashlib.md5(name.encode()).hexdigest()[:12]}"
    return {
        "id": offer_id,
        "platform": "ehsy",
        "title": name[:100],
        "brand": p.get("brand"),
        "priceText": price_text,
        "priceValue": price_value,
        "unitText": unit,
        "unitComparable": False,
        "deliveryText": p.get("delivery"),
        "productUrl": p.get("url") or _EHSY_SEARCH_FALLBACK,
        "platformSku": str(sku) if sku else None,
        "rawRank": raw_rank,
    }


async def fetch_ehsy_offers(search_term: str, limit: int = 8) -> list[dict]:
    """抓西域并映射成未排序 ExternalOffer dict;任何异常→[](降级)。"""
    try:
        raw = await search_ehsy(search_term, limit=limit)
    except Exception:
        logger.warning("ehsy fetch failed for %r", search_term, exc_info=True)
        return []
    offers = []
    for i, p in enumerate(raw):
        o = _to_external_offer(p, i)
        if o:
            offers.append(o)
    return offers
```

- [ ] **Step 4: 跑测试确认通过**

Run: `cd backend && python -m pytest tests/test_ehsy_comparison_source.py -q`
Expected: PASS（7 个）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/ehsy_comparison_source.py backend/tests/test_ehsy_comparison_source.py
git commit -m "feat(ehsy): ehsy→ExternalOffer 归一适配器(纯映射+降级)"
```

---

## Task 3: start_draft 注入西域子任务

**Files:**
- Modify: `backend/app/services/comparison_task_service.py`
- Test: `backend/tests/test_comparison_task_service.py`

注入用**独立 session、独立 try/except**,在主事务(jd/zkh)提交之后执行,确保西域故障绝不影响 jd/zkh。排序复用 `rank_external_offers`(与 `submit_subtask_results` 对称),完成状态用 `ComparisonSubtaskStatus.DONE`。

- [ ] **Step 1: 写失败测试**

```python
# 追加到 backend/tests/test_comparison_task_service.py
@pytest.mark.asyncio
async def test_ehsy_search_term_prefers_jd_then_zkh_then_producttype():
    from app.services.comparison_task_service import _ehsy_search_term
    assert _ehsy_search_term({"jd": ["a", "b"], "zkh": ["c"]}, {}) == "a"
    assert _ehsy_search_term({"jd": [], "zkh": ["c"]}, {}) == "c"
    assert _ehsy_search_term({}, {"specification": {"productType": "口罩"}}) == "口罩"


@pytest.mark.asyncio
async def test_inject_ehsy_inserts_done_subtask(monkeypatch):
    from app.services import comparison_task_service as svc

    captured = {}

    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params):
            if "INSERT INTO comparison_subtasks" in str(statement):
                captured.update(params)
            return FakeResult()
        async def commit(self): pass
    monkeypatch.setattr(svc, "AsyncSessionLocal", S)

    async def fake_fetch(term, limit=8):
        return [{"id": "ehsy-1", "platform": "ehsy", "priceValue": 4.0, "title": "口罩"}]
    monkeypatch.setattr(svc.ehsy_comparison_source, "fetch_ehsy_offers", fake_fetch)
    monkeypatch.setattr(svc, "rank_external_offers", lambda s, o, preferences=None: o)
    async def fake_prefs(uid): return {}
    monkeypatch.setattr(svc.memory_service, "get_preference_signals", fake_prefs)
    async def fake_refresh(session, sid): return None
    monkeypatch.setattr(svc, "_refresh_task_status", fake_refresh)

    await svc._inject_ehsy_subtask("task-1", "u7", {"specification": {"productType": "口罩"}}, {"jd": ["口罩"]})

    assert captured.get("platform") == "ehsy"
    assert captured.get("status") == svc.ComparisonSubtaskStatus.DONE.value
    assert "口罩" in captured.get("items_json", "")


@pytest.mark.asyncio
async def test_inject_ehsy_swallows_failure(monkeypatch):
    from app.services import comparison_task_service as svc
    inserted = {"n": 0}

    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params):
            inserted["n"] += 1
            return FakeResult()
        async def commit(self): pass
    monkeypatch.setattr(svc, "AsyncSessionLocal", S)

    async def boom(term, limit=8):
        raise RuntimeError("ehsy down")
    monkeypatch.setattr(svc.ehsy_comparison_source, "fetch_ehsy_offers", boom)

    # 不抛异常,且没有 INSERT
    await svc._inject_ehsy_subtask("task-1", "u7", {}, {"jd": ["口罩"]})
    assert inserted["n"] == 0
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_comparison_task_service.py -k "ehsy" -q`
Expected: FAIL（`_ehsy_search_term` / `_inject_ehsy_subtask` 不存在;`ehsy_comparison_source` 未导入）

- [ ] **Step 3: 实现**

在 `comparison_task_service.py` 顶部加 import(若无 logging 也补上):
```python
import logging

from app.services import ehsy_comparison_source

logger = logging.getLogger(__name__)
```
新增两个函数(放在 `start_draft` 之后):
```python
def _ehsy_search_term(search_terms: dict, structure: dict) -> str:
    for key in ("jd", "zkh"):
        terms = search_terms.get(key) or []
        if terms:
            return terms[0]
    return ((structure or {}).get("specification") or {}).get("productType") or ""


async def _inject_ehsy_subtask(task_id: str, user_id: str, structure: dict, search_terms: dict) -> None:
    """后端服务端抓西域,排序后以 DONE 子任务落库。独立 session + try/except:
    西域故障绝不影响已提交的 jd/zkh 子任务。"""
    try:
        term = _ehsy_search_term(search_terms, structure)
        if not term:
            return
        raw = await ehsy_comparison_source.fetch_ehsy_offers(term)
        if not raw:
            # 也写一个 0 条的 DONE 子任务,让前端显示"西域:暂无匹配"
            raw_ranked = []
        else:
            preferences = await memory_service.get_preference_signals(user_id)
            raw_ranked = [
                {**o, "selectedSearchTerm": term}
                for o in rank_external_offers(structure, raw, preferences=preferences)
            ]
        subtask_id = _new_id("cmp_subtask")
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO comparison_subtasks (id, task_id, platform, status, search_terms_json, items_json)
                    VALUES (:id, :task_id, 'ehsy', :status, :search_terms_json, :items_json)
                    """
                ),
                {
                    "id": subtask_id,
                    "task_id": task_id,
                    "status": ComparisonSubtaskStatus.DONE.value,
                    "search_terms_json": _json([term]),
                    "items_json": _json(raw_ranked),
                },
            )
            await _refresh_task_status(session, subtask_id)
            await session.commit()
    except Exception:
        logger.warning("ehsy injection failed; comparison continues without 西域", exc_info=True)
```
改 `start_draft`:把 draft 的 SELECT 加 `structure_json`,把 ehsy 从扩展规格里过滤掉,提交后注入 ehsy。具体:
- SELECT 改为 `SELECT id, selected_platforms, search_terms_json, structure_json FROM comparison_drafts ...`
- `selected_platforms = _loads(draft[1]) or ["jd", "zkh", "ehsy"]`
- 新增 `extension_platforms = [p for p in selected_platforms if p != "ehsy"]`,把 `_build_subtask_specs(...)` 的第一个参数从 `selected_platforms` 改为 `extension_platforms`
- 在 `await session.commit()`(主事务)之后、`return await get_task(...)` 之前加:
```python
    if "ehsy" in selected_platforms:
        await _inject_ehsy_subtask(task_id, user_id, _loads(draft[3]) or {}, search_terms)
```

- [ ] **Step 4: 跑测试确认通过 + 全后端回归**

Run: `cd backend && python -m pytest -q`
Expected: PASS（新 ehsy 测试 + 既有套件零回归;`test_start_draft_*` 因 SELECT 多了一列,若 FakeSession 的 draft 行只返回 3 列需补第 4 列 `structure_json`——按现有 FakeSession 里 `drafts` 的构造补一个 JSON 字段)

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/comparison_task_service.py backend/tests/test_comparison_task_service.py
git commit -m "feat(ehsy): start_draft 注入西域 DONE 子任务(独立 session,故障隔离)"
```

---

## Task 4: 精炼平台过滤泛化为 keep/drop(N 平台正确)+ 西域

**Files:**
- Modify: `backend/app/services/comparison_refine_service.py`
- Test: `backend/tests/test_comparison_refine_service.py`

**为何不只是"加西域"**:现有 `cmd["platform"]` 是单一"只看某平台",`去掉震坤行` 靠"二选一"(→ 只看京东)实现——这在两平台下对、三平台下**错**(`去掉震坤行` 会把西域也丢掉)。根因解:把平台过滤拆成 `platformKeep`(只看某平台)+ `platformDrop`(去掉某平台),对任意平台数都正确。

- [ ] **Step 1: 写失败测试(新增 + 改写旧平台测试)**

```python
# —— 改写 test_comparison_refine_service.py 中现有这几个平台测试 ——
def test_platform_keep():
    assert parse_refinement("只看京东工业品")["platformKeep"] == "jd"
    assert parse_refinement("只看西域")["platformKeep"] == "ehsy"

def test_platform_drop():
    assert parse_refinement("去掉震坤行")["platformDrop"] == "zkh"
    assert parse_refinement("去掉西域")["platformDrop"] == "ehsy"

def test_composition_platform_sort_limit():
    cmd = parse_refinement("京东上最便宜的3个")
    assert cmd["platformKeep"] == "jd" and cmd["sort"] == "asc" and cmd["limit"] == 3

# —— 新增 apply 层 keep/drop 测试 ——
def test_apply_platform_keep_ehsy():
    offers = [{"id":"a","platform":"jd","priceValue":1},{"id":"b","platform":"ehsy","priceValue":2}]
    cmd = {"platformKeep":"ehsy","platformDrop":None,"brandKeep":None,"brandDrop":None,
           "priceMin":None,"priceMax":None,"sort":None,"limit":None,"label":""}
    assert [o["id"] for o in apply_refinement(offers, cmd)] == ["b"]

def test_apply_platform_drop_ehsy():
    offers = [{"id":"a","platform":"jd","priceValue":1},{"id":"b","platform":"ehsy","priceValue":2}]
    cmd = {"platformKeep":None,"platformDrop":"ehsy","brandKeep":None,"brandDrop":None,
           "priceMin":None,"priceMax":None,"sort":None,"limit":None,"label":""}
    assert [o["id"] for o in apply_refinement(offers, cmd)] == ["a"]

def test_label_ehsy_keep_and_drop():
    base = {"platformKeep":None,"platformDrop":None,"brandKeep":None,"brandDrop":None,
            "priceMin":None,"priceMax":None,"sort":None,"limit":None}
    from app.services.comparison_refine_service import build_label
    assert build_label({**base,"platformKeep":"ehsy"}) == "西域"
    assert build_label({**base,"platformDrop":"ehsy"}) == "去掉西域"
```
注:任何引用旧 `cmd["platform"]` 键的现有 apply 测试(如 `test_apply_platform_then_sort`)都把 `"platform":"jd"` 改成 `"platformKeep":"jd"`。

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && python -m pytest tests/test_comparison_refine_service.py -k "platform or label_ehsy or composition" -q`
Expected: FAIL（无 platformKeep/platformDrop 键、不识别西域、`_PLAT_CN` 无 ehsy）

- [ ] **Step 3: 实现**

`_PLATFORM`(第 17 行)加西域;`_PLAT_CN`(第 46 行)加 ehsy:
```python
_PLATFORM = (("京东工业品", "jd"), ("京东", "jd"), ("jd", "jd"),
             ("震坤行", "zkh"), ("zkh", "zkh"),
             ("西域", "ehsy"), ("ehsy", "ehsy"))
...
_PLAT_CN = {"jd": "京东工业品", "zkh": "震坤行", "ehsy": "西域"}
_PLAT_NEG_MAP = {"京东工业品": "jd", "京东": "jd", "震坤行": "zkh", "西域": "ehsy", "ehsy": "ehsy"}
```
`parse_refinement`:cmd 初始化里把 `"platform": None` 换成 `"platformKeep": None, "platformDrop": None`。平台解析段(现有 `_neg_plat` 块)整体替换为:
```python
    # 平台:先判否定(去掉/排除/不要 X)→ platformDrop;否则 只看 X → platformKeep。
    _neg_plat = re.search(r"(去掉|不要|排除|除了)\s*(京东工业品|京东|震坤行|西域|ehsy)", work)
    if _neg_plat:
        cmd["platformDrop"] = _PLAT_NEG_MAP[_neg_plat.group(2)]
        strip(_neg_plat.group(0)); matched = True
    else:
        for kw, plat in _PLATFORM:
            if kw in work:
                cmd["platformKeep"] = plat
                strip(kw); matched = True; break
```
品牌 keep 正则里排除集补西域(避免"只看西域"被当品牌):现有 `if m and m.group(2) not in {"", "京东", "震坤行"}` → 加 `"西域"`。
`apply_refinement` 平台段(现有 `if cmd.get("platform")`)替换为:
```python
    if cmd.get("platformKeep"):
        out = [o for o in out if o.get("platform") == cmd["platformKeep"]]
    if cmd.get("platformDrop"):
        out = [o for o in out if o.get("platform") != cmd["platformDrop"]]
```
`build_label` 平台段(现有 `if cmd.get("platform")`)替换为:
```python
    if cmd.get("platformKeep"):
        parts.append(_PLAT_CN[cmd["platformKeep"]])
    if cmd.get("platformDrop"):
        parts.append("去掉" + _PLAT_CN[cmd["platformDrop"]])
```

- [ ] **Step 4: 跑测试确认通过(全文件)**

Run: `cd backend && python -m pytest tests/test_comparison_refine_service.py -q`
Expected: PASS（含改写的平台测试 + 新增 keep/drop/label;其余精炼测试不破）

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/comparison_refine_service.py backend/tests/test_comparison_refine_service.py
git commit -m "feat(ehsy): 精炼平台过滤泛化 keep/drop(三平台正确)+ 只看/去掉西域"
```

---

## Task 5: 前端(西域标签 + 类型 + 展示)

**Files:**
- Modify: `frontend/src/types/index.ts`、`frontend/src/components/OfferRow.tsx`、`frontend/src/components/ComparisonTaskCard.tsx`

> 前端无测试框架,以 `npm --prefix frontend run build` 通过 + 线上实操为验收。

- [ ] **Step 1: 类型加 ehsy**

`types/index.ts`:找到 `ExternalOffer.platform` / `ComparisonPlatform` 的联合类型(当前 `"jd" | "zkh"`),改为 `"jd" | "zkh" | "ehsy"`。

- [ ] **Step 2: PLATFORM_LABELS 加西域(顺带 dedup)**

`OfferRow.tsx` 与 `ComparisonTaskCard.tsx` 各有一份 `PLATFORM_LABELS`(`{jd:"京东工业品", zkh:"震坤行"}`)。两处都加 `ehsy: "西域"`。同时把这份常量提取到 `types/index.ts`(或一个 `constants.ts`)导出,两个组件 import 同一份,消除重复(Task6 遗留)。例:
```ts
// types/index.ts
export const PLATFORM_LABELS: Record<"jd" | "zkh" | "ehsy", string> = {
  jd: "京东工业品", zkh: "震坤行", ehsy: "西域",
};
```
`OfferRow.tsx` / `ComparisonTaskCard.tsx` 删除本地定义,改 `import { PLATFORM_LABELS } from "../types"`。

- [ ] **Step 3: 西域子任务展示(无登录态)**

`ComparisonTaskCard.tsx` 渲染各平台状态/子任务处:西域子任务恒 `done`,不显示"需登录/重试"。若现有 `PlatformStatusChip` 对未知/已完成平台已优雅处理,只需确认西域走"已完成"分支即可;若它硬编码了 jd/zkh 的登录态逻辑,给 ehsy 加一条"服务端源,无需登录"的展示(简单标"已完成")。

- [ ] **Step 4: 构建验收 + 提交**

Run: `npm --prefix frontend run build`
Expected: 构建通过(无 TS 错误)
```bash
git add frontend/src
git commit -m "feat(ehsy): 前端西域标签 + 类型 + 展示(PLATFORM_LABELS dedup)"
```

---

## Task 6: 部署 + 线上回归

- [ ] **Step 1: 部署**(commit 推送 + 服务器 `git reset` + `docker compose up -d --build backend frontend`,按部署陷阱验证 HEAD/容器重建/容器内代码;**无新迁移**,本特性不加 DB 列)
- [ ] **Step 2: 线上回归**:登录测试账号发起一次真实比价(如「防尘口罩 KN95 带阀」)→ 点开始比价 → 确认**西域结果出现在比价卡片**(秒出、带价格/货期/西域标签);扩展离线时西域仍出;发"只看西域最便宜的2个" → 精炼出西域 priceValue 最低 2 条
- [ ] **Step 3:**(可选)`docker compose exec -T backend python - < 西域实测脚本` 复跑确认 App API 仍活

---

## 自检(Spec 覆盖)

| Spec 要求 | 对应任务 |
|---|---|
| 西域作第3平台、服务端执行器、start 同步抓 | Task 3 |
| 复用 search_ehsy、ehsy→ExternalOffer 归一 | Task 2 |
| Platform 加 ehsy、默认开启 | Task 1 |
| unitComparable=False | Task 2(`_to_external_offer` 固定 False) |
| 失败优雅降级、不拖垮 start_draft | Task 2(fetch 降级)+ Task 3(独立 session+try/except) |
| 排序/disliked 复用 | Task 3(`rank_external_offers(structure, offers, preferences)`) |
| 精炼"只看西域" + 平台过滤泛化(keep/drop,修三平台下"去掉某平台"误丢西域) | Task 4 |
| 前端西域标签 + dedup | Task 5 |
| 搜索词复用主搜索词 | Task 3(`_ehsy_search_term`) |
| 扩展离线西域照常 | Task 3(独立于扩展)+ Task 6(线上验证) |
