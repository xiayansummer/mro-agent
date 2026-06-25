# 批量询价升级实施计划:库内匹配 + 逐行外部比价

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重新上线封存的批量询价,并升级为「库内 SKU 批量匹配(现有)+ 对选中行按需触发三平台外部比价(京东/震坤行/西域),行内展开,关页面重开自动接回」。

**Architecture:** 后端只新增 1 个入口 `POST /api/inquiry/compare-row`——把一行需求拼成 query,复用 `build_comparison_structure`(空上下文+不追问)→ `create_draft`(inquiry- 前缀 session,不污染对话)→ `start_draft`,返回 taskId;前端 InquiryPage 每行加「外部比价」按钮,复用 ChatWindow 的轮询模式拉 `get_task`,行内展开复用 `ComparisonTaskCard`,taskId 持久化进 localStorage 历史实现断点恢复。其余(parse/draft/task/ranker/ehsy注入/比价卡片)全复用,零或极小改动。

**Tech Stack:** FastAPI + pytest(后端有测试设施,走 TDD);React/Vite + TypeScript(前端无测试设施,走 `tsc -b` 类型门 + 手动验证)。

---

## 文件结构

| 文件 | 职责 | 动作 |
|---|---|---|
| `backend/app/routers/inquiry.py` | 加 `POST /inquiry/compare-row` 入口 + import 比价服务 | Modify |
| `backend/tests/test_inquiry.py` | compare-row 单元测试 | Create |
| `frontend/src/services/api.ts` | `compareInquiryRow()` API 封装 | Modify |
| `frontend/src/components/InquiryPage.tsx` | 行比价状态 / 按钮 / 触发 / 轮询 / 展示 / 持久化 | Modify |
| `frontend/src/components/Sidebar.tsx` | 取消注释批量询价入口 | Modify |

约定:本仓 mro-agent 改代码部署**必须** `docker compose up -d --build`(镜像 COPY,非 bind-mount),见 Task 7。

---

## Task 1: 后端 `compare-row` 入口(TDD)

**Files:**
- Modify: `backend/app/routers/inquiry.py`(顶部 import 区 + 文件末尾加入口)
- Create: `backend/tests/test_inquiry.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_inquiry.py`:

```python
import pytest

from app.routers import inquiry


class _FakeResult:
    def __init__(self, should, structure=None, guidance=None):
        self.shouldCreateDraft = should
        self.structure = structure
        self.guidance = guidance


@pytest.mark.asyncio
async def test_compare_row_builds_task(monkeypatch):
    captured = {}

    async def fake_build(query, conversation_context=None, memory_context="", image_base64="", skip_clarification=False):
        captured["query"] = query
        captured["conversation_context"] = conversation_context
        captured["skip_clarification"] = skip_clarification
        return _FakeResult(True, structure=object())

    async def fake_create_draft(user_id, session_id, raw_query, structure):
        captured["session_id"] = session_id
        return {"id": "draft-1"}

    async def fake_start_draft(draft_id, user_id):
        captured["draft_id"] = draft_id
        return {"id": "task-1"}

    monkeypatch.setattr(inquiry, "build_comparison_structure", fake_build)
    monkeypatch.setattr(inquiry, "create_draft", fake_create_draft)
    monkeypatch.setattr(inquiry, "start_draft", fake_start_draft)
    monkeypatch.setattr(inquiry, "_require_db_user_id", lambda u: 14)

    resp = await inquiry.compare_inquiry_row(
        {"需求品名": "防尘口罩", "需求品牌": "3M", "需求型号": "KN95"}, user_id="u14"
    )

    assert resp["ok"] is True
    assert resp["taskId"] == "task-1"
    assert resp["draftId"] == "draft-1"
    # 关键:每行独立解析,空上下文 + 不追问(天然无串味、不弹追问卡)
    assert captured["conversation_context"] == []
    assert captured["skip_clarification"] is True
    # 会话隔离:inquiry- 前缀
    assert captured["session_id"].startswith("inquiry-14-")
    # query 由 品牌+品名+型号 拼成
    assert "防尘口罩" in captured["query"] and "3M" in captured["query"] and "KN95" in captured["query"]


@pytest.mark.asyncio
async def test_compare_row_rejects_vague(monkeypatch):
    started = {"called": False}

    async def fake_build(query, conversation_context=None, memory_context="", image_base64="", skip_clarification=False):
        return _FakeResult(False, guidance="该行需求过于宽泛")

    async def fake_start_draft(draft_id, user_id):
        started["called"] = True
        return {"id": "x"}

    monkeypatch.setattr(inquiry, "build_comparison_structure", fake_build)
    monkeypatch.setattr(inquiry, "start_draft", fake_start_draft)

    resp = await inquiry.compare_inquiry_row({"需求品名": "东西"}, user_id="u14")

    assert resp["ok"] is False
    assert "宽泛" in resp["guidance"]
    assert started["called"] is False  # 模糊行不建 task


@pytest.mark.asyncio
async def test_compare_row_empty_query_returns_guidance():
    resp = await inquiry.compare_inquiry_row({"需求品名": "", "需求品牌": "", "需求型号": ""}, user_id="u14")
    assert resp["ok"] is False
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd backend && /Users/summer/anaconda3/bin/python -m pytest tests/test_inquiry.py -v`
Expected: FAIL —— `AttributeError: module 'app.routers.inquiry' has no attribute 'compare_inquiry_row'`(入口尚未存在)

