# 西域(ehsy)整合进比价结果 — 设计文档

> 日期:2026-06-19 · 状态:待评审 · 把已有的西域服务端抓取并入比价(第 3 个平台,服务端执行器)

## 1. 背景

比价目前只有**京东工业品(jd)+ 震坤行(zkh)**,二者靠浏览器扩展用用户登录态抓取(异步、碰风控)。代码里已有 `competitor_search.search_ehsy`:走 `m2.ehsy.com` 手机 App API(逆向 `ehsy-verify` 头、`token=""`),**免登录、免插件、服务端直抓**;实测从生产服务器跑 3 个 MRO 查询均返回真实结构化数据(品牌/价格/单位/sku/货期)。但它是独立 `/competitor` 端点,**未并入比价**。本设计把西域并入比价结果。

## 2. 目标与非目标

**目标**:每次比价默认额外纳入**西域**结果,与 jd/zkh 一并归一、排序、展示、可被新「结果精炼」操作。西域走**后端服务端抓取**(不经扩展、不需登录)。

**非目标(明确不做)**:
- 不为西域单独建 LLM 搜索词(v1 复用比价结构的主搜索词)。
- 不做单位价归一(`unitComparable=False`,同震坤行)。
- 不改 jd/zkh 的扩展抓取链路。
- 不做西域的"重试/登录"交互(它无登录、失败即降级)。

## 3. 用户场景

```
用户发起「防尘口罩 KN95 带阀」比价 → 点「开始比价」
  ~1s 后比价卡片出现:西域已 3 条(3M ¥4/只、安可护 ¥69/盒…),jd/zkh 显示"查询中"
  扩展抓完 → jd/zkh 结果陆续填入,三平台合并排序
用户:只看西域最便宜的 2 个 → 精炼出西域 priceValue 最低 2 条
```
扩展离线时:jd/zkh 提示需打开浏览器,**西域照常出结果**(服务端抓取)。

## 4. 架构与数据流

西域是**第 3 个平台**,执行器是**后端**(jd/zkh 是扩展):

```
start_draft(draft):
  ├─ jd  subtask → status=queued / login_required(扩展租取,如现状)
  ├─ zkh subtask → status=queued / login_required(扩展)
  └─ ehsy subtask → 后端同步:
        offers = await ehsy_comparison_source.fetch_ehsy_offers(主搜索词, structure, preferences)
        以 status=completed + items_json=offers 落库(~1s,不经扩展)
返回 task → 前端轮询 get_task → 合并三平台 subtasks.items
```

要点:
- ehsy subtask 一创建即 `completed`(带 items)。扩展 `lease_next_subtask` 只租 `queued`,**天然不碰 ehsy**。
- ehsy 抓取在 `start_draft` 内 `await`(~1s,12s 超时上限),阻塞 start 响应但换来"首轮轮询即有西域"。超时/出错 → `[]` → ehsy subtask completed 0 条(降级)。
- 扩展在线/登录态**不影响**西域(西域独立于扩展)。

## 5. 新建归一适配器 `ehsy_comparison_source.py`

新模块,单一职责:把西域原始结果适配成排序后的 `ExternalOffer`。`competitor_search.py`(原始 API 客户端)保持纯净不动。

```python
async def fetch_ehsy_offers(search_term: str, structure: dict, preferences: dict | None) -> list[dict]:
    raw = await search_ehsy(search_term, limit=8)        # 复用现有客户端
    offers = [_to_external_offer(p, i) for i, p in enumerate(raw)]
    offers = [o for o in offers if o]
    return rank_external_offers(structure, offers, preferences)  # 复用排序+disliked剔除
```

> `rank_external_offers` 的入参(结构是 `ComparisonStructure` 模型还是 dict、是否收 `preferences`)以其**现有签名为准**,实现时对齐(从 `start_draft` 已有的 `structure_json`/`user_id` 取);若该 ranker 不收 preferences,disliked 仍由读取路径 `filter_disliked_items` 兜底。

### 5.1 字段映射 ehsy dict → ExternalOffer

| ehsy 键 | ExternalOffer | 处理 |
|---|---|---|
| name | title | `[:100]` |
| brand | brand | |
| price(str) | priceValue | `float(price)`,不可解析→None |
| price+unit | priceText | `¥{price}/{unit}` |
| unit | unitText | |
| — | unitComparable | **False(固定)** |
| sku | platformSku | |
| sku | id | `ehsy-{sku}`(无 sku→`ehsy-{hash(name)}`,保证稳定) |
| url | productUrl | 无则回退 `https://www.ehsy.com/searchlist?key={query}`(必填字段不可空) |
| delivery | deliveryText | 如 "15个工作日" |
| — | platform | `"ehsy"` |
| (枚举序号) | rawRank | |
| (ranker 赋) | matchScore/matchReasons | `rank_external_offers` 填 |

