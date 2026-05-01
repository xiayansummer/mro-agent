# 5 维参数追问 chip 化 + 搜索鲁棒性增强（v1.2）

**日期**: 2026-05-01
**作者**: summer + Claude
**状态**: 设计已确认，待实施
**关联**: 借鉴京东工业品 mro-bom.jd.com 的 chip 追问与品牌别名解析模式

---

## 1. 背景与问题

### 1.1 现状

当前 MRO Agent 在 `intent_parser` 输出 `need_clarification=true` 时，让 LLM 输出一个 5 维 Markdown 表格作为 `clarification_question`，表格三列（参数 / 当前已知 / 需要确认）。前端 `MessageBubble.tsx` 直接 markdown 渲染，无任何交互 — 用户看到选项后必须手动打字答复。

### 1.2 痛点

1. **追问交互过原始** — 选项以纯文本展示，用户每次得手输内容，体验远落后于业内同类产品（如 JD 工业品的 chip 化追问）
2. **品牌识别脆弱** — 实测中"TOHO"、"美和TOHO"等品牌别名无法匹配 DB 里的标准品牌名"美和"，用户问了 5 轮才搜到货
3. **Brand-only 查询无降级** — 用户只给品牌不给品类时，系统反复追问而不是返回该品牌下的品类聚类供用户选择
4. **品类关键词无同义** — "搬运产品"匹配不到 L1 "物料搬运"

### 1.3 目标

把追问 UI 改造为结构化 chip 卡，同时修复搜索引擎的品牌别名 / 品类同义 / brand-only fallback 三类鲁棒性问题。两条线在 chip 卡这一层咬合：brand-only fallback 复用 chip 卡渲染品类聚类。

---

## 2. 范围

### 2.1 包含

- `intent_parser.py` 输出 schema 改造：从 schema 移除 `clarification_question` 字段（不再产出 markdown 表格），新增 `slot_clarification` 结构化 JSON 字段。`response_gen.generate_guided_selection_stream` 中 inject markdown 表格的逻辑一并删除。老消息持久化在 `t_chat_message.content` 里的 markdown 表格仍能正常显示（按 markdown 渲染兼容路径）
- 新增 SSE 事件 `slot_clarification`，前端新增 `SlotClarificationCard` 组件
- 后端新增 `data/brand_aliases.json` 和 `data/category_synonyms.json` 数据文件
- `sku_search.py` 增加 brand-only fallback 分支
- `agent.py` query 预处理时归一化品牌与品类
- 持久化：`t_chat_message` 新增 `slot_clarification MEDIUMTEXT` 列
- 老消息兼容：旧 markdown 表格按原样 markdown 渲染

### 2.2 不包含（YAGNI / 后续迭代）

- "查看分析推导过程"折叠步骤条（与 thinking dot 重复）
- chip 智能默认勾选（基于 Memos 用户偏好自动选品牌）→ v1.3
- 移动端 chip 滑动 / 横向滚动优化（默认 flex-wrap 即可）
- 品类聚类计数的精确显示（v1.2 直接拼到 option 文本里，如 "手拉葫芦 (8)"）

---

## 3. 设计决策（已经过用户确认）

| 决策点 | 选择 | 理由 |
|---|---|---|
| chip 点击语义 | **Plan B** — 填入卡片内输入区，可继续输入自由文本，统一提交 | 兼顾快速点选和自由补充（如"长度 50mm，急用"） |
| UI 结构 | **Plan C** — 完全替换 markdown 表格为「需求概述 + 已知参数 + chip 群 + tag pill + 自由输入」 | 去掉表格冗余、保留 JD 精华、不做"分析推导过程"折叠 |
| 同维度多选 | **A — 单选** | 防矛盾表达；用户可在自由文本里说"304 或 316 都行" |
| 跨维度选择 | 累加 | 自然多维补全 |
| 提交输入框 | **chip 卡内独立输入框 + 提交按钮**，不复用主聊天输入框 | 避免与历史消息 chip 状态混淆；卡片自包含 |
| 维度 key 生成 | LLM 自由命名（如 `slip_level` / `size_range`） | JD 第二轮的"脚套材质 / 防滑等级"明显是动态子维度 |
| summary 形式 | 自然语言完整句，每轮重新合成 | 累积消化已知信息（"需要采购给水输送、承插式连接的 50mm PVC 水管"） |
| known 数量 | 不限 | 1-N 视场景而定 |
| 多轮上限 | 最多 3 轮 slot_clarification，超过强制走 SKU 搜索 | 防止用户被反复追问劝退 |
| chip 文本拼接 | 空格分隔 | 比无空格更可读，LLM 解析无差别 |
| 品牌/品类归一化 | JSON 数据字典 + intent_parser & agent.py 预处理 | 维护简单，新增品牌别名只需改 JSON |
| brand-only fallback UI | 复用 SlotClarificationCard，不新建组件 | chip 卡数据契约通用 |