- [ ] **Step 3: 加 import**

`backend/app/routers/inquiry.py` 顶部,在现有 `from app.services.sku_search import search_skus, relaxed_search` 之后追加:

```python
import uuid

from app.services.comparison_structure import build_comparison_structure
from app.services.comparison_draft_service import create_draft, _require_db_user_id
from app.services.comparison_task_service import start_draft
```

(`uuid` 与顶部其它 `import` 放一起亦可;关键是 `build_comparison_structure` / `create_draft` / `start_draft` / `_require_db_user_id` 进入 `inquiry` 模块命名空间,测试才能 monkeypatch。)

- [ ] **Step 4: 实现入口**

在 `backend/app/routers/inquiry.py` 末尾(`download_template` 之后)追加:

```python
@router.post("/inquiry/compare-row")
async def compare_inquiry_row(
    row: dict = Body(...),
    user_id: str = Depends(require_user_id),
):
    """对询价表的一行需求,按需触发一次三平台外部比价(京东/震坤行/西域)。

    复用现有比价流程:拼 query → build_comparison_structure(空上下文+不追问)
    → create_draft(inquiry- 前缀 session,不写 t_chat_message、不污染对话历史)
    → start_draft。返回 taskId,前端轮询 GET /api/comparison/tasks/{taskId}。
    """
    品名 = (row.get("需求品名") or "").strip()
    品牌 = (row.get("需求品牌") or "").strip()
    型号 = (row.get("需求型号") or "").strip()
    query = " ".join(p for p in [品牌, 品名, 型号] if p)
    if not query:
        return {"ok": False, "guidance": "该行无品名,无法外部比价"}

    result = await build_comparison_structure(
        query, conversation_context=[], memory_context="", skip_clarification=True
    )
    if not result.shouldCreateDraft or not result.structure:
        return {"ok": False, "guidance": result.guidance or "该行需求过于宽泛,无法外部比价,请补充品名/型号"}

    db_user_id = _require_db_user_id(user_id)
    session_id = f"inquiry-{db_user_id}-{uuid.uuid4().hex}"
    draft = await create_draft(
        user_id=user_id, session_id=session_id, raw_query=query, structure=result.structure
    )
    task = await start_draft(draft["id"], user_id)
    if not task:
        return {"ok": False, "guidance": "比价任务创建失败,请重试"}
    return {"ok": True, "taskId": task["id"], "draftId": draft["id"]}
```

同时确认 `Body` 已导入:把顶部 `from fastapi import APIRouter, Depends, File, HTTPException, UploadFile` 改为追加 `Body`:

```python
from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
```

- [ ] **Step 5: 跑测试确认通过**

Run: `cd backend && /Users/summer/anaconda3/bin/python -m pytest tests/test_inquiry.py -v`
Expected: PASS —— 3 passed

- [ ] **Step 6: 防回归 + 提交**

