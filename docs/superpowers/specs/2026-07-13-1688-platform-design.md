# 设计:接入 1688 作为第 4 个比价平台

- 日期:2026-07-13
- 状态:已批准(待实施)
- 相关:ADR-001(扩展比价 + 六层结构)、架构审查 finding #7(SearchTerms 抽象无法表达西域)

## 目标

把阿里巴巴 1688(`https://www.1688.com/`)作为第 4 个比价平台接入 MRO Agent。走 Chrome 扩展、用用户已登录的浏览器账号采集(与京东工业品/震坤行同路),默认参与每次比价(四平台全触发),批发价取搜索页可见价(区间下限/起批价)参与排序、展示时如实标注起订量。顺手把搜索词模型 `ComparisonSearchTerms` 从硬字段改为 dict,根治架构审查里的 finding #7(西域靠偷 jd/zkh 词的临时路径)。

## 关键决策(已与用户确认)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 采集方式 | Chrome 扩展(仿 jd/zkh) | 1688/淘宝风控极严(滑块/登录墙/sign 参数),服务端抓大概率失效;扩展路径符合 ADR-001,基础设施(任务队列/登录态探测/回传)现成 |
| 默认开启 | 默认四平台全触发 | 与现有三平台一致,无额外交互;未登录 1688 时该子任务标 login_required,不影响其余平台 |
| 阶梯价口径 | 取**搜索页可见价(区间下限/起批价)** + 标注起订量,`unitComparable=false` | 搜索列表页拿不到真实批发底价(需进详情页,列范围外);取区间下限/起批价近似,`priceText` 如实展示口径;不与京东零售价做单位归一 |
| 搜索词模型 | `ComparisonSearchTerms` 改 `dict[str, list[str]]` | 根治 finding #7;以后加平台=加数据而非改代码;"1688" 可直接做 dict 键(数字开头不能作 Python 标识符) |
| 平台别名/默认列表/collector | 建后端**平台注册表 `platforms.py` 单一真源** | 平台名/别名此前散落 5+ 处(refine 三张表 + 两处内联正则 + 默认列表 + `!= "ehsy"` 特判);建 registry 后各处派生,加平台=注册表加一条数据。符合"找根因不按特例调" |

## 架构改动

### 后端

| 文件 | 改动 |
|---|---|
| `platforms.py` 🆕 | **平台注册表单一真源**:`PLATFORM_REGISTRY = {id: {cn, aliases, collector}}`(见下方专节),含 `DEFAULT_PLATFORMS`。1688 加一条 `{"cn":"阿里巴巴1688","aliases":["1688","阿里巴巴","阿里","alibaba"],"collector":"extension"}` |
| `models/comparison.py` | `Platform` 加 `"1688"`;`PurchaseConstraints.preferredPlatforms` 默认改为引用 `DEFAULT_PLATFORMS`(含 1688);`ComparisonSearchTerms` 由硬字段 `jd/zkh` 改为内部 `dict[str, list[str]]`(序列化 `{"jd":[…],"zkh":[…],"1688":[…],"ehsy":[…]}`) |
| `comparison_query_builder.py` | `build_search_terms` 统一产出 `{平台: 词列表}` dict,四平台复用同一批降级词序列;删对 jd/zkh 的硬编码 |
| `comparison_refine_service.py` | **(用户审查补漏)** 处理"只看X/去掉X"的三张表(`_PLATFORM`/`_PLAT_CN`/`_PLAT_NEG_MAP`)+ 两处内联正则(`(去掉\|不要\|排除\|除了)\s*(平台名)`、`not in {"","京东",…}`)全部改为**从 `PLATFORM_REGISTRY` 派生**。不改则"只看1688"/"去掉1688"识别不了 |
| `comparison_task_service.py` | 删临时 `_ehsy_search_term`(改从 dict 取词);`extension_platforms` 的 `!= "ehsy"` 特判改为按 registry 的 `collector=="extension"` 筛选(1688 天然入列,顺手根治 ehsy 特判) |
| `comparison_draft_service.py` | 默认平台列表 `["jd","zkh","ehsy"]` → 引用 `DEFAULT_PLATFORMS` |
| `agent.py` / `comparison_structure.py` | 旧文案"查询京东工业品和震坤行"(连 ehsy 都没提)→ 改泛化措辞"查询各比价平台",不再写死平台名(加平台不用再改文案) |
| `inquiry.py` | docstring"三平台外部比价(京东/震坤行/西域)"→"外部比价(各平台)" |

### 扩展(新增 1688 采集器,仿 zkh)

