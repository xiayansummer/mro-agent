# ADR 001: 通过 Chrome 扩展实现外部平台比价

## 状态

Accepted

## 背景

`mro-agent` 当前是一个 MRO 工业品采购助手，已有能力包括：

- 自然语言解析采购需求。
- 使用现有 MySQL 商品库做品类、品牌、规格、标准号归一化。
- 聊天页、服务端会话历史、Memos 偏好记忆。

下一阶段要把输出从“本库 SKU 推荐”切换为“京东工业 / 震坤行外部平台选品比价”。目标不是展示本库 SKU，而是利用本库数据做六层结构梳理，再到外部平台找可采购候选。

外部平台价格、库存、货期可能依赖用户账号、地区、企业合同价和登录态。后端直接抓取会面临登录态、验证码、风控和合规边界问题。

## 决策

第一版采用“现有 Web 聊天页 + FastAPI 后端 + Chrome 扩展”的架构：

- 所有采购型输入都进入外部平台查询流程，不再默认展示本库 SKU。
- 聊天页新增比价卡片，承载结构确认、平台登录态、任务进度、重试和结果表。
- 后端负责六层结构解析、搜索词生成、草稿/任务状态、结果归一和排序。
- Chrome 扩展负责在用户本机浏览器内访问京东工业和震坤行，并回传结构化商品结果。
- 扩展 MVP 使用短轮询拉任务，不使用长 WebSocket。
- 用户只支持一个 active Chrome 扩展；后绑定的扩展覆盖旧扩展。
- 扩展通过一次性配对码绑定用户，不复用 Web 登录 token。
- 默认只上传结构化商品字段，不上传 cookie、localStorage 或 HTML 原文。

## 六层结构

工程模型采用 `l1-l4 + specification + purchaseConstraints`：

```ts
type ComparisonStructure = {
  category: {
    l1?: string
    l2?: string
    l3?: string
    l4?: string
    confidence: number
    alternatives?: Array<{ l1?: string; l2?: string; l3?: string; l4?: string; label: string }>
  }
  specification: {
    productType?: string
    brand?: string
    model?: string
    material?: string
    size?: string
    standard?: string
    attributes: Array<{ name: string; value: string; unit?: string }>
    missing: string[]
  }
  purchaseConstraints: {
    quantity?: number
    unit?: string
    budgetMax?: number
    deliveryRequiredBy?: string
    preferredPlatforms: Array<"jd" | "zkh">
    requireInStock?: boolean
  }
  searchTerms: {
    jd: string[]
    zkh: string[]
  }
}
```

现有数据库只用于：

1. 品类路径校准。
2. 规格词、品牌、型号、标准号归一化。
3. 平台搜索词生成参考。

它不作为最终 SKU 推荐源，第一版 UI 不展示本库 SKU。

## 外部结果模型

扩展回传统一 `ExternalOffer`：

```ts
type ExternalOffer = {
  id: string
  platform: "jd" | "zkh"
  title: string
  brand?: string
  specText?: string
  priceText?: string
  priceValue?: number
  currency: "CNY"
  unitText?: string
  normalizedUnitPrice?: number
  unitComparable: boolean
  minOrderQty?: string
  stockText?: string
  deliveryText?: string
  productUrl: string
  platformSku?: string
  rawRank: number
  matchScore: number
  matchReasons: string[]
}
```

必填字段：

- `platform`
- `title`
- `productUrl`
- `rawRank`
- `unitComparable`
- `matchScore`

## 用户流程

1. 用户在聊天输入框输入采购需求。
2. 后端解析六层结构。
3. 聊天页展示结构确认卡片和平台登录态。
4. 如果平台未登录，用户点击打开平台登录；登录后点击重新检测或开始比价。
5. 后端创建平台子任务。
6. Chrome 扩展轮询拉取任务，访问 JD/ZKH 搜索结果页前 N 条。
7. 扩展回传结构化商品结果。
8. 聊天卡片展示平台子状态、partial results、重试按钮和最终对比表。

## 搜索策略

每个平台生成 2–3 个候选搜索词，从精确到宽泛尝试：

1. `品牌 + 产品类型 + 规格核心`
2. `产品类型 + 规格核心 + 材质/标准号`
3. `产品类型 + 关键规格`

停止条件：

- 每个平台最多尝试 3 个搜索词。
- 每个搜索词最多取搜索结果页前 10 条。
- 某个搜索词返回不少于 5 条可解析商品时，停止该平台后续搜索词。
- 单平台总耗时上限 12 秒；超时返回 partial + timeout 状态。

## 排序策略

默认按匹配度排序，价格只是辅助排序：

- 品类/标题包含产品类型。
- 核心规格匹配。
- 材质、标准、型号匹配。
- 品牌匹配。
- 平台原始排名。
- 单位可比时再用归一化价格做同分排序。

单位折算采用保守策略：

- 能明确识别包装数量时，计算 `normalizedUnitPrice`。
- 不能明确识别时，保留原始价格和单位，`unitComparable=false`，不参与低价排序。

## 安全和合规边界

- 扩展永不上传 cookie、localStorage、账号信息。
- 默认不上传 HTML 原文。
- 解析失败只上传错误码、选择器版本、少量脱敏文本片段。
- 调试模式必须用户显式开启，且提示可能包含页面内容。
- 后端日志不能记录完整 HTML、cookie、token。

## 后果

### 正面

- 最大化复用现有 `mro-agent` 的语义解析、归一化、聊天页、认证和历史能力。
- 企业价和登录态留在用户浏览器，合规边界更清晰。
- 短轮询更适配 Chrome Manifest V3 service worker 生命周期。
- 比价流程在聊天页内完成，用户不会面对多个入口。

### 代价

- 用户必须安装 Chrome 扩展。
- 任务实时性取决于扩展轮询间隔。
- JD/ZKH 页面变更会导致解析适配器需要维护。
- 后端需要新增草稿、任务、子任务和扩展会话状态模型。

## 被拒绝方案

### 后端直接抓 JD/ZKH

拒绝原因：登录态、验证码、企业价、地区价、风控和合规风险不可控。

### 一开始做复杂 Multi-Agent

拒绝原因：MVP 的关键风险在平台抓取、登录态、结构化解析和状态恢复，不在 Agent 协作。第一版采用单 Orchestrator + 明确工具/服务模块，后续可拆分为 Requirement Agent、Platform Agent 和 Comparison Agent。

### 独立比价页面

拒绝原因：用户希望所有查询结果都在聊天页输出，避免多页面入口造成困惑。第一版使用聊天页内的强状态比价卡片。