```bash
cd /Users/summer/mro-agent
/Users/summer/anaconda3/bin/python -m pytest backend/tests/test_inquiry.py backend/tests/test_comparison_draft_service.py -q
git add backend/app/routers/inquiry.py backend/tests/test_inquiry.py
git commit -m "feat(inquiry): 加 /inquiry/compare-row 入口——逐行复用比价流程"
```
Expected: 测试全绿。

---

## Task 2: 前端 `compareInquiryRow()` API 封装

**Files:**
- Modify: `frontend/src/services/api.ts`

- [ ] **Step 1: 加 API 函数与返回类型**

在 `frontend/src/services/api.ts` 末尾追加(`API_BASE`、`authHeader`、`responseText` 均已在该文件可用):

```typescript
export interface CompareRowResponse {
  ok: boolean;
  taskId?: string;
  draftId?: string;
  guidance?: string;
}

export async function compareInquiryRow(row: {
  需求品名?: string;
  需求品牌?: string;
  需求型号?: string;
}): Promise<CompareRowResponse> {
  const response = await fetch(`${API_BASE}/inquiry/compare-row`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(row),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "外部比价启动失败"));
  }
  return response.json();
}
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc -b`
Expected: 无错误(0 输出)。

- [ ] **Step 3: 提交**

```bash
cd /Users/summer/mro-agent
git add frontend/src/services/api.ts
git commit -m "feat(inquiry): 前端 compareInquiryRow API 封装"
```

---

## Task 3: InquiryPage —— 行比价状态 + 「外部比价」按钮 + 触发

**Files:**
- Modify: `frontend/src/components/InquiryPage.tsx`

- [ ] **Step 1: 扩展 InquiryRow 类型 + 引入依赖**

在 `frontend/src/components/InquiryPage.tsx` 顶部,给 `InquiryRow` 接口加可选字段(用于断点恢复):

```typescript
interface InquiryRow {
  index: number;
  input: { 需求品名?: string; 需求品牌?: string; 需求型号?: string; 采购数量?: string };
  matches: SkuMatch[];
  match_count: number;
  matched: boolean;
  compareTaskId?: string;  // 已触发外部比价的 taskId,持久化用于关页面重开接回
}
```

在文件 import 区追加:

```typescript
import { compareInquiryRow, getComparisonTask } from "../services/api";
import ComparisonTaskCard from "./ComparisonTaskCard";
import { ComparisonTask } from "../types";
```

- [ ] **Step 2: 加行比价状态 + ref**

在组件内(与其它 `useState` 并列处)加:

```typescript
  // 行外部比价状态:rowIndex → { taskId, task, loading, error }
  interface RowCompare {
    taskId: string;
    task: ComparisonTask | null;
    loading: boolean;
    error?: string;
  }
  const [rowCompare, setRowCompare] = useState<Map<number, RowCompare>>(new Map());
  const rowCompareRef = useRef(rowCompare);
  useEffect(() => { rowCompareRef.current = rowCompare; }, [rowCompare]);
```

- [ ] **Step 3: 触发外部比价的 handler**

在组件内(与 `toggleRow` 并列处)加:

```typescript
  const handleCompareRow = useCallback(async (row: InquiryRow) => {
    // 强制展开该行(库内无匹配的行也能看外部结果)
    setExpandedRows((prev) => new Set(prev).add(row.index));
    setRowCompare((prev) => new Map(prev).set(row.index, { taskId: "", task: null, loading: true }));
    try {
      const resp = await compareInquiryRow(row.input);
      if (!resp.ok || !resp.taskId) {
        setRowCompare((prev) => new Map(prev).set(row.index, {
          taskId: "", task: null, loading: false, error: resp.guidance || "无法比价",
        }));
        return;
      }
      setRowCompare((prev) => new Map(prev).set(row.index, { taskId: resp.taskId!, task: null, loading: false }));
      // 持久化 taskId(断点恢复)—— Task 5 实现 persistCompareTaskId,此处先调用
      persistCompareTaskId(row.index, resp.taskId!);
    } catch {
      setRowCompare((prev) => new Map(prev).set(row.index, {
        taskId: "", task: null, loading: false, error: "比价启动失败,请重试",
      }));
    }
  }, [persistCompareTaskId]);
```

(deps 含 `persistCompareTaskId`:Task 5 把它从占位换成真实实现/依赖 `currentHistoryId` 后,`handleCompareRow` 会随之更新,避免 stale closure。)