---

## 4. 数据契约

### 4.1 后端 → 前端 SSE 事件

新增事件 `slot_clarification`，payload：

```json
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
    }
  ]
}
```

字段说明：

- `summary`: 自然语言完整句，每轮重新生成，累积消化所有已知信息
- `known[]`: 当前轮已抓取到的结构化字段，{label, value} 形式，长度不限
- `missing[]`: 待补充维度，长度建议 2-4 个
  - `key`: LLM 自由命名（小写下划线 / 简短英文），用于内部追踪，不展示
  - `icon`: emoji，由 LLM 输出，提示词附带常用 icon 参考表
  - `question`: 中文问题
  - `options`: 候选 chip 文本，3-5 个为佳

### 4.2 Brand-only fallback 触发的 payload 形态

后端在 `sku_search.py` 命中 brand-only fallback 分支后，由 agent.py 直接生成 `slot_clarification` 事件：

```json
{
  "summary": "美和品牌下找到 5 类商品",
  "known": [{ "label": "品牌", "value": "美和" }],
  "missing": [
    {
      "key": "category",
      "icon": "📦",
      "question": "请选择具体品类",
      "options": ["手拉葫芦 (8)", "电动葫芦 (3)", "电动单梁起重机 (2)", "钢丝绳 (12)", "其他"]
    }
  ]
}
```

- option 文本里的 `(N)` 是商品数量后缀，纯展示
- 用户点击提交后，下一轮 query 会被 LLM 重新解析为 brand="美和" + category="手拉葫芦"

### 4.3 前端 ChatMessage 类型扩展

```typescript
interface SlotMissing {
  key: string;
  icon: string;
  question: string;
  options: string[];
}

interface SlotClarification {
  summary: string;
  known: { label: string; value: string }[];
  missing: SlotMissing[];
  selected?: Record<string, string>; // chip key → 选中 option 文本
  freeText?: string;                 // 用户自由补充
  submitted?: boolean;               // 是否已提交（freeze 状态）
}

interface ChatMessage {
  // ... existing fields
  slotClarification?: SlotClarification;
}
```

---

## 5. UI 设计

### 5.1 SlotClarificationCard 组件结构

