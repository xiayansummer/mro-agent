# MRO Agent — 搜索质量增强 & 个性化推荐 设计文档

**日期：** 2026-03-26
**范围：** B（产品数据与搜索质量）+ D（智能化升级）
**不涉及：** 购物车/询价流程（A）、管理后台（C）

---

## 背景

当前系统的核心痛点：**推荐结果不懂用户习惯**。
用户每次搜索都得从头指定材质/规格，系统不记得他常用 304 不锈钢、M8 规格；搜索结果排序也不反映他的历史偏好。

本次设计解决四个问题，按优先级排序：

1. **B1（高）** 对话内属性追问 + 行业惯例建议
2. **D（高）** 个性化排序 + 偏好摘要自动更新
3. **B2（中）** 跨标准替代件推荐 + 产品知识卡片
4. **B3（低）** ERP 历史数据导入

---

## Feature 1：对话内属性追问 + 行业惯例建议

### 触发条件
`broad_spec` 查询，且搜索结果跨越多个关键属性维度（如同时含 A2/A4，或 M6~M20 混合）。

### intent_parser 新增字段

```json
{
  "attribute_gaps": ["材质等级", "规格（螺纹直径）"],
  "attribute_suggestions": {
    "材质等级": [
      {"value": "A2-70（304）", "note": "最常用，适合室内/一般环境", "is_common": true},
      {"value": "A4-80（316）", "note": "耐海水/化工腐蚀，溢价约30%", "is_common": false}
    ],
    "规格（螺纹直径）": [
      {"value": "M8", "note": "工业最常用规格", "is_common": true},
      {"value": "M6", "note": "", "is_common": false},
      {"value": "M10", "note": "", "is_common": false}
    ]
  }
}
```

### 行业惯例知识：两层叠加（均在 agent.py 里完成，intent_parser 只负责识别缺失维度）

- **第一层（静态知识库）**：`agent.py` 引用内置字典，覆盖紧固件常见属性维度，每个值附行业说明。
- **第二层（搜索结果实际值）**：搜索完成后，从返回结果的 `specification`/`attribute_details` 字段提取真实存在的属性值，与第一层合并去重。只有库里有的值才出现在选项里。

### agent.py 逻辑
`broad_spec` + `attribute_gaps` 非空时：
1. 用第一层静态知识构建 suggestions 基础集
2. 用搜索结果实际值补充/过滤 suggestions
3. 从 `memory_context` 读取历史偏好，将偏好项排到 suggestions 首位

### 追问输出格式
```
还需确认：您需要哪种材质等级？

→ **A2-70（304不锈钢）** ⭐ 最常用，适合室内/一般环境
→ A4-80（316不锈钢） — 耐海水/化工腐蚀，溢价约30%
```

### 改动文件
- `backend/app/services/intent_parser.py` — 新增 attribute_gaps / attribute_suggestions 字段
- `backend/app/services/agent.py` — 读取偏好并排序 suggestions
- `backend/app/services/response_gen.py` — 结构化追问输出

---

## Feature 2：个性化排序 + 偏好摘要自动更新

### 核心原则
不改搜索逻辑，改排序权重。搜索结果出来后，根据用户历史偏好做一次重排序。

### 新增模块：`preference_ranker.py`

```python
def rank_by_preference(results: list[dict], memory_context: str) -> list[dict]:
    """
    从 memory_context 提取偏好信号，对 results 重排序。
    返回重排后的列表，原始搜索排名作为 tiebreaker。
    """
```

### 偏好信号权重表

| 信号 | 权重 | 来源 |
|------|------|------|
| 品牌偏好（历史常用） | +2 | `#feedback` 👍 统计 |
| 曾明确点 👍 的产品 | +3 | `#feedback #liked` |
| 曾明确点 👎 的产品 | -5 | `#feedback #disliked` |
| 品类偏好 | +1 | `#session` 统计 |

### 透明度
被上浮的产品在推荐理由列加注 `（符合您的采购偏好）`。

### 偏好摘要自动更新（Memos `#preference` memo）

当该用户累计会话数达到 10 的倍数时（10、20、30…），自动将偏好统计结果写成一条结构化摘要 memo，覆盖旧版，供快速读取。

```
## 用户偏好摘要（自动更新）
偏好品牌：SMC, 米思米, 博世
偏好材质：304不锈钢, 碳钢镀锌
常用规格：M8, M10, DN25
#uid-xxxxx #preference
```