注意:`persistCompareTaskId` 在 Task 5 定义。为保持本 task 可独立 `tsc -b` 通过,**本 task 先加一个占位实现**(Task 5 再补全):

```typescript
  const persistCompareTaskId = useCallback((_idx: number, _taskId: string) => {
    // Task 5 补全:写入 result.rows[idx].compareTaskId + 同步 history + saveHistory
  }, []);
```

(把 `persistCompareTaskId` 定义放在 `handleCompareRow` 之前,避免 TS 使用前定义告警;两者都用 `useCallback`。)

- [ ] **Step 4: 行可展开条件 + 「外部比价」按钮**

把行汇总 `div` 的展开点击条件(当前 `onClick={() => row.match_count > 0 && toggleRow(row.index)}`)改为允许"有外部比价的行"也能 toggle:

```tsx
                      onClick={() => (row.match_count > 0 || rowCompare.has(row.index)) && toggleRow(row.index)}
```

把表头与每行的 grid 模板从 `"50px 1fr 100px 130px 80px 60px"` 改为 `"50px 1fr 90px 110px 70px 96px"`(给按钮腾列;表头那一行与数据行两处都改)。

把行汇总最后一列(原本只放展开箭头的 `<span>`)替换为「外部比价」按钮 + 箭头:

```tsx
                      <span style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: 6 }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleCompareRow(row); }}
                          disabled={rowCompare.get(row.index)?.loading}
                          title="对该行触发京东/震坤行/西域外部比价"
                          style={{
                            border: "1px solid var(--border)", borderRadius: 6,
                            background: "transparent", color: "var(--accent)",
                            cursor: "pointer", fontSize: 11.5, padding: "3px 8px", whiteSpace: "nowrap",
                          }}
                        >
                          🔍 比价
                        </button>
                        {(row.match_count > 0 || rowCompare.has(row.index)) && (
                          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2" strokeLinecap="round" style={{ transform: expanded ? "rotate(180deg)" : "none", transition: "transform 0.2s" }}>
                            <path d="M6 9l6 6 6-6" />
                          </svg>
                        )}
                      </span>
```

- [ ] **Step 5: 类型检查**

Run: `cd frontend && npx tsc -b`
Expected: 无错误。(此时点「🔍 比价」会调后端拿到 taskId、行展开,但结果区与轮询在 Task 4 才加,卡片暂不显示;占位 persist 不报错。)

- [ ] **Step 6: 提交**

```bash
cd /Users/summer/mro-agent
git add frontend/src/components/InquiryPage.tsx
git commit -m "feat(inquiry): 行内「外部比价」按钮 + 触发与行比价状态"
```

---

## Task 4: InquiryPage —— 轮询 + 行内展开渲染比价结果

**Files:**
- Modify: `frontend/src/components/InquiryPage.tsx`

- [ ] **Step 1: 加轮询(照搬 ChatWindow 模式)**

在组件内加(`useMemo` 需从 react 引入——把顶部 `import { useState, useRef, useCallback, useEffect } from "react";` 改为追加 `useMemo`):

```typescript
  // 仅当"活跃比价行集合"变化时重建轮询定时器,避免每次 setRowCompare 都重建
  const activeCompareKey = useMemo(
    () =>
      Array.from(rowCompare.entries())
        .filter(([, c]) => c.taskId && (!c.task || ["queued", "running", "partial"].includes(c.task.status)))
        .map(([idx, c]) => `${idx}:${c.taskId}:${c.task?.status ?? "new"}`)
        .join(","),
    [rowCompare],
  );

  useEffect(() => {
    if (!activeCompareKey) return;
    const timer = window.setInterval(async () => {
      const active = Array.from(rowCompareRef.current.entries()).filter(
        ([, c]) => c.taskId && (!c.task || ["queued", "running", "partial"].includes(c.task.status)),
      );
      if (active.length === 0) return;
      const updates = await Promise.allSettled(active.map(([, c]) => getComparisonTask(c.taskId)));
      setRowCompare((prev) => {
        const next = new Map(prev);
        active.forEach(([idx], i) => {
          const u = updates[i];
          if (u.status === "fulfilled") {
            const cur = next.get(idx);
            if (cur) next.set(idx, { ...cur, task: u.value });
          }
        });
        return next;
      });
    }, 2500);
    return () => window.clearInterval(timer);
  }, [activeCompareKey]);
```