```
┌──────────────────────────────────────┐
│ 需求概述: 需要采购 PVC 水管            │
│                                      │
│ 已知参数:                            │
│   • 商品类型: PVC水管                │
│   • 规格: 50mm                       │
│                                      │
│ 🏭 用于什么场景？                     │
│   [给水输送] [排水排污] [农业灌溉]    │
│   [其他用途]                          │
│                                      │
│ ⚙️ 需要哪种连接方式？                 │
│   [承插式] [法兰连接] [螺纹连接]      │
│   [卡箍连接]                          │
│                                      │
│ ─────────────────────────────────    │
│ 已选: [给水输送 ✕]  [承插式 ✕]        │
│ ┌──────────────────────────────────┐ │
│ │ 自由补充（如长度 50mm、急用…）  ➤│ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

### 5.2 交互细节

- **Chip 视觉态**：未选（灰底圆角，1px 边框）；已选（强调色边框 + 浅背景，下方 tag pill 镜像）
- **同维度切换**：点维度内另一个 chip 即替换当前选中
- **取消选中**：点已选 chip 切回未选；或点 tag pill 上 ✕
- **自由文本**：独立 textarea，提交时与 tag pill 文本按空格拼接
- **提交后**：卡片 freeze 进只读态（chip 不可点、输入框消失、tag pill 保留高亮）；新一轮回复作为下条 assistant 消息正常渲染
- **绕过 chip**：用户在主聊天输入框直接打字发送，当前卡 freeze；后端按新 query 重新走流程

### 5.3 提交流转

用户提交时，前端组合：

```
"<tag pill 文本，空格分隔> <自由文本>"
```

例：tag pill = ["给水输送", "承插式"]，free text = "长度 6 米，急用"
→ 发送内容: `"给水输送 承插式 长度 6 米，急用"`

走标准 `POST /api/chat`，session_id 不变（同一会话内继续）。

---

## 6. 后端搜索鲁棒性增强

### 6.1 brand_aliases.json

位置: `backend/data/brand_aliases.json`

```json
{
  "美和": ["TOHO", "美和TOHO", "美和toho", "东星", "TOHO美和"],
  "NOK": ["耐欧凯", "恩欧凯", "nok"],
  "SKF": ["斯凯孚", "skf"],
  "Festo": ["费斯托", "festo"],
  "SMC": ["速码客", "smc"],
  "Parker": ["派克", "parker"],
  "科德宝": ["Freudenberg", "freudenberg"],
  "博世": ["BOSCH", "bosch"],
  "施耐德": ["Schneider", "schneider"]
}
```

key 是 DB 标准品牌名（与 t_sku.brand_name 一致），value 数组是别名列表。匹配时大小写不敏感。

### 6.2 category_synonyms.json

位置: `backend/data/category_synonyms.json`

```json
{
  "搬运": "物料搬运",
  "搬运产品": "物料搬运",
  "起重": "起重工具及设备",
  "紧固": "紧固密封 框架结构",
  "工具": "工具 工具耗材",
  "存储": "物料搬运 存储包装"
}
```

key 是用户常用简写，value 是 DB 中的标准 L1/L2 名。

### 6.3 intent_parser 改造点

- 增加 brand 解析后的归一化步骤：解析出的 brand 字符串先查 alias 表，命中即替换为标准名（用于下游 SKU search 精确匹配）
- 系统提示新增一段：常见品牌别名（举例 5-8 个）让 LLM 在解析阶段尽量直接输出标准名

### 6.4 agent.py 预处理

在调用 intent_parser 之前对 user_message 做 category 同义替换（仅顶层关键词）：

```python
def normalize_query(msg: str) -> str:
    for syn, std in category_synonyms.items():
        if syn in msg and std not in msg:
            msg = msg.replace(syn, std, 1)
    return msg
```

注意：单向替换，避免双向混淆。

### 6.5 sku_search.py brand-only fallback 分支

```python
async def search_skus(intent: dict) -> tuple[list[Sku], Optional[BrandFallback]]:
    if intent["brand"] and not intent["l1_category"] and not intent["l2_category"]:
        # Brand-only fallback
        rows = await db.fetch(
            "SELECT * FROM t_sku WHERE brand_name = %s LIMIT 50",
            intent["brand"]
        )
        if rows:
            clusters = group_by_l3(rows)  # {l3_name: count}
            return [], BrandFallback(brand=intent["brand"], clusters=clusters)
    # ... 原有逻辑
