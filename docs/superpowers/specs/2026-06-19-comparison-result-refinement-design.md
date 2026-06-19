# 对话内"比价结果精炼" — 设计文档

> 日期:2026-06-19 · 状态:待评审 · 解决"对已有比价结果的自然语言指令被误当成新商品"的根因

## 1. 背景与问题

实测会话(用户 13816702381 / 会话「防尘口罩」`mqj78az3eun2t6y9c4`):已有一个有效的防尘口罩比价后,用户说**"能不能选出价格最低的五个"**——这是对**现有结果**的指令,系统却把整句当成**新商品**:

- `parse_intent` 抽不出商品 → 8ca12c7 加的 `_fallback_keyword_from_message` 把**原句当关键词**;
- `slotClarification.known.商品类型 = "能不能选出价格最低的五个"`,继续追问数量;
- 提交后生成 `productType = "能不能选出价格最低的五个,请先确认关键参数…100件"` 的**垃圾比价草稿**(类目置信度 0%)。

**根因(两层)**:
1. `handle_message` 里**每条消息都无差别走** `create_draft_from_message`(新商品路径),没有"对当前结果做操作"的分支;
2. 8ca12c7 兜底**过宽**:商品抽空时把原句当关键词——对"防尘口罩"(真商品 LLM 偶发漏抽)是对的,对"能不能选出价格最低的五个"(根本不是商品)却造出垃圾。

扫描该账号 6 个会话证实该 bug **间歇性**:同类追问"是否有其他推荐"(手推车)、"上述推荐不对…海洋腐蚀环境的样品"(六角螺栓)**碰巧解析对了**(LLM 保留了原商品);"能不能选出价格最低的五个"因**一个商品名词都没有** + 兜底抓原句而**爆雷**。即:这是**所有比价会话的潜在风险**,复现与否靠运气。

## 2. 目标与非目标

**目标**:识别"对已有比价结果的精炼指令"(排序/取前N、按品牌、按价位、按平台),**直接在已采集的 offers 上操作并新出一条结果消息**,不重新建比价、不重新抓取(不碰风控)。

**非目标(明确不做)**:
- 不重新查询平台(精炼只在**已有 offers** 上做)。
- 不引入 LLM 做意图分类(确定性解析——LLM 不确定性正是 bug 之源)。
- 不做跨会话/历史结果的精炼(只针对**本会话最近一次**有结果的比价)。
- 不做"加一个新品类一起比"之类的复杂复合(YAGNI)。

## 3. 用户场景

```
[已存在] 防尘口罩比价结果(若干 offers 已采集)
用户:能不能选出价格最低的五个
助手:在「防尘口罩」结果中,按价格从低到高取前 5:[结果列表卡片]

用户:只看 3M 的
助手:在「防尘口罩」结果中,只看 3M:[结果列表卡片]

用户:京东上 50 元以下的
助手:在「防尘口罩」结果中,京东工业品、≤50 元:[结果列表卡片]
```
无结果时(没跑过比价 / 草稿还没点"开始比价" / 还没出 offers):
```
用户:能不能选出价格最低的五个
助手:您还没有可精炼的比价结果,先发起一次比价、出结果后我再帮您挑。
```

## 4. 架构与路由

在 `agent.py: handle_message` 里,`create_draft_from_message` **之前**插一条早分支;新建 `comparison_refine_service`:

```
handle_message(message)
  → cmd = comparison_refine_service.parse_refinement(message)   # 纯函数,快
  ├─ cmd is None        → 走原"新建比价"路径(不变)
  └─ cmd is not None     → offers = get_latest_session_offers(session_id, user_id)
        ├─ 无 offers     → yield 引导文本 + done(不建草稿)
        └─ 有 offers     → refined = apply_refinement(offers, cmd)
                            ├─ refined 为空 → yield "结果里没有符合条件的商品" + done
                            └─ 否则        → yield refined_offers 事件 + 引导文本 + done
```

要点:**先解析(纯函数、零 IO)再查库**——只有命中精炼模式才查最近结果,普通新品消息零额外开销。

## 5. 意图与操作解析(确定性,纯函数)

`parse_refinement(message: str) -> RefinementCommand | None`,返回结构:

```
RefinementCommand = {
  platform:  'jd' | 'zkh' | None,      # 平台过滤
  brandKeep: str | None,                # 只看某品牌(原文 token)
  brandDrop: str | None,                # 去掉某品牌
  priceMin:  float | None,
  priceMax:  float | None,
  sort:      'asc' | 'desc' | None,     # 按 priceValue
  limit:     int | None,                # 取前 N
  label:     str,                       # 人类可读,如 "按价格最低取前 5"
}
```

触发词(大小写/空格不敏感,数字支持阿拉伯与中文一~十):