### 改动文件
- `backend/app/services/preference_ranker.py` — 新增模块
- `backend/app/services/agent.py` — 搜索后调用 ranker
- `backend/app/services/memory_service.py` — 新增 `update_preference_memo()`，每10次会话触发

---

## Feature 3：跨标准替代件推荐 + 产品知识卡片

### 触发条件
主搜索结果 < 3 个，且 parsed keywords 含已知标准号（DIN/ISO/GB）。

### 新增模块：`standard_mapping.py`

```python
STANDARD_EQUIVALENTS = {
    "DIN934":  ["ISO 4032", "GB/T 6170"],   # 六角螺母
    "DIN933":  ["ISO 4017", "GB/T 5783"],   # 全螺纹六角螺栓
    "DIN931":  ["ISO 4014", "GB/T 5782"],   # 半螺纹六角螺栓
    "DIN912":  ["ISO 4762", "GB/T 70.1"],   # 内六角圆柱头螺钉
    "DIN125":  ["ISO 7089", "GB/T 97.1"],   # 平垫圈
    "DIN127":  ["ISO 7090", "GB/T 93"],     # 弹簧垫圈
    # 持续扩充
}
```

**边界约定：不跨尺寸、不跨强度等级替代。只做标准体系等效映射。**

### 知识卡片格式（`generate_equivalent_stream()` 新增函数）

```
## {标准号} {产品名} — 产品知识

**① 定义与标识**
**② 主流材质与性能**
**③ 典型规格示例**
**④ 选型和采购要点**
**⑤ 常见误区**

---
以下库存产品与您搜索的 {标准号} 完全等效：

| 编号 | 产品名称 | 规格 | 说明 |
```

知识内容由 AI 基于标准知识生成；产品表格只用真实库存数据。

### 改动文件
- `backend/app/services/standard_mapping.py` — 新增模块
- `backend/app/services/agent.py` — 触发等效搜索逻辑
- `backend/app/services/response_gen.py` — 新增 `generate_equivalent_stream()`

---

## Feature 4：ERP 历史数据导入

### 导入流程

```
用户上传 Excel/CSV
→ POST /api/profile/import
→ 解析列：item_code / item_name / brand / quantity / date（宽松匹配中英文列名）
→ 聚合统计：Top 品牌、Top 品类、常用规格
→ 写入一条 #preference memo（覆盖旧的）
→ 返回摘要预览
```

### 支持列名（宽松匹配）

| 必须有其一 | 可选 |
|-----------|------|
| 产品编码 / item_code / 物料号 | 采购数量 / qty |
| 产品名称 / item_name / 物料描述 | 采购金额 / amount |
| | 品牌 / brand |
| | 采购日期 / date |

### 隐私原则
只存聚合摘要到 Memos，原始 Excel 不入库，导入后即丢弃。

### 改动文件
- `backend/app/api/profile.py` — 新增 router + import endpoint
- `backend/app/services/erp_importer.py` — 新增解析 + 聚合逻辑
- `frontend/src/components/Sidebar.tsx` — 底部加"导入采购历史"入口

---

## 整体架构关系

```
Memos                          MySQL
────────────────────           ──────────────────
#session  每次对话摘要          （现有 SKU 数据库）
#feedback 👍/👎 记录
#preference 偏好摘要
（ERP导入聚合 → 写入#preference）
         ↓
    get_user_context()
         ↓
 ┌───────────────────────────────┐
 │ intent_parser                 │  → attribute_gaps + suggestions
 │ preference_ranker             │  → 搜索结果重排序
 │ agent（standard_mapping）     │  → 等效标准替代搜索
 │ response_gen                  │  → 知识卡片 / 结构化追问
 └───────────────────────────────┘
```

## 不改动
- 前端所有现有组件（属性追问通过对话流实现，无需新 UI）
- `sku_search.py` 搜索逻辑
- `intent_parser.py` 现有字段（只新增字段）
- Memos 存储结构（只新增 `#preference` 写入，现有 `#session`/`#feedback` 不变）

---

## 交付顺序

| 优先级 | Feature | 预计改动量 |
|--------|---------|-----------|
| 1 | 对话内属性追问 + 行业惯例 | 中（3个文件） |
| 2 | 个性化排序 + 偏好摘要 | 中（3个文件 + 1个新模块） |
| 3 | 跨标准替代 + 知识卡片 | 中（2个新模块 + 2个文件） |
| 4 | ERP 导入 | 小（1个新模块 + 1个新 endpoint + 前端入口） |
