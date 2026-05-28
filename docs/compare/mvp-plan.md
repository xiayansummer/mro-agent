# 外部平台比价 MVP 计划

## 目标

把 `/Users/summer/mro-agent` 从“本库 SKU 推荐输出”改造成“外部平台选品比价输出”：

```text
用户输入采购需求
  → 六层结构解析与确认
  → Chrome 扩展检测 JD/ZKH 登录态
  → 扩展访问搜索结果页
  → 回传结构化商品结果
  → 聊天页比价卡片展示结果
```

第一版明确不展示本库 SKU。本库只做品类、规格、品牌、型号和搜索词生成参考。

## 非目标

- 不做后端直连 JD/ZKH 抓取。
- 不做商品详情页抓取。
- 不做 Chrome Web Store 上架阻塞项。
- 不做完整树形类目编辑器。
- 不做多 active 扩展调度。
- 不做复杂 Multi-Agent 编排。
- 不做批量 Excel 比价；现有批量询价能力先保持不变。

## MVP 范围

### 用户体验

所有采购型输入都走外部平台查询流程：

1. 用户在现有聊天页输入需求。
2. 如果无法抽出采购对象，返回引导卡片，不创建比价草稿。
3. 如果能抽出采购对象，创建比价草稿。
4. 聊天页显示六层结构确认卡片。
5. 用户可通过 chip 或局部文本编辑修正低置信字段。
6. 用户确认后，系统检测扩展和平台登录态。
7. 平台未登录时，卡片提示打开平台登录；登录后用户点击重试/重新检测。
8. 扩展抓取搜索结果页前 N 条。
9. 卡片逐步展示平台状态和外部结果。

### 平台范围

- 京东工业：MVP 必做。
- 震坤行：同一套协议预留，建议 M1.5 接入；如果排期紧，先只接 JD 跑通闭环。

### 抓取范围

- 只抓搜索结果页。
- 每个平台最多 3 个搜索词。
- 每个搜索词最多取前 10 条。
- 某个搜索词返回不少于 5 条可解析商品即停止。
- 单平台最多 12 秒。

## 数据模型

### `comparison_drafts`

用于保存结构确认阶段状态。

字段建议：

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar/uuid | 草稿 ID |
| `user_id` | int | 用户 ID |
| `chat_session_id` | varchar | 关联聊天会话 |
| `chat_message_id` | int/null | 关联助手卡片消息 |
| `raw_query` | text | 用户原始输入 |
| `structure_json` | json | `ComparisonStructure` |
| `selected_platforms` | json | `["jd", "zkh"]` |
| `search_terms_json` | json | 平台候选搜索词 |
| `platform_status_json` | json | 扩展检测到的平台登录态 |
| `status` | varchar | `needs_confirmation / needs_login / ready_to_compare / task_created / cancelled` |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

### `comparison_tasks`

用于保存一次真实外部查询。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar/uuid | 任务 ID |
| `draft_id` | varchar/uuid | 草稿 ID |
| `user_id` | int | 用户 ID |
| `status` | varchar | `queued / running / partial / done / failed / cancelled` |
| `created_at` | datetime | 创建时间 |
| `completed_at` | datetime/null | 完成时间 |

### `comparison_subtasks`

每个平台一条子任务。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar/uuid | 子任务 ID |
| `task_id` | varchar/uuid | 任务 ID |
| `platform` | varchar | `jd / zkh` |
| `status` | varchar | `queued / in_progress / login_required / done / timeout / failed` |
| `search_terms_json` | json | 该平台搜索词 |
| `items_json` | json | `ExternalOffer[]` |
| `error_json` | json/null | 错误码和错误上下文 |
| `leased_until` | datetime/null | 扩展短租约 |
| `created_at` | datetime | 创建时间 |
| `updated_at` | datetime | 更新时间 |

### `extension_sessions`

Chrome 扩展绑定状态。

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | varchar/uuid | 扩展 session ID |
| `user_id` | int | 用户 ID |
| `ext_token_hash` | varchar | 扩展 token 哈希 |
| `device_name` | varchar | 设备名 |
| `browser` | varchar | 固定为 Chrome，预留 |
| `active` | boolean | 是否当前 active 扩展 |
| `status_json` | json | 平台登录态、版本、最近错误 |
| `last_seen_at` | datetime | 最近心跳/轮询时间 |
| `created_at` | datetime | 创建时间 |

### `extension_pairing_codes`

一次性配对码。

| 字段 | 类型 | 说明 |
|---|---|---|
| `code_hash` | varchar | 6 位码哈希 |
| `user_id` | int | 用户 ID |
| `expires_at` | datetime | 5 分钟过期 |
| `used_at` | datetime/null | 使用时间 |
| `created_at` | datetime | 创建时间 |

## API 草案