| 维度 | 触发样例 | 解析 |
|---|---|---|
| 排序-升 | 最便宜、价格最低、最低价、便宜的、价低 | sort=asc |
| 排序-降 | 最贵、价格最高、最高价、贵的 | sort=desc |
| 取前N | 前N个、N个、(最便宜的)N个、取/留 N 个 | limit=N |
| 品牌-留 | 只看X、只要X、X品牌、要X的 | brandKeep=X |
| 品牌-去 | 去掉X、排除X、不要X、除了X | brandDrop=X |
| 价位 | X元以下/低于X/不超过X/X以内;X元以上/高于X;X到Y元/X-Y元 | priceMax/priceMin |
| 平台 | 只看京东(工业品)、京东上的;只看震坤行 | platform=jd/zkh |

可组合:"京东上最便宜的3个" → platform=jd, sort=asc, limit=3。

### 5.1 保守原则(关键:绝不劫持新比价)

- 必须命中**至少一个明确的精炼操作符**才可能判为精炼。
- 品牌词 X 必须**对得上当前结果里实际存在的品牌**(`text_matches_brand`);对不上则不作为品牌操作。
- 去掉已识别的精炼 token 后,**若残留明显的新商品名词**(如"最便宜的**电钻**"残留"电钻")→ 返回 `None`,回落新品路径。
- 裸品牌词、裸数字、无操作符 → 返回 `None`。
- **取舍**:漏判(精炼被当新品)可接受——回落后用户换句话即可;**误判(新品被当精炼)不可接受**,体验更差。故宁可漏判。

**必须判为精炼**:"能不能选出价格最低的五个"、"最便宜的5个"、"按价格排序"、"只看3M"、"去掉震坤行"、"50元以下的"、"京东上最便宜的3个"。
**必须不判为精炼(走新品)**:"防尘口罩"、"美和2吨手拉葫芦"、"最便宜的电钻"(含新商品名词)。

## 6. 操作对象(数据来源)

新增 `comparison_task_service.get_latest_session_offers(session_id, user_id) -> list[offer] | None`:

```sql
SELECT t.id FROM comparison_tasks t
JOIN comparison_drafts d ON t.draft_id = d.id
WHERE d.chat_session_id = :sid AND t.user_id = :uid
ORDER BY t.created_at DESC LIMIT 1
```

拿到最近 task_id 后**复用 `get_task(task_id, user_id)`** 装配 offers(已含 disliked 过滤、跨平台合并)。task 不存在 / 未开始 / 无 offers → 返回 `None`(→ 引导)。关联链已存在:`comparison_drafts.chat_session_id`(已建索引)→ `comparison_tasks.draft_id`。

## 7. 操作执行

`apply_refinement(offers, cmd) -> list[offer]`,顺序:**过滤 → 排序 → 取前N**。

1. **平台过滤**:`offer.platform == cmd.platform`。
2. **品牌过滤**:`brandKeep` 用 `comparison_ranker.text_matches_brand(offer_text, X)` 保留;`brandDrop` 反之剔除。
3. **价位过滤**:按 `priceValue`;`priceValue is None` 的在价位过滤中**剔除**(无价无法比较)。
4. **排序**:复用 `comparison_ranker._price_sort_value`,asc/desc;`priceValue is None` 排末尾。
5. **取前N**:`limit`。

`unitComparable=False`(震坤行单位价不可比)的 offer:**保留**但在卡片沿用既有"不可比"提示;若价格排序的前列含不可比项,引导文本附一句"含单位不可比项,价格仅供参考"。

`label` 由 cmd 生成(如"京东工业品、≤50 元、按价格最低取前 3")。

## 8. 呈现(SSE + 前端)

新 SSE 事件 `refined_offers`,payload:
```
{ sourceProductType: str, operationLabel: str, offers: ExternalOffer[], note?: str }
```
`handle_message` 依次 `yield`:`refined_offers` 事件 → 一条引导 `text`("在「防尘口罩」结果中,{label}:") → `done`。

**持久化**(可回看):`t_chat_message` 新增 `refined_offers` JSON 列(迁移),与 `comparison_draft` 平行:
- `chat.py: _capturing_stream` 捕获 `refined_offers` 事件累积;
- `chat_history_service.save_turn` 增参 `refined_offers`,写入新列;
- `get_session` 反序列化为消息的 `refinedOffers` 字段。