| 文件 | 改动 |
|---|---|
| `platforms.js` | 加 1688 平台条目:`probeUrl: https://www.1688.com/`、`loginUrl`、登录态特征选择器/文案(初版为合理猜测,待真实页校准) |
| `alibaba1688Parser.js` 🆕 | 仿 `zkhParser.js`:解析 1688 搜索结果页 DOM → 标题/**搜索页可见价(区间取下限,否则起批单价)**/**起订量**/图片/链接;导出 `parse1688SearchPage`/`is1688SearchResultUrl`/`classify1688Page`(登录墙/占位识别) |
| `alibaba1688Search.js` 🆕 | 仿 `zkhSearch.js`:`run1688SearchTask`,多词降级、品牌匹配兜底、超时保护 |
| `background.js` | `getTaskRunner` 加 `if (platform === "1688") return run1688SearchTask` |
| `manifest.json` | `host_permissions` 加 `https://*.1688.com/*`;`version` `0.3.0 → 0.3.1` |
| `scripts/1688-calibrate.console.js` 🆕 | 仿 `zkh-calibrate.console.js`,在真实 1688 搜索页跑、校准选择器 |

### 前端

| 文件 | 改动 |
|---|---|
| `types/index.ts` | `ComparisonPlatform` 加 `"1688"`;`PLATFORM_LABELS` 加 `"1688": "阿里巴巴1688"`(前端保留自己的 label map,不 import 后端);`ComparisonSearchTerms` 类型改 dict(`Record<string, string[]>`) |
| `ComparisonDraftCard.tsx` | 第 64 行写死的文案"确认结构后查询京东工业品、震坤行和西域"→ 改从 `draft.selectedPlatforms` 用 `PLATFORM_LABELS` 拼(该组件第 107 行本就这么拼平台名),不再写死 |
| 卡片 / `OfferRow` | **无需改**:阶梯价走现有 `priceText`("¥2.50起 / ≥100件")、`unitComparable=false` 复用现有 offer 渲染 |

## 数据流(一次含 1688 的比价)

1. 需求 → `build_comparison_structure` → 建 draft,`selectedPlatforms=[jd, zkh, ehsy, 1688]`
2. `build_search_terms` 产出 `terms` dict `{jd:[…], zkh:[…], "1688":[…], ehsy:[…]}`(四平台复用同一批降级词)
3. `start_draft`:`extension_platforms=[jd, zkh, 1688]`(排除 ehsy)建 3 个扩展子任务(queued);ehsy 服务端注入
4. 扩展心跳 → `fetchNextTask` 拿到 `platform=1688` 子任务 → `getTaskRunner` → `run1688SearchTask` → 在 1688.com 搜索、解析阶梯价 → `submitSubtaskResults` 回传
5. 后端 `rank_external_offers` 排序(1688 offer `priceValue`=搜索页可见价[区间下限/起批价]、`unitComparable=false`)→ 落 DONE 子任务
6. 前端轮询 `getComparisonTask` → 卡片展示 1688 列(「阿里巴巴1688」标签 + 「¥2.50起 / ≥100件」)

## SearchTerms dict 迁移 + 存量兼容

- `ComparisonSearchTerms` 内部 `dict[str, list[str]]`。取词统一 `terms.get(platform, [])`。
- **存量兼容零迁移**:DB 里旧 draft 的 `search_terms_json` 是 `{"jd":[…],"zkh":[…]}`,反序列化成 dict 天然兼容——缺的键(1688/ehsy)取词时 `.get()` 兜底空列表。不需要数据迁移脚本。
- 删 `_ehsy_search_term` 的偷词逻辑(ehsy 现在有自己的键;若某平台词为空,回退到"任一非空平台的首词"作为通用兜底,替代原来只偷 jd/zkh 的写法)。

## 平台单一真源(根治 refine 平台别名散落 —— 用户审查补漏)

**问题**:平台名/别名此前散落硬编码在 ≥5 处,加 1688 若逐处补丁则继续堆特例,且极易漏(本次就漏了 refine)。最关键的是 `comparison_refine_service.py` 处理"只看X / 去掉X"自然语言指令的地方:三张表(`_PLATFORM` 别名→id、`_PLAT_CN` id→中文、`_PLAT_NEG_MAP` 否定别名→id)+ 两处内联正则(`(去掉|不要|排除|除了)\s*(京东工业品|京东|震坤行|西域|ehsy)`、排除集合 `{"","京东","震坤行","西域"}`)。**不改这些,用户发"只看1688"/"去掉1688"识别不了。**

**方案**:建后端平台注册表作单一真源,各处派生:

```python
# app/platforms.py
PLATFORM_REGISTRY = {
    "jd":   {"cn": "京东工业品", "aliases": ["京东工业品", "京东", "jd"],           "collector": "extension"},
    "zkh":  {"cn": "震坤行",     "aliases": ["震坤行", "zkh"],                      "collector": "extension"},
    "ehsy": {"cn": "西域",       "aliases": ["西域", "ehsy"],                       "collector": "server"},
    "1688": {"cn": "阿里巴巴1688","aliases": ["1688", "阿里巴巴", "阿里", "alibaba"], "collector": "extension"},
}
DEFAULT_PLATFORMS = list(PLATFORM_REGISTRY)  # ["jd", "zkh", "ehsy", "1688"]
```

