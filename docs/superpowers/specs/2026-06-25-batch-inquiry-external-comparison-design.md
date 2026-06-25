# 批量询价升级:库内匹配 + 逐行外部比价 设计文档

**目标:** 重新上线封存的批量询价,并升级为「库内 SKU 批量匹配 + 按需逐行外部比价(京东工业品 / 震坤行 / 西域)」。

**架构一句话:** 上传 Excel → 库内批量匹配(现有)→ 用户对某行点「外部比价」→ 后端为该行复用现有比价流程建 task → 前端轮询 → 行内展开三平台比价结果;taskId 持久化到 localStorage,关页面重开自动接回。

**技术栈:** FastAPI(后端)、React/Vite(前端)、现有 comparison 流程(draft/task/ranker/插件抓取/ehsy 服务端注入)。

---

## 1. 背景与现状

- 批量询价 2026-06-15 被封存(commit `cd0fccf`):**仅注释掉 `Sidebar.tsx` 一行入口**,`InquiryPage` 组件、`inquiry` 路由、后端 `/api/inquiry` 全部保留。
- 封存原因(commit message):旧版**只匹配本库 SKU、不含外部实时比价**,当时计划"重新设计为『库内批量匹配 + 按需逐行外部比价』后再放出"。
- 现状实测(2026-06-25,生产 DB):库内 SKU 批量匹配**可用**(`防尘口罩/螺栓/安全帽/手套/扳手` 5/5 命中)。`sku_search` 已迁到真实存在的表(`t_brand` / `t_category` / `t_item_info` 分片 / `v_item_file`),早期"`t_item_sample` 不存在导致失效"的状态已不成立。
- 旧版流程:上传 Excel(列含「需求品名」「需求品牌」「需求型号」)→ 逐行 `search_skus` → 返回每行匹配结果;另有模板下载 `/api/inquiry/template`。前端 `InquiryPage` 已有行展开机制(`expandedRows`)与 `localStorage` 历史(`mro-inquiry-history`,留 30 条)。

## 2. 已确认的设计决策

| 决策 | 选定 |
|---|---|
| 上线范围 | 升级版(库内匹配 + 逐行外部比价),非仅恢复旧版 |
| 外部比价源 | **三平台全触发**:京东工业品 + 震坤行 + 西域 |
| 触发粒度 | **单行按需**:每行一个「外部比价」按钮,不一键全表(压住 jd/zkh 插件串行排队) |
| 结果展示 | **行内展开**,复用现有 `ComparisonTaskCard` |
| 断点恢复 | `taskId` 持久化到 `localStorage`(行级),同浏览器重开自动接回;**不做跨设备恢复(YAGNI)** |

## 3. 总体流程

```
上传 Excel / 粘贴
   → 库内批量匹配 (POST /api/inquiry/upload,现有,不变)
   → 表格逐行展示库内匹配
        ↓ 用户对某行点「🔍 外部比价」
   → POST /api/inquiry/compare-row (新增,为该行建比价 task)
        · 拼 query → build_comparison_structure (空上下文 + 不追问)
        · create_draft (inquiry- 前缀 session) → start_draft → 返回 taskId
   → 前端存 taskId 到行状态 + localStorage,启动轮询
   → 轮询 GET /api/comparison/tasks/{taskId} (现有,零改动)
        · 西域服务端先秒出;京东/震坤行插件异步抓完回填
   → 行内展开区下半部展示三平台比价结果 (复用 ComparisonTaskCard)
```

## 4. 后端设计

**只新增 1 个入口,其余全复用。**

### 4.1 新入口 `POST /api/inquiry/compare-row`

- **入参**(JSON):`{ "需求品名": str, "需求品牌": str, "需求型号": str }`(与库内匹配同一行结构;`采购数量` v1 不进比价)。
- **流程**:
  1. 拼 `query = " ".join([需求品牌, 需求品名, 需求型号])`(去空)。
  2. `result = await build_comparison_structure(query, conversation_context=[], memory_context="", skip_clarification=True)`
     - **空上下文 + 不追问**:每行独立解析,天然无多轮串味、不会弹追问卡(批量场景不能逐行追问)。
  3. 若 `not result.shouldCreateDraft or not result.structure`(需求太模糊):返回 `{ "ok": false, "guidance": result.guidance or "该行需求过于宽泛,无法外部比价,请补充品名/型号" }`,**不建 task**。
  4. `draft = await create_draft(user_id, session_id=f"inquiry-{db_user_id}-{uuid}", raw_query=query, structure=result.structure)`(`uuid` 服务端生成,仅保证 session id 唯一,不参与业务)
  5. `task = await start_draft(draft["id"], user_id)`
  6. 返回 `{ "ok": true, "taskId": task["id"], "draftId": draft["id"] }`。

### 4.2 会话隔离(不变量)

