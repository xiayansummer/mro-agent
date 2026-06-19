# 「换个产品比价」按钮 — 设计文档

> 日期:2026-06-19 · 状态:待评审 · 解决"单会话反复查/精炼时,新产品查询被历史上下文串味"

## 1. 背景与目标

`parse_intent` 用最近 6 轮对话做上下文(`handle_message` 取 `ctx["conversation"][-6:]`)。用户在同一会话里出过比价结果后再打一个**新产品**(如先比"防尘口罩"+精炼"只要3M",再打"防尘口罩"),新查询会把前几轮(KN95/带阀、3M、"未找到")卷进结构 → 串味、误导。自动分清"换新产品"与"接着细化(要304的)"很难且易错,故给用户一条**显式的干净重来**路径。

**目标**:比价结果卡片上加一个「换个产品比价」按钮,点了**新建并切到一个新对话**,新查询天然零上下文。

## 2. 非目标

- 不做"自动检测新产品→重置"(模糊、易误判,YAGNI)。
- 不做原地"上下文边界标记"(需改 DB 加载、复杂)。
- 不改后端(新 session 天然空上下文,见 §3)。

## 3. 架构与数据流(纯前端,零后端改动)

```
[比价结果卡片] 点「换个产品比价」
  → App.handleNewChat()(已存在,侧栏在用)
  → 新建并切到新 session(activeId=新id)
  → ChatWindow key=新id 重挂载,空消息
  → 用户打新产品 → POST /api/chat(新 session_id)
  → get_session_context(新id) 缓存未命中 → _load_session_conversation
    → get_recent_agent_context(新id):该 session 无消息 → []
  → conversation=[] → parse_intent 无历史可串味
```

**为何无需后端改动 / 无需上下文边界标记**:新 `session_id` 在 `t_chat_message` 里无任何行,`get_recent_agent_context` 返回空,内存 `_sessions` 也无该 session 的缓存 → `conversation` 天然为 `[]`。

## 4. 接线(prop 透传)

`handleNewChat` 已在 `App.tsx`(传给 `Sidebar`)。新增一条到比价卡片的透传链:

```
App.handleNewChat
  → ChatWindow         (新增 prop: onNewChat)
  → MessageBubble      (新增 prop: onNewComparison)
  → ComparisonTaskCard (新增 prop: onNewComparison)
  → 按钮 onClick={onNewComparison}
```

`App` 渲染 `ChatWindow` 处把 `onNewChat={handleNewChat}` 传入;`ChatWindow` 渲染 `MessageBubble` 处把它作 `onNewComparison` 传下;`MessageBubble` 渲染 `ComparisonTaskCard` 处再传下。

## 5. UI

- **位置**:比价**任务卡片**(`ComparisonTaskCard`,有 `comparisonTask` 那张)的**页脚**,挨着现有「刷新/重试」操作区。
- **文案**:`🔄 换个产品比价`。
- **显示条件**:卡片存在即显示(不论 task 状态——queued/running/partial/done 都可"换产品")。
- 次要按钮样式,与卡片现有 secondary 按钮一致。

## 6. 行为 / 边界

| 情况 | 行为 |
|---|---|
| 点击 | `handleNewChat()` → 新建/复用空白会话并切过去;旧比价留在左侧历史可切回 |
| 误点 | 非破坏,旧对话在历史里,一键切回 → 不加二次确认 |
| 已有空白新对话(<60s) | `handleNewChat` 既有逻辑会复用它(仍是空上下文)→ 行为正确 |

## 7. 测试

前端无测试框架 → `npm --prefix frontend run build` 通过(0 TS 错误)+ 实操验证:
- 比价出结果 → 卡片上有「换个产品比价」按钮;
- 点击 → 切到新空白对话;
- 在新对话打一个产品 → 结构/slot 概述**不再**带上一轮的历史规格/品牌(对比修复前的串味)。

## 8. 风险

- 仅前端 prop 透传 + 复用 `handleNewChat`,无新错误路径、无后端/DB 改动。
- `handleNewChat` 的"复用 <60s 空白会话"既有行为不变,对本特性无害(复用的也是空上下文)。