**前端**:
- `services/api.ts`:`SSECallbacks` 加 `onRefinedOffers`,解析 `refined_offers` 事件。
- `ChatWindow.handleSend`:`onRefinedOffers` → 写入该助手消息的 `refinedOffers`。
- `types`:`ChatMessage.refinedOffers?: { sourceProductType, operationLabel, offers, note? }`。
- 新建 `RefinedOffersCard.tsx`:顶部 `operationLabel` + offers 列表,**复用 `ComparisonTaskCard` 的 `OfferRow`**(含"合适/不合适"反馈)。为复用,将 `OfferRow` 抽成可共享组件。
- `MessageBubble`:消息含 `refinedOffers` 时渲染 `RefinedOffersCard`。

## 9. 边界与错误处理

| 情况 | 行为 |
|---|---|
| 命中精炼但本会话无可精炼结果 | 引导"您还没有可精炼的比价结果,先发起一次比价";若存在未开始的草稿,提示"先点开始比价" |
| 过滤后为空(品牌/价位无匹配) | "当前结果里没有符合条件的商品(如 {X})" |
| 命中精炼但抽不出具体操作 | 反问"想按价格、品牌、价位还是平台筛选?" |
| 价格操作时全部 `priceValue` 缺失 | "这些结果暂无可比较的价格,无法按价格筛选/排序" |

## 10. 顺带修复 8ca12c7 兜底过宽

`comparison_structure.py` 的新品兜底:消息一旦被 `parse_refinement` 判为精炼命令,**绝不**回落成"原句当商品关键词"。由于精炼分支在 `handle_message` 中**先于** `create_draft_from_message`,精炼命令根本不会进到 `_fallback_keyword_from_message`——天然堵住当初 bug 的最坏症状(垃圾草稿)。无需改 `_fallback_keyword_from_message` 本身(它对"真商品 LLM 漏抽"仍正确);回归测试覆盖"防尘口罩"那条会话不再出垃圾草稿即可。

## 11. 数据流(逐步)

1. 用户发消息 → `handle_message`。
2. `parse_refinement(message)` → cmd 或 None。None 则走原路径(完)。
3. cmd 命中 → `get_latest_session_offers(session_id, user_id)`。
4. 无 offers → 引导文本 + done(完)。
5. 有 offers → `apply_refinement(offers, cmd)`。
6. 空 → "无符合条件" + done;非空 → `refined_offers` 事件 + 引导 + done。
7. `_capturing_stream` 捕获 `refined_offers` → `save_turn` 落 `refined_offers` 列。
8. 回看历史时 `get_session` 装配 `refinedOffers` → 前端 `RefinedOffersCard` 渲染。

## 12. 新建 / 改动清单

| 新建 | 改动 |
|---|---|
| `services/comparison_refine_service.py`:`parse_refinement` + `apply_refinement` + `label` | `agent.py: handle_message` 加早分支 |
| `comparison_task_service.get_latest_session_offers`(同文件新函数) | `chat.py: _capturing_stream` 捕获 `refined_offers` |
| 迁移:`t_chat_message` 加 `refined_offers` JSON 列 | `chat_history_service.save_turn` / `get_session` 加 `refined_offers` |
| 前端 `RefinedOffersCard.tsx`(复用抽出的 `OfferRow`) | `api.ts`(onRefinedOffers)、`ChatWindow`、`MessageBubble`、`types` |

复用(不改逻辑):`comparison_ranker._price_sort_value` / `text_matches_brand`、`comparison_task_service.get_task`(含 disliked 过滤)、`ExternalOffer` 模型、`OfferRow` 渲染。

## 13. 测试计划(TDD)

- **`parse_refinement` 纯函数**(最高优先):
  - 各维度单测:排序升/降、取前N(阿拉伯+中文数字)、品牌留/去、价位(以下/以上/区间)、平台。
  - 组合:"京东上最便宜的3个" → platform+sort+limit。
  - **否定样本**:"防尘口罩"、"美和2吨手拉葫芦"、"最便宜的电钻"(含新商品名词)→ None。
  - **回归**:"能不能选出价格最低的五个" → 命中精炼(sort=asc, limit=5),**不再**被当新商品。
- **`apply_refinement`**:过滤→排序→取前N 顺序;priceValue 缺失处理;过滤后为空;unitComparable 保留。
- **`get_latest_session_offers`**:正确取本会话最近有 offers 的 task;无 task/无 offers → None。
- **集成**:`handle_message` 在"有结果 + 精炼句"→ 出 `refined_offers`;"无结果 + 精炼句"→ 引导;"新商品句"→ 走原路径不变。
- 前端可手动验证(无测试框架),按既有方式 build + 线上实操复现"防尘口罩→能不能选出价格最低的五个"。

## 14. 前置依赖 / 风险

- 依赖已采集 offers 的质量(本设计不改召回)。
- 确定性解析对**没预料的说法**会漏判(回落新品),可后续按真实日志补触发词;不上 LLM。
- `refined_offers` 列为新迁移,需在部署时执行(与现有 migrations 同机制)。
