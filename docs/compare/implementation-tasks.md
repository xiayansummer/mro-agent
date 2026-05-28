# 外部平台比价实施任务拆解

## 原则

- 基于现有 `mro-agent` 改造，不另起后端项目。
- 第一版只要求跑通聊天页内 JD 外部结果闭环。
- 不展示本库 SKU。
- 所有任务都应围绕“可端到端验证”的垂直切片拆分。

## M0：协议、Schema、骨架

### CMP-001 定义共享数据模型

**范围**

- 在后端定义 `ComparisonStructure`、`ExternalOffer`、draft/task/subtask 状态枚举。
- 前端 TypeScript 类型同步定义。
- 约定 JSON 字段命名和必填字段。

**验收**

- 后端 Pydantic / typing 类型可导入。
- 前端 `npm run build` 类型通过。
- 文档中 `docs/adr/001-external-comparison-via-chrome-extension.md` 的模型与代码一致。

### CMP-002 新增数据库迁移

**范围**

- `comparison_drafts`
- `comparison_tasks`
- `comparison_subtasks`
- `extension_sessions`
- `extension_pairing_codes`

**验收**

- 迁移可在空库执行。
- 迁移重复执行不破坏已有表。
- 关键索引包含 `user_id`、`status`、`draft_id`、`task_id`、`active`、`expires_at`。

### CMP-003 新增后端 router 骨架

**范围**

- `backend/app/routers/comparison.py`
- `backend/app/routers/extension.py`
- 注册到 `backend/app/main.py`。

**验收**

- `GET /api/comparison/health` 返回 OK。
- `GET /api/extension/health` 返回 OK。
- 需要用户身份的接口复用 `require_user_id`。

### CMP-004 新增前端比价卡片骨架

**范围**

- 增加 `comparisonDraftCard` / `comparisonTaskCard` 类型。
- 在 `MessageBubble` 或专门组件里渲染空状态卡片。

**验收**

- 可用 mock message 在聊天页渲染结构确认卡片。
- 不影响普通消息、SKU card、slot card 现有渲染。

## M1：六层结构草稿闭环

### CMP-101 六层结构解析服务

**范围**

- 新增 `comparison_structure.py`。
- 复用 `intent_parser.py` 和 `normalization.py`。
- 输出 `l1-l4 + specification + purchaseConstraints`。
- 信息不足时输出引导原因，不创建草稿。

**验收**

- 输入 `M8 304 外六角螺栓 30mm` 能生成品类、产品类型、规格、材质。
- 输入 `你好` 不创建草稿，返回引导消息。
- 单元测试覆盖明确采购需求、信息不足、低置信类目。

### CMP-102 搜索词生成服务

**范围**

- 新增 `comparison_query_builder.py`。
- 每个平台生成 2–3 个候选搜索词。
- 从精确到宽泛排序。

**验收**

- 有品牌时优先输出 `品牌 + 产品类型 + 规格核心`。
- 无品牌时不塞空字段。
- 不把完整 `l1-l4` 原样塞进平台搜索词。

### CMP-103 创建和更新 comparison draft

**范围**

- `POST /api/comparison/drafts`
- `GET /api/comparison/drafts/{id}`
- `PATCH /api/comparison/drafts/{id}`

**验收**

- draft 按用户隔离。
- 创建后保存原始输入、结构、搜索词、状态。
- 更新结构后重新生成搜索词。
- 非 owner 访问返回 404 或 403。

### CMP-104 聊天输入默认进入比价草稿

**范围**

- 改造聊天主流程：采购型输入创建 comparison draft，而不是默认输出本库 SKU。
- assistant message 保存/返回比价草稿卡片 payload。

**验收**

- 用户输入采购需求后，聊天页出现结构确认卡片。
- 不展示本库 SKU。
- 刷新后可从服务端历史恢复卡片。

## M2：Chrome 扩展绑定和登录态

### CMP-201 配对码绑定接口

**范围**

- `POST /api/extension/pairing-code`
- `POST /api/extension/register`
- 生成 `ext_token`，仅保存哈希。
- 新扩展注册后撤销旧 active 扩展。

**验收**

- 配对码 5 分钟过期。
- 配对码只能使用一次。
- 用户最多一个 active 扩展。
- Web token 不暴露给扩展。

### CMP-202 扩展状态接口

**范围**

- `POST /api/extension/status`
- `GET /api/extension/status`
- 保存版本、设备名、JD/ZKH 登录态、最近心跳。

**验收**

- Web 可显示 active 扩展在线/离线。
- 平台登录态可显示在比价卡片。
- 扩展离线超过阈值时前端提示。

### CMP-203 Chrome 扩展脚手架

**范围**

- 新增扩展目录。
- Manifest V3。
- Popup 输入配对码。
- `chrome.storage.local` 保存 `ext_token`。

**验收**

- Chrome 可以加载 unpacked 扩展。
- Popup 可完成配对。
- 扩展能上报状态。

### CMP-204 平台登录态检测

**范围**

- 扩展检测 JD/ZKH 登录态。
- MVP 可用轻量探测 URL 或页面特征。

**验收**