```

返回 `BrandFallback` 对象时，agent.py 不发 `sku_results` 事件，改发 `slot_clarification`（payload 见 4.2）。

---

## 7. 多轮收敛策略

每轮调用 intent_parser 前，后端先查 `t_chat_message` 表统计当前 session 内 `slot_clarification IS NOT NULL` 的消息条数（即历史轮次）：

- 历史轮次 < 3：根据 intent_parser 的 `need_clarification` 判断是否再发 chip
- 历史轮次 ≥ 3：强制走 SKU 搜索（即使 LLM 仍想追问也忽略），返回当前抓到信息下的最佳匹配商品 + 一条引导文字"已为您匹配最相关商品，可继续描述需求精筛"
- brand-only fallback 也计入轮次（不另算）
- 用户开启新会话 → 自然重置（新 session_id 新计数）

无需引入 redis 或内存 dict —— 直接用持久化表查询，服务重启不丢状态。

---

## 8. 持久化

`t_chat_message` 表新增列：

```sql
ALTER TABLE t_chat_message
ADD COLUMN slot_clarification MEDIUMTEXT NULL
AFTER competitor_results;
```

存储完整的 `SlotClarification` JSON（包含 selected / freeText / submitted 字段）。会话恢复时按 submitted=true 渲染只读卡片。

迁移脚本: `backend/migrations/003_add_slot_clarification.sql`

---

## 9. 老消息兼容

老消息没有 `slot_clarification` 字段（NULL），但 `content` 里可能含旧的 markdown 表格 → 继续按 markdown 渲染（无修改）。新代码读老消息无副作用。

前端渲染逻辑：

```
if (message.slotClarification) {
  return <SlotClarificationCard ... />;
}
// 否则按原 markdown 渲染 message.content
```

---

## 10. 数据流（端到端）

```
[user] 50pvc水管
    ↓
[agent.py] normalize_query → intent_parser
    ↓
[intent_parser LLM] 输出 JSON 含 slot_clarification 字段
    ↓
[agent.py] SSE event=slot_clarification, data=<JSON>
    ↓
[frontend] 新建 ChatMessage with slotClarification, render SlotClarificationCard
    ↓
[user] 点击 chip + 自由输入 + 提交
    ↓ POST /api/chat with composed message
    ↓ PATCH 当前 message.slot_clarification.submitted=true
[backend 持久化] 更新 t_chat_message
    ↓
[第 2 轮 intent_parser] 已知信息更全，再判断 need_clarification
    ↓
[或继续 chip / 或直接 SKU 搜索]
```

---

## 11. 时间表

| 阶段 | 工作量 | 依赖 |
|---|---|---|
| 后端搜索鲁棒性（brand_aliases.json / category_synonyms.json / 归一化逻辑 / brand-only fallback 分支） | 1.5 天 | 无 |
| 后端 chip 数据契约改造（intent_parser JSON schema 重写、新 SSE 事件、多轮计数器） | 1 天 | 无 |
| 前端 SlotClarificationCard 组件 + ChatMessage 类型扩展 | 1.5 天 | 无 |
| 持久化迁移 + chat_history 服务读写适配 | 0.5 天 | 后端 |
| 联调 + brand-only fallback chip variant 测试 + 多轮收敛测试 | 0.5 天 | 全部 |
| **合计** | **~5 天** | |

后端 search 增强与 chip 工作可并行；联调阶段统一对接。

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| LLM 输出 JSON 不规范（缺字段 / 字段类型错） | chip 卡渲染失败 | 后端 schema 校验，校验失败时降级回 markdown 表格（保留 v0 行为做兜底） |
| 品牌别名表覆盖不全 | 部分品牌仍搜不到 | 持续运营维护，从用户反馈中迭代；初期 cover 30 个常用品牌 |
| 多轮 chip 用户疲劳 | 用户跳出 | 3 轮硬上限 + 每轮 missing 限制 2-4 个维度 |
| 老消息 markdown 表格在新前端样式错位 | 历史会话视觉违和 | 前端隔离 CSS scope；保留对老 markdown 的渲染兼容 |
| 同会话切换品类后 known 字段污染 | 错误延续上一品类的已知字段 | intent_parser 系统提示明确：known 仅基于本轮 user message，不沿用历史 |

---

## 13. 后续迭代（v1.3+）

- 基于 Memos 用户偏好自动预选 chip（如品牌偏好默认勾选）
- 移动端 chip 横向滑动优化
- chip 卡支持"跳过此项"按钮（用户明确不知道怎么填时）
- 品类聚类的精确商品数量 API 化（不再拼在 option 文本里）
- 折叠式"分析推导过程"步骤条（如果 agent 流程变得多步）