- [ ] **Step 2: 行内展开区渲染比价结果**

把现有展开区(当前 `{expanded && row.matches.length > 0 && ( ... )}`)改为:展开条件放宽到"有外部比价也展开",并在库内匹配下方加比价结果区。将该块整体替换为:

```tsx
                    {/* Expanded area: 库内匹配 + 外部比价 */}
                    {expanded && (row.matches.length > 0 || rowCompare.has(row.index)) && (
                      <div style={{ background: "#f8f9fb", borderTop: `1px solid ${borderColor}`, padding: "8px 16px 12px 66px" }}>
                        {row.matches.length > 0 && (
                          <>
                            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8, fontFamily: "var(--mono)" }}>
                              库内匹配（共 {row.match_count} 个，显示前 5）
                            </div>
                            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                              {row.matches.map((m) => (
                                <div key={m.item_code} style={{ display: "grid", gridTemplateColumns: "110px 1fr 100px 120px", gap: 8, background: "var(--surface)", border: `1px solid ${borderColor}`, borderRadius: 6, padding: "8px 12px", fontSize: 12.5 }}>
                                  <span style={{ fontFamily: "var(--mono)", color: "var(--accent)", fontWeight: 500 }}>{m.item_code}</span>
                                  <span style={{ color: "var(--text-primary)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.item_name}</span>
                                  <span style={{ color: "var(--text-secondary)" }}>{m.brand_name || "—"}</span>
                                  <span style={{ color: "var(--text-muted)", fontFamily: "var(--mono)", fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{m.specification || m.mfg_sku || "—"}</span>
                                </div>
                              ))}
                            </div>
                          </>
                        )}

                        {rowCompare.has(row.index) && (
                          <div style={{ marginTop: row.matches.length > 0 ? 14 : 0 }}>
                            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 8, fontFamily: "var(--mono)" }}>
                              外部比价（京东 / 震坤行 / 西域）
                            </div>
                            {(() => {
                              const rc = rowCompare.get(row.index)!;
                              if (rc.loading) return <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>正在发起外部比价…</div>;
                              if (rc.error) return <div style={{ fontSize: 12.5, color: "#b45309" }}>{rc.error}</div>;
                              if (rc.task) return <ComparisonTaskCard task={rc.task} />;
                              return <div style={{ fontSize: 12.5, color: "var(--text-muted)" }}>正在查询…</div>;
                            })()}
                          </div>
                        )}
                      </div>
                    )}
```

- [ ] **Step 3: 类型检查**

Run: `cd frontend && npx tsc -b`
Expected: 无错误。

- [ ] **Step 4: 提交**

```bash
cd /Users/summer/mro-agent
git add frontend/src/components/InquiryPage.tsx
git commit -m "feat(inquiry): 轮询比价 task + 行内展开渲染 ComparisonTaskCard"
```

---

## Task 5: InquiryPage —— taskId 持久化 + 关页面断点恢复

**Files:**
- Modify: `frontend/src/components/InquiryPage.tsx`

- [ ] **Step 1: 加 currentHistoryId 关联当前 result 与 history 条目**

在组件内加 state:

```typescript
  // 当前展示的 result 对应的 history 条目 id,持久化 compareTaskId 时定位该条目
  const [currentHistoryId, setCurrentHistoryId] = useState<string>("");
```

在 `processFile` 成功分支,把现有 history 写入改为先算出 id 并记住(替换 line 128-132 那段):

```typescript
      const data: InquiryResult = await res.json();
      const entryId = Date.now().toString(36);
      setResult(data);
      setCurrentHistoryId(entryId);
      setHistory((h) => [
        { id: entryId, filename: file.name, total: data.total, matched: data.matched, time: Date.now(), result: data },
        ...h.slice(0, 19),
      ]);
```

在 history 项点击恢复处(当前 `onClick={() => { setResult(h.result); setError(""); window.scrollTo(...) }}`)追加记住其 id:

```tsx
                      onClick={() => { setResult(h.result); setCurrentHistoryId(h.id); setError(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}
```