- 未登录时返回 `loggedIn=false`。
- 已登录时返回 `loggedIn=true`。
- 检测失败返回 `unknown`，不误报登录。

## M3：JD 外部结果闭环

### CMP-301 创建任务和子任务

**范围**

- `POST /api/comparison/drafts/{id}/start`
- 为 selected platforms 创建子任务。
- 检查 active 扩展和平台登录态。

**验收**

- 未绑定扩展时 draft/task 显示需要安装扩展。
- 平台未登录时子任务为 `login_required`。
- 已就绪时子任务为 `queued`。

### CMP-302 扩展短轮询拉任务

**范围**

- `GET /api/extension/tasks/next`
- 子任务租约 `leased_until`。
- 防重复派发。

**验收**

- 无任务返回 204。
- 有任务返回平台、搜索词、子任务 ID。
- 租约未过期时不会被重复派发。

### CMP-303 JD 搜索结果页适配器

**范围**

- 扩展访问 JD 工业搜索结果页。
- 按搜索词顺序尝试。
- 解析前 10 条搜索结果。
- 命中足够时停止。

**验收**

- 至少 5 个测试关键词能返回结构化结果。
- 不进入详情页。
- 不上传 cookie/HTML 原文。
- 解析失败有错误码。

**验收命令**

```bash
node extension/chrome/scripts/validate-jd-search.mjs
```

默认关键词见 `extension/chrome/README.md`。脚本通过本机 Chrome 打开 JD 搜索结果页并复用扩展内同一套 parser，报告输出到 `extension/chrome/validation/jd-search-real-report.json`。JD 搜索页要求登录时，用 `--headless false --user-data-dir <dir> --login-wait-ms 120000` 建立独立验证 profile。

### CMP-304 回写结果和任务状态

**范围**

- `POST /api/extension/subtasks/{id}/progress`
- `POST /api/extension/subtasks/{id}/results`
- `POST /api/extension/subtasks/{id}/fail`

**验收**

- 扩展只能回写自己用户的任务。
- 重复回写不产生重复结果。
- 任务状态从 subtask 聚合更新。
- 前端能看到 partial results。

### CMP-305 外部结果匹配排序

**范围**

- 新增 `comparison_ranker.py`。
- 根据六层结构计算 `matchScore` 和 `matchReasons`。
- 单位可比时做保守单价折算。

**验收**

- 明确规格匹配结果排在价格低但规格不匹配结果之前。
- 单位不可比不参与低价排序。
- UI 展示匹配原因。

## M4：聊天页结果体验

### CMP-401 比价任务卡片

**范围**

- 展示平台子状态。
- 展示登录失效、重试、重新检测。
- 展示 partial results。

**验收**

- JD 先返回时能先展示，不等 ZKH。
- 平台失败不影响其他平台结果展示。
- 用户刷新页面后状态恢复。

### CMP-402 对比表组件

**范围**

- 展示 `ExternalOffer` 列表。
- 字段：平台、标题、品牌、规格、价格、单位、货期、库存、匹配原因、链接。

**验收**

- 默认按 `matchScore` 排序。
- 可点击打开外部商品链接。
- 单位不可比有明确标记。

### CMP-403 登录失效重试

**范围**

- 平台 `login_required` 时提示打开平台登录。
- 用户登录后点击“重新检测”或“重试该平台”。
- 保留原 draft、搜索词和任务上下文。

**验收**

- 用户不需要重新输入查询内容。
- 重试只重试失败平台。
- 重试后结果合并进原卡片。

## M5：震坤行和稳定性

### CMP-501 ZKH 搜索结果页适配器

**范围**

- 复用 JD 适配器协议。
- 解析震坤行搜索结果页。

**验收**

- 至少 5 个测试关键词返回结构化结果。
- 单价单位不确定时 `unitComparable=false`。

### CMP-502 Fixture 回归测试

**范围**

- 保存脱敏搜索结果 HTML fixture。
- 给 JD/ZKH parser 建单元测试。

**验收**

- 页面结构变更能被测试捕获。
- parser 覆盖成功、空结果、登录失效、解析失败场景。

### CMP-503 结果历史和导出

**范围**

- 比价任务历史。
- 导出 CSV/XLSX。

**验收**

- 用户可从聊天历史恢复结果。
- 可导出当前比价表。

## 推荐实施顺序

1. `CMP-001` → `CMP-002` → `CMP-003`
2. `CMP-101` → `CMP-102` → `CMP-103`
3. `CMP-104` → `CMP-004`
4. `CMP-201` → `CMP-202` → `CMP-203`
5. `CMP-301` → `CMP-302` → `CMP-303` → `CMP-304`
6. `CMP-305` → `CMP-401` → `CMP-402` → `CMP-403`
7. `CMP-501` → `CMP-502` → `CMP-503`

## MVP Done Definition

- 聊天页输入采购需求后，不展示本库 SKU。
- 六层结构卡片可确认。
- Chrome 扩展可绑定并拉取任务。
- JD 搜索结果页可返回结构化结果。
- 聊天页展示对比结果卡片。
- 刷新页面不丢草稿、任务、结果。
- 未登录平台不丢查询内容，可登录后重试。
- 后端和前端关键路径有测试。