### Web 侧

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/comparison/drafts` | 从用户输入创建六层结构草稿 |
| `GET` | `/api/comparison/drafts/{id}` | 获取草稿 |
| `PATCH` | `/api/comparison/drafts/{id}` | 修改结构、平台、采购约束 |
| `POST` | `/api/comparison/drafts/{id}/start` | 确认草稿并创建任务 |
| `GET` | `/api/comparison/tasks/{id}` | 查询任务和结果 |
| `POST` | `/api/extension/pairing-code` | 创建扩展配对码 |
| `GET` | `/api/extension/status` | 当前用户 active 扩展状态 |

### 扩展侧

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/extension/register` | 用配对码注册扩展，返回 `ext_token` |
| `POST` | `/api/extension/status` | 上报扩展和平台登录态 |
| `GET` | `/api/extension/tasks/next` | 拉取下一条平台子任务 |
| `POST` | `/api/extension/subtasks/{id}/progress` | 上报抓取进度 |
| `POST` | `/api/extension/subtasks/{id}/results` | 回传结构化结果 |
| `POST` | `/api/extension/subtasks/{id}/fail` | 回传失败、超时、登录失效 |

## 后端服务划分

新增模块建议：

```text
backend/app/routers/comparison.py
backend/app/routers/extension.py
backend/app/services/comparison_structure.py
backend/app/services/comparison_query_builder.py
backend/app/services/comparison_ranker.py
backend/app/services/comparison_task_service.py
backend/app/services/extension_service.py
backend/app/services/platform_offer_schema.py
```

复用现有模块：

- `intent_parser.py`：抽取采购对象、品类、规格。
- `normalization.py`：品牌、类目同义词。
- `sku_search.py`：只作为类目/规格归一化参考，不返回本库 SKU 给前端。
- `chat_history_service.py`：保存比价卡片消息，并用于恢复上下文。
- `memory_service.py`：后续可保存比价结果和偏好。

## 前端改造

聊天页新增消息卡片类型：

- `comparisonDraftCard`
- `comparisonTaskCard`

卡片状态：

| 状态 | UI |
|---|---|
| `needs_confirmation` | 六层结构、候选 chip、规格/约束编辑 |
| `needs_login` | 平台登录态、打开平台登录、重新检测 |
| `ready_to_compare` | 开始比价按钮 |
| `running` | 平台子状态、进度、partial results |
| `done` | 对比表、排序、匹配原因 |
| `failed` | 错误、重试按钮 |

前端无需新增独立页面，仍在聊天页内完成。

## 扩展 MVP 行为

### 注册绑定

1. Web 登录用户生成配对码。
2. 用户在 Chrome 扩展 popup 输入配对码。
3. 扩展获得 `ext_token` 并保存到 `chrome.storage.local`。
4. 后端撤销旧 active 扩展，只保留最新 active 扩展。

### 轮询任务

- 扩展每 3 秒调用 `/api/extension/tasks/next`。
- 没任务时返回 204。
- 拿到任务后设置租约，防止重复执行。
- 扩展执行完成后回写结果。

### 登录态

- 扩展在结构确认阶段前后上报 JD/ZKH 登录态。
- 未登录时不执行平台搜索，返回 `login_required`。
- 用户登录完成后，在 Web 卡片点击重新检测/重试。
- MVP 不做 cookie 监听自动恢复。

## 验收标准

MVP 结束时必须满足：

1. 用户在聊天页输入一个明确采购需求。
2. 系统展示六层结构确认卡片。
3. 用户确认后，后端创建比价任务。
4. Chrome 扩展拉取 JD 子任务并访问搜索结果页。
5. 扩展回传不少于 1 条结构化 `ExternalOffer`。
6. 聊天页卡片展示平台结果、匹配原因、价格、单位、货期、链接。
7. 用户刷新页面后，草稿/任务/结果能从后端恢复。
8. 未登录平台时，卡片提示登录并保留原查询内容。

## 风险

| 风险 | MVP 应对 |
|---|---|
| MV3 service worker 被挂起 | 短轮询拉任务，任务有租约 |
| 平台页面结构变更 | 解析器版本化，fixture HTML 回归 |
| 企业价/登录态不稳定 | 使用用户本机 Chrome 会话 |
| 用户不装扩展 | 聊天卡片内明确提示“需要扩展获取账号可见价格” |
| 单位不可比 | 不猜测，标记 `unitComparable=false` |
| 非采购输入 | 返回引导卡片，不创建草稿 |

## 后续演进

- 接入震坤行适配器。
- 登录失效自动监听 cookie 并恢复。
- 批量 Excel 比价。
- 比价历史和导出。
- 调试模式和解析失败样本回传。
- 从单 Orchestrator 演进到 Requirement / Platform / Comparison 多 Agent。