- [ ] **Step 2: 补全 persistCompareTaskId(替换 Task 3 的占位实现)**

```typescript
  const persistCompareTaskId = useCallback((idx: number, taskId: string) => {
    // 1) 更新当前 result 中该行的 compareTaskId
    setResult((prev) => {
      if (!prev) return prev;
      const rows = prev.rows.map((r) => (r.index === idx ? { ...r, compareTaskId: taskId } : r));
      return { ...prev, rows };
    });
    // 2) 同步进 history 对应条目并落 localStorage(关页面后可恢复)
    setHistory((prev) => {
      const next = prev.map((e) =>
        e.id === currentHistoryId
          ? { ...e, result: { ...e.result, rows: e.result.rows.map((r) => (r.index === idx ? { ...r, compareTaskId: taskId } : r)) } }
          : e,
      );
      saveHistory(next);
      return next;
    });
  }, [currentHistoryId]);
```

(删除 Task 3 Step 3 里的占位 `persistCompareTaskId`。)

- [ ] **Step 3: 断点恢复 —— result 变化时,对有 compareTaskId 的行重新接回轮询**

在组件内加:

```typescript
  // result 设定后(upload 完成 / 从历史恢复 / 刷新后点历史),把已比价过的行重新挂上轮询
  useEffect(() => {
    if (!result) return;
    setRowCompare((prev) => {
      const next = new Map(prev);
      result.rows.forEach((r) => {
        if (r.compareTaskId && !next.has(r.index)) {
          next.set(r.index, { taskId: r.compareTaskId, task: null, loading: false });
        }
      });
      return next;
    });
  }, [result]);
```

(轮询 effect(Task 4)会自动接管这些 `task: null` 且有 `taskId` 的行,拉 `get_task` 回填结果;后端 task 一直在 DB,从未丢失。)

- [ ] **Step 4: 类型检查**

Run: `cd frontend && npx tsc -b`
Expected: 无错误。

- [ ] **Step 5: 提交**

```bash
cd /Users/summer/mro-agent
git add frontend/src/components/InquiryPage.tsx
git commit -m "feat(inquiry): compareTaskId 持久化 localStorage + 关页面断点恢复"
```

---

## Task 6: 取消注释批量询价入口

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Step 1: 恢复入口**

`frontend/src/components/Sidebar.tsx` 第 151-153 行(commit `cd0fccf` 注释掉的那行)——删掉三行注释,恢复为一行有效配置:

```tsx
            { view: "inquiry" as const, label: "批量询价", icon: <path strokeLinecap="round" strokeLinejoin="round" d="M9 17v-2m3 2v-4m3 4v-6m2 10H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /> },
```

- [ ] **Step 2: 类型检查**

Run: `cd frontend && npx tsc -b`
Expected: 无错误。

- [ ] **Step 3: 提交**

```bash
cd /Users/summer/mro-agent
git add frontend/src/components/Sidebar.tsx
git commit -m "feat(inquiry): 恢复侧边栏批量询价入口"
```

---

## Task 7: 端到端验证 + 部署(前后端 rebuild)

**Files:** 无(部署 + 验证)

- [ ] **Step 1: 本地全量回归**

```bash
cd /Users/summer/mro-agent/backend && /Users/summer/anaconda3/bin/python -m pytest tests/test_inquiry.py tests/test_comparison_task_service.py tests/test_agent_context.py -q
cd /Users/summer/mro-agent/frontend && npx tsc -b && npm run build
```
Expected: 后端测试全绿;前端 build 成功出 bundle。

- [ ] **Step 2: 推送**

```bash
cd /Users/summer/mro-agent
git -c http.version=HTTP/1.1 push origin main
```

- [ ] **Step 3: 部署(必须 rebuild,前后端;detached + done-marker)**

```bash
sshpass -p 'iwrxZHNX3424' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 root@154.219.114.111 '
  cd /root/mro-agent || exit 1
  git fetch origin >/dev/null 2>&1 && git reset --hard origin/main >/dev/null 2>&1
  echo "HEAD=$(git rev-parse --short HEAD)"
  rm -f /tmp/dep_inq_done
  setsid sh -c "cd /root/mro-agent && docker compose up -d --build backend frontend >>/tmp/dep_inq.log 2>&1; echo DONE > /tmp/dep_inq_done" < /dev/null > /dev/null 2>&1 &
  echo "BUILD_LAUNCHED(detached)"
'
```