派生关系:
- `_PLATFORM` / `_PLAT_NEG_MAP`(别名→id)= 遍历 registry 的 aliases 生成;`_PLAT_CN`(id→中文)= `{id: v["cn"]}`
- 两处内联正则的平台名 group = `"|".join(所有 aliases)`(动态拼);排除集合 = 所有 cn/aliases
- `comparison_task_service` 的 `extension_platforms` = `[p for p in selected if REGISTRY[p]["collector"] == "extension"]`(替代 `!= "ehsy"` 特判)
- `DEFAULT_PLATFORMS` 供 models 默认值 / draft_service / task_service 的默认列表引用

**收益**:加平台 = 在 registry 加一条数据;refine 的过滤指令、默认列表、扩展/服务端路由全自动跟上,不再逐处改代码。前端 `PLATFORM_LABELS` 是前端自己的一份 label map(不 import 后端),仍手动加 1688 一行(仅一处)。

## 价格口径(阶梯价 / 搜索页可见价)

⚠️ **重要语义澄清**:1688 搜索结果**列表页**通常只展示「起批价」(购买最小起订量时的单价,常是较高的那一档)或「价格区间」(如"2.5–3元");**真正的批发底价(大批量降到更低)一般要点进商品详情页才加载得到**。首版只抓搜索结果页(与 jd/zkh 同路,一次搜索页拿一批 offer),**不**逐个商品进详情页。因此:

- **`offer.priceValue`(参与排序)= 搜索结果页可见价**:若为区间**取区间下限**;若仅有单价则取该单价。**该值是"起批价 / 区间下限",不保证是该商品的终极批发底价。**
- `offer.priceText` = 展示原文并如实带上起订量,如 "¥2.5–3 / ≥100件" 或 "¥3起 / ≥100件"(区间/起批**如实展示,不掩盖**,让用户知道这是起批口径)
- `offer.unitComparable = false` → 现有 `priceSortValue` 用 `priceValue*1.2`、不与京东零售价做严格单位归一(也弱化了上述价格语义偏差对跨平台排序的影响)
- 批发起批价通常仍低于零售、会排前,属合理;卡片有平台标签,用户自行权衡批发 vs 零售

## 错误处理 / 登录态

- 1688 未登录 / 触发滑块风控 → 解析器识别登录墙/占位 → 子任务标 `login_required`(复用 zkh 的 `classifyPage` 范式),前端显示「1688:需登录/验证」+ 重试按钮
- 1688 采集失败**绝不影响** jd/zkh/ehsy(各子任务独立 session + 独立回写)
- 登录态探测复用 `loginProbe` 的 30min TTL 缓存(避免每分钟开 1688 页触发风控)

## 测试策略

- **后端**:`build_search_terms` 产四平台词单测;`ComparisonSearchTerms` 读旧格式(仅 jd/zkh)兼容单测;含 1688 的 `start_draft` 建子任务单测(复用 `test_comparison_task_service` 的 FakeSession);**`parse_refinement` 对"只看1688"/"去掉1688"/"不要阿里巴巴"识别出 `platformKeep`/`platformDrop`=`"1688"` 的单测**(锁住用户指出的补漏);registry 派生的别名映射单测
- **扩展**:`alibaba1688Parser` 对样本 HTML 的解析单测(标题/价格[区间取下限、单价取值]/起订量提取);登录墙识别单测
- **前端**:`ComparisonPlatform`/`PLATFORM_LABELS` 类型 tsc 通过;`normalizeComparisonTask` 对含 1688 subtask 的 task 单测

## 已知风险

⚠️ **扩展解析器的 DOM 选择器需要真实 1688 搜索结果页来校准**(与 zkh 同):没有真实样本页,选择器无法保证一次写对。首版交付=骨架 + 合理选择器猜测 + `1688-calibrate.console.js` 校准脚本;线上准确度需拿真实页迭代几轮。

⚠️ **扩展改动需发新版**:改了扩展(v0.3.1)要重新打包 + 走 Edge/Chrome 商店审核(注意 Edge 审核的 1.3.1 可测试性要求——需在审核备注提供测试账号)。

⚠️ **1688 价格并非终极批发底价**:受限于搜索结果页 DOM,`priceValue` 取到的是**起批价 / 区间下限**,而非大批量的真实底价(那要进详情页)。跨平台排序时 1688 的价格权重要意识到这个偏差——它可能偏高(把起批价当"最低")。`unitComparable=false` 已避免与零售价做严格单位归一,减轻影响;`priceText` 如实展示"起/区间 + 起订量",不误导用户。真实底价需进详情页,列为范围外(见下)。

## 范围外(YAGNI)

- 淘宝/天猫等其他阿里系平台(本次只 1688)
- **进商品详情页抓真实批发底价 / 按采购数量匹配对应阶梯档**(首版只抓搜索结果页的起批价/区间下限;进详情页=每个商品多开一次页,N 倍请求 + 风控暴增 + 慢,故不做)
- 1688 服务端 API 接入(风控原因,走扩展)
