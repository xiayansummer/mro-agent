# 「换个产品比价」按钮 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 比价结果卡片加「🔄 换个产品比价」按钮 → 点击新建对话 → 新查询天然零上下文,避免单会话历史串味。

**Architecture:** 纯前端,零后端改动。把已有的 `App.handleNewChat` 经 prop 透传到比价卡片的按钮:`App → ChatWindow(onNewChat) → MessageBubble(onNewComparison) → ComparisonTaskCard(onNewComparison) → 按钮`。新 session_id 天然空上下文(`get_recent_agent_context` 查不到消息),无需任何后端/边界机制。

**Tech Stack:** React + Vite(TS),无前端测试框架 → 以 `tsc -b && vite build` + 实操验收。

**Spec:** `docs/superpowers/specs/2026-06-19-new-comparison-button-design.md`

> 与 spec §5 的细化:卡片的操作按钮(刷新)在**卡片头部**而非页脚,故「换个产品比价」放在**刷新按钮旁**(spec 的核心意图是"挨着刷新")。

---

## 文件结构

| 改动 | 文件 | 职责 |
|---|---|---|
| 传 prop | `frontend/src/App.tsx` | 渲染 `ChatWindow` 处加 `onNewChat={handleNewChat}` |
| 透传 | `frontend/src/components/ChatWindow.tsx` | Props 加 `onNewChat?`;渲染 `MessageBubble` 处作 `onNewComparison` 传下 |
| 透传 | `frontend/src/components/MessageBubble.tsx` | Props 加 `onNewComparison?`;渲染 `ComparisonTaskCard` 处传下 |
| 加按钮 | `frontend/src/components/ComparisonTaskCard.tsx` | Props 加 `onNewComparison?`;刷新按钮旁加「换个产品比价」 |

---

## Task 1: 透传回调 + 加按钮(一次性原子改动)

四个文件互相依赖(TS 类型链),作为一个原子改动一起完成,最后统一 build。

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/ChatWindow.tsx`
- Modify: `frontend/src/components/MessageBubble.tsx`
- Modify: `frontend/src/components/ComparisonTaskCard.tsx`

- [ ] **Step 1: App.tsx —— 给 ChatWindow 传 onNewChat**

`App.tsx` 渲染 `ChatWindow` 处(现有 `<ChatWindow key={activeSession.id} sessionId=... messages=... onMessagesChange=... onToggleSidebar=... />`)加一行 prop:
```tsx
        <ChatWindow
          key={activeSession.id}
          sessionId={activeSession.id}
          messages={activeSession.messages}
          onMessagesChange={handleMessagesChange}
          onToggleSidebar={handleToggleSidebar}
          onNewChat={handleNewChat}
        />
```
(`handleNewChat` 已存在于 App.tsx,侧栏在用,直接复用。)

- [ ] **Step 2: ChatWindow.tsx —— Props 加 onNewChat + 透传给 MessageBubble**

Props 接口(现有 `sessionId/messages/onMessagesChange/onToggleSidebar`)加:
```tsx
  onNewChat?: () => void;
```
函数签名解构加 `onNewChat`:
```tsx
export default function ChatWindow({ sessionId, messages, onMessagesChange, onToggleSidebar, onNewChat }: Props) {
```
渲染 `MessageBubble` 处(现有传 `onChipSubmit/onComparisonStart/onComparisonRefresh/onComparisonRetry`)加一行:
```tsx
              onNewComparison={onNewChat}
```

- [ ] **Step 3: MessageBubble.tsx —— Props 加 onNewComparison + 透传给 ComparisonTaskCard**

Props 接口(`MessageBubble.tsx:12-20`)加:
```tsx
  onNewComparison?: () => void;
```
解构(`MessageBubble.tsx:22-30`)加 `onNewComparison`。
渲染 `ComparisonTaskCard` 处(`MessageBubble.tsx:138-143`)加一行:
```tsx
            <ComparisonTaskCard
              task={message.comparisonTask as ComparisonTask}
              sessionId={sessionId}
              onRefresh={() => onComparisonRefresh?.(message.id, message.comparisonTask!.id)}
              onRetryPlatform={(platform) => onComparisonRetry?.(message.id, message.comparisonTask!.id, platform)}
              onNewComparison={onNewComparison}
            />
```

- [ ] **Step 4: ComparisonTaskCard.tsx —— Props 加 onNewComparison + 加按钮**

Props 接口(`ComparisonTaskCard.tsx:5-10`)加:
```tsx
  onNewComparison?: () => void;
```
解构(`ComparisonTaskCard.tsx:24`)加 `onNewComparison`:
```tsx
export default function ComparisonTaskCard({ task, sessionId, onRefresh, onRetryPlatform, onNewComparison }: Props) {
```
把现有刷新按钮(`ComparisonTaskCard.tsx:44` `<button onClick={onRefresh} style={buttonStyle}>刷新</button>`)替换为两个按钮并排:
```tsx
        <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
          <button onClick={onNewComparison} style={buttonStyle}>🔄 换个产品比价</button>
          <button onClick={onRefresh} style={buttonStyle}>刷新</button>
        </div>
```
(复用现有 `buttonStyle`,与刷新同款 secondary 样式。)

- [ ] **Step 5: 构建验收**

Run: `npm --prefix /Users/summer/mro-agent/frontend run build`
Expected: `tsc -b && vite build` 通过,0 TS 错误。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/App.tsx frontend/src/components/ChatWindow.tsx frontend/src/components/MessageBubble.tsx frontend/src/components/ComparisonTaskCard.tsx
git commit -m "feat(ui): 比价卡片加「换个产品比价」按钮(开新对话避免上下文串味)"
```

---

## Task 2: 部署 + 实操验证

- [ ] **Step 1: 部署**(commit 推送 + 服务器 `git reset` + 重建 **仅 frontend**(无后端改动):`docker compose up -d --build --no-deps frontend`;按部署陷阱验证 HEAD/容器重建/前端哈希)
- [ ] **Step 2: 实操验证**:
  - 发起一次比价出结果 → 卡片头部刷新旁有「🔄 换个产品比价」按钮;
  - 点击 → 切到新空白对话(欢迎语);
  - 在新对话打一个产品(如先在旧对话比"防尘口罩"+精炼"只要3M",再点按钮、在新对话打"防尘口罩")→ 新查询的结构/slot 概述**不再**带上一轮的 KN95/3M 历史(对比串味场景);
  - 旧比价在左侧历史可切回(非破坏)。

---

## 自检(Spec 覆盖)

| Spec 要求 | 对应 |
|---|---|
| 比价结果卡片加按钮 | Task 1 Step 4 |
| 点击 → App.handleNewChat 开新对话 | Task 1 Step 1-2(透传 handleNewChat) |
| prop 透传 App→ChatWindow→MessageBubble→ComparisonTaskCard | Task 1 Step 1-4 |
| 纯前端、无后端改动 | 全计划只动 4 个 .tsx |
| 不论 task 状态都显示、不加二次确认 | Task 1 Step 4(按钮无状态门控、无 confirm) |
| 构建 + 实操验收 | Task 1 Step 5 + Task 2 |