- [ ] **Step 4: 等 done-marker + 核对容器内代码**

```bash
sshpass -p 'iwrxZHNX3424' ssh -o StrictHostKeyChecking=no -o ConnectTimeout=20 root@154.219.114.111 '
  for i in $(seq 1 50); do [ -f /tmp/dep_inq_done ] && break; sleep 8; done
  echo "MARKER=$(cat /tmp/dep_inq_done 2>/dev/null || echo NOT_DONE)"
  cd /root/mro-agent && docker compose ps backend frontend | tail -3
  docker compose exec -T backend grep -c "compare-row" /app/app/routers/inquiry.py
'
```
Expected: `MARKER=DONE`;两容器刚重建 Up;backend 含 `compare-row`(≥1)。

- [ ] **Step 5: 线上端到端验证**

后端入口可达性(用账号 13816702381,见 MEMORY):

```bash
/Users/summer/anaconda3/bin/python - <<'PY'
import json, urllib.request
BASE="https://mro.fultek.ai/api"
tok=json.load(urllib.request.urlopen(urllib.request.Request(BASE+"/auth/login",data=json.dumps({"phone":"13816702381"}).encode(),headers={"Content-Type":"application/json"},method="POST"),timeout=30))["auth_token"]
body=json.dumps({"需求品名":"防尘口罩","需求品牌":"3M","需求型号":"KN95"}).encode()
r=json.load(urllib.request.urlopen(urllib.request.Request(BASE+"/inquiry/compare-row",data=body,headers={"Content-Type":"application/json","Authorization":"Bearer "+tok},method="POST"),timeout=90))
print("compare-row:", r)
assert r.get("ok") and r.get("taskId"), "compare-row 应返回 ok+taskId"
t=json.load(urllib.request.urlopen(urllib.request.Request(BASE+"/comparison/tasks/"+r["taskId"],headers={"Authorization":"Bearer "+tok}),timeout=30))
print("task status:", t.get("status"), "subtasks:", [(s.get("platform"), s.get("status"), len(s.get("items") or [])) for s in t.get("subtasks",[])])
PY
```
Expected: `ok:true` + taskId;task 有 jd/zkh/ehsy subtasks(西域应较快出 items)。

- [ ] **Step 6: 前端手动验证(浏览器,硬刷新 Cmd+Shift+R)**

逐项确认:
1. 侧边栏出现「批量询价」入口,点击进入。
2. 上传/粘贴询价表 → 库内匹配结果正常展示(回归)。
3. 某行点「🔍 比价」→ 该行展开,西域先出参考价,京东/震坤行随插件抓取回填。
4. 库内"未找到"的行也能点「🔍 比价」并展开看外部结果。
5. 比价进行中**关闭页面/刷新** → 重开后从「历史」点回该次询价 → 已比价的行自动重新接回结果(后端 task 未丢)。
6. 不污染对话:切到「智能对话」,会话列表无 `inquiry-` 记录。

- [ ] **Step 7: 完成**

无需提交(本 task 仅部署+验证)。部署信息(commit + 分支)汇报给用户。

---

## 自检对照(spec coverage)

- 升级版/三平台:Task 1 复用 start_draft(jd/zkh 插件 + ehsy 注入,三平台)✓
- 单行按需触发:Task 3「🔍 比价」按钮逐行 ✓
- 行内展开 + 复用 ComparisonTaskCard:Task 4 ✓
- 空上下文 + 不追问(无串味):Task 1 实现 + 测试断言 ✓
- inquiry- 会话隔离、不污染对话:Task 1(不写 t_chat_message)+ Task 7 Step6.6 验证 ✓
- 断点恢复(localStorage,不跨设备):Task 5 ✓
- 错误处理(模糊行/失败行不影响他行):Task 1(ok:false 不建 task)+ Task 3/4(行级 error)✓
- 入口恢复:Task 6 ✓
- 非目标(跨设备/一键全表/外部结果导出/数量进召回):均未实现,符合 YAGNI ✓