- 合成 `inquiry-` 前缀 session id 写入 `comparison_drafts.chat_session_id`。
- `compare-row` **不调用** `chat_history_service.save_turn`、**不写** `t_chat_message`。
- 因对话历史列表(`GET /api/chat/sessions`)来自 `t_chat_message`,`inquiry-` 比价**不会出现在对话历史列表**,不污染对话。
- (实现时需断言:`compare-row` 调用链中无任何 `t_chat_message` 写入。)

### 4.3 复用,零改动

- 轮询沿用现有 `GET /api/comparison/tasks/{taskId}`(`get_task`)。
- jd/zkh 经现有插件 `lease → submit` 机制抓取;西域经 `_inject_ehsy_subtask` 服务端注入;排序经 `rank_external_offers`。

## 5. 前端设计(InquiryPage)

### 5.1 行内交互

- 每个库内匹配行加「🔍 外部比价」按钮。
- 点击:`POST /api/inquiry/compare-row` → 拿 `taskId` → 写入该行比价状态(`Map<rowIndex, { taskId, task }>`)→ 持久化(见 5.3)→ 启动轮询。
- 行展开区(复用现有 `expandedRows`):
  - **上半**:库内 SKU 匹配(现有,不变)。
  - **下半**:外部比价结果,**复用 `ComparisonTaskCard`**(三平台 offers / 进度 / 重试 UI 全继承)。
- `ok:false`(需求太模糊):行内显示 `guidance` 提示,不展开比价卡。

### 5.2 轮询(照搬 ChatWindow 模式)

- `setInterval(2500ms)`,对状态为 `queued / running / partial` 的行调 `getComparisonTask(taskId)`,回填行比价状态;`done / failed` 的行停止轮询。
- 多行同时比价时,一个 interval 批量轮询所有活跃行(同 ChatWindow 的 `activeTaskKey` 思路)。

### 5.3 断点恢复(localStorage)

- `InquiryRow` 增加可选字段 `compareTaskId?: string`。
- 点「外部比价」拿到 taskId 后,写入对应行的 `compareTaskId` 并 `saveHistory`(连同库内匹配一起进 `mro-inquiry-history`)。
- 重开页面:`loadHistory` 恢复库内匹配;对有 `compareTaskId` 的行启动轮询 `getComparisonTask` → 已完成的直接回填、未完成的继续轮询。
- **后端 task 始终在 DB(关页面不丢),前端只是重新接线。**

### 5.4 入口恢复

- `Sidebar.tsx` 取消注释「批量询价」入口(commit `cd0fccf` 注释的那行)。

## 6. 异步、状态与错误处理

- **平台时序**:西域服务端先秒出参考价;京东/震坤行插件异步抓完回填。task 状态 `queued → running → partial → done`,`ComparisonTaskCard` 自带进度展示。
- **插件不在线**:jd/zkh 标 `login_required`(现有机制),西域照常出;不阻塞该行其它平台,也不阻塞别的行。
- **单行失败**:某行 parse 失败 / `shouldCreateDraft=False` / 全平台失败 → 行内提示,**不影响其他行**。
- **重复触发**:行已有 `compareTaskId` 且未失败 → 点击直接重新轮询已有 task(不重复建);另提供「重新比价」显式重建(走 `compare-row` 拿新 taskId)。
- **整页健壮**:复用已上线的 `ErrorBoundary`,单行比价卡渲染异常只影响该行,不拖垮整页。

## 7. 测试

- **后端** `tests/test_inquiry.py`(新增用例,mock `build_comparison_structure` / `create_draft` / `start_draft`):
  - 一行需求 → 调用 `compare-row` → 返回 `taskId`;
  - 透传断言:`build_comparison_structure` 收到 `conversation_context=[]` 且 `skip_clarification=True`;
  - session id 以 `inquiry-` 前缀;
  - `shouldCreateDraft=False` 时返回 `ok:false` + guidance,**不调用** `start_draft`。
- **前端**:无测试设施 → `tsc -b` 类型检查 + 部署后端到端验证(上传 → 库内匹配 → 点行外部比价 → 行内出三平台结果 → 关页面重开自动恢复)。

## 8. 复用 / 新增清单

- **复用(零或极小改动)**:`build_comparison_structure`、`create_draft`、`start_draft`、`get_task`、`ComparisonTaskCard`、`OfferRow`、`rank_external_offers`、`_inject_ehsy_subtask`、`ExternalOffer`、`InquiryPage` 的 `expandedRows` 与 `localStorage` 历史、ChatWindow 轮询模式。
- **新增**:后端 1 个入口 `/api/inquiry/compare-row`;前端 InquiryPage 行内「外部比价」按钮 + 轮询 + 结果区 + `compareTaskId` 持久化;`Sidebar.tsx` 取消注释入口。

## 9. 非目标(YAGNI)

- 跨设备 / 跨浏览器恢复(localStorage 单浏览器已够)。
- 一键全表批量触发外部比价(单行按需,压住 jd/zkh 排队)。
- 外部比价结果导出 CSV(现有导出仅含库内匹配,本期不扩展;需要再加)。
- 采购数量进入比价召回 / 单价折算(v1 仅用品名/品牌/型号召回)。