`specText/minOrderQty/stockText/normalizedUnitPrice/imageUrl` v1 留空(名称已含规格)。

## 6. Platform 类型与默认平台

- `Platform = Literal["jd","zkh"]` → `Literal["jd","zkh","ehsy"]`(`comparison.py`)。
- `preferredPlatforms` 默认 `["jd","zkh"]` → `["jd","zkh","ehsy"]`(**默认开启**)。
- draft 的 `selected_platforms` 默认含 ehsy。

## 7. 单位价口径

`unitComparable=False`(同震坤行)。价格照显并沿用既有"单位不可比"提示;`priceValue` 仍写入,供精炼**排序/价位筛选**与 ranker 平手决胜使用。

## 8. 失败降级

- `search_ehsy` 已 try/except→`[]`;`fetch_ehsy_offers` 同样不抛(出错返回 `[]`)。
- ehsy subtask 落 `completed` + 0 条;比价照常显示 jd/zkh。
- `start_draft` 对 ehsy 的 `await` 包 try/except,**绝不让西域故障拖垮整个 start_draft**(jd/zkh 必须照常入队)。

## 9. 精炼 + ranker 复用

- `rank_external_offers` 已平台无关 → ehsy offers 一视同仁排序;disliked 剔除(写入路径 in adapter + 读取路径 `filter_disliked_items`)对 ehsy 同样生效。
- `get_latest_session_offers` 拍平所有 subtasks.items → **自动含 ehsy**,精炼开箱即用。
- `comparison_refine_service.parse_refinement`:`_PLATFORM` 加 `("西域","ehsy"),("ehsy","ehsy")`,支持"只看西域";`build_label` 的 `_PLAT_CN` 加 `"ehsy":"西域"`。

## 10. 前端

- 平台标签 `ehsy→西域`:`OfferRow.tsx` 与 `ComparisonTaskCard.tsx` 的 `PLATFORM_LABELS` 各加一项(本次顺带把重复的 `PLATFORM_LABELS` 提取共享,消除 Task6 遗留的重复)。
- 比价卡片的平台状态:西域子任务恒"已完成",**不展示"需登录/重试"**(它无登录态);`PlatformStatusChip` 对 ehsy 显示"已完成/服务端"。
- `ExternalOffer.platform` 类型已是 `Platform`,前端 types 同步加 `"ehsy"`。

## 11. 边界 / 细节

| 情况 | 行为 |
|---|---|
| 西域搜索词 | 复用 `structure.searchTerms.jd[0]`(无则 `zkh[0]`,再无则 productType);v1 不单独建词 |
| 西域 0 结果 | ehsy subtask completed 0 条,前端显示"西域:暂无匹配" |
| 西域 API 失效(逆向头过期) | `search_ehsy` 返回 `[]` → 同 0 结果路径,比价不挂 |
| 无 sku 的西域条目 | id 用 `ehsy-{hash(name)}`,productUrl 回退搜索页 |
| 扩展离线 | jd/zkh 阻塞提示,**西域照常出**(亮点) |

## 12. 测试计划(TDD)

- **`_to_external_offer` 归一**(纯函数):正常条目;缺价(priceValue=None);缺 sku(id 回退 + url 回退);unitComparable 恒 False;platform="ehsy"。
- **`fetch_ehsy_offers`**:mock `search_ehsy` 返回样本 → 归一+排序;mock `search_ehsy` 抛错 → 返回 `[]`(降级)。
- **`start_draft` 注入 ehsy**:mock `fetch_ehsy_offers` → ehsy subtask 以 completed+items 落库;jd/zkh 仍 queued;**mock `fetch_ehsy_offers` 抛错 → start_draft 仍正常建 jd/zkh subtask**(西域故障不拖垮)。
- **`parse_refinement`**:"只看西域" → platform=ehsy;"西域上最便宜的3个" 组合。
- **ranker**:ehsy offers 与 jd/zkh 混排,平台无关。
- 前端:`npm run build` 通过;手动/线上验证西域结果出现在比价卡片。

## 13. 风险 / 前置依赖

- **维护风险**:`ehsy-verify` 是逆向,app 升级可能失效 → 已有优雅降级(返回 `[]`),坏了只是少一个源,不报错;失效时在日志可见(`competitor_search` 已 `logger.warning`)。
- **生产依赖**:`competitor_search.py` 用 `pycryptodome`(`Crypto`),生产 backend 镜像须已含该依赖(`/competitor` 路由已在用 → 应已具备,实现时确认)。
- **start_draft 阻塞**:ehsy 同步 `await` 给 start 增加 ~1s;以 12s 超时 + try/except 兜底。
- 不改召回质量;西域结果质量取决于 App API 本身。
