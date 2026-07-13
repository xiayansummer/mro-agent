# 设计:接入 1688 作为第 4 个比价平台

- 日期:2026-07-13
- 状态:已批准(待实施)
- 相关:ADR-001(扩展比价 + 六层结构)、架构审查 finding #7(SearchTerms 抽象无法表达西域)

## 目标

把阿里巴巴 1688(`https://www.1688.com/`)作为第 4 个比价平台接入 MRO Agent。走 Chrome 扩展、用用户已登录的浏览器账号采集(与京东工业品/震坤行同路),默认参与每次比价(四平台全触发),批发阶梯价取最低档单价参与排序、展示时标注起订量。顺手把搜索词模型 `ComparisonSearchTerms` 从硬字段改为 dict,根治架构审查里的 finding #7(西域靠偷 jd/zkh 词的临时路径)。

## 关键决策(已与用户确认)

| 决策点 | 选择 | 理由 |
|---|---|---|
| 采集方式 | Chrome 扩展(仿 jd/zkh) | 1688/淘宝风控极严(滑块/登录墙/sign 参数),服务端抓大概率失效;扩展路径符合 ADR-001,基础设施(任务队列/登录态探测/回传)现成 |
| 默认开启 | 默认四平台全触发 | 与现有三平台一致,无额外交互;未登录 1688 时该子任务标 login_required,不影响其余平台 |
| 阶梯价口径 | 取最低档单价 + 标注起订量,`unitComparable=false` | 简单直观;不与京东零售价做单位归一;用户按平台标签自行权衡批发 vs 零售 |
| 搜索词模型 | `ComparisonSearchTerms` 改 `dict[str, list[str]]` | 根治 finding #7;以后加平台=加数据而非改代码;"1688" 可直接做 dict 键(数字开头不能作 Python 标识符) |

## 架构改动

### 后端

| 文件 | 改动 |
|---|---|
| `models/comparison.py` | `Platform` 加 `"1688"`;`PurchaseConstraints.preferredPlatforms` 默认加 `"1688"`;`ComparisonSearchTerms` 由硬字段 `jd/zkh` 改为内部 `dict[str, list[str]]`(序列化 `{"jd":[…],"zkh":[…],"1688":[…],"ehsy":[…]}`) |
| `comparison_query_builder.py` | `build_search_terms` 统一产出 `{平台: 词列表}` dict,四平台复用同一批降级词序列;删对 jd/zkh 的硬编码 |
| `comparison_task_service.py` | 删临时的 `_ehsy_search_term`(改从 dict `.get("ehsy")` 或统一取词);`extension_platforms = [p for p in selected if p != "ehsy"]` **天然已含 1688**,建扩展子任务逻辑复用 jd/zkh 路径,无平台特判 |
| `comparison_draft_service.py` | 默认平台列表 `["jd","zkh","ehsy"]` → 加 `"1688"` |

### 扩展(新增 1688 采集器,仿 zkh)

| 文件 | 改动 |
|---|---|
| `platforms.js` | 加 1688 平台条目:`probeUrl: https://www.1688.com/`、`loginUrl`、登录态特征选择器/文案(初版为合理猜测,待真实页校准) |
| `alibaba1688Parser.js` 🆕 | 仿 `zkhParser.js`:解析 1688 搜索结果页 DOM → 标题/**阶梯价最低档单价**/**起订量**/图片/链接;导出 `parse1688SearchPage`/`is1688SearchResultUrl`/`classify1688Page`(登录墙/占位识别) |
| `alibaba1688Search.js` 🆕 | 仿 `zkhSearch.js`:`run1688SearchTask`,多词降级、品牌匹配兜底、超时保护 |
| `background.js` | `getTaskRunner` 加 `if (platform === "1688") return run1688SearchTask` |
| `manifest.json` | `host_permissions` 加 `https://*.1688.com/*`;`version` `0.3.0 → 0.3.1` |
| `scripts/1688-calibrate.console.js` 🆕 | 仿 `zkh-calibrate.console.js`,在真实 1688 搜索页跑、校准选择器 |

### 前端

| 文件 | 改动 |
|---|---|
| `types/index.ts` | `ComparisonPlatform` 加 `"1688"`;`PLATFORM_LABELS` 加 `"1688": "阿里巴巴1688"`;`ComparisonSearchTerms` 类型改 dict(或 `Record<string, string[]>`) |
| 卡片 / `OfferRow` | **无需改**:阶梯价走现有 `priceText`("¥2.50起 / ≥100件")、`unitComparable=false` 复用现有 offer 渲染 |

## 数据流(一次含 1688 的比价)

1. 需求 → `build_comparison_structure` → 建 draft,`selectedPlatforms=[jd, zkh, ehsy, 1688]`
2. `build_search_terms` 产出 `terms` dict `{jd:[…], zkh:[…], "1688":[…], ehsy:[…]}`(四平台复用同一批降级词)
3. `start_draft`:`extension_platforms=[jd, zkh, 1688]`(排除 ehsy)建 3 个扩展子任务(queued);ehsy 服务端注入
4. 扩展心跳 → `fetchNextTask` 拿到 `platform=1688` 子任务 → `getTaskRunner` → `run1688SearchTask` → 在 1688.com 搜索、解析阶梯价 → `submitSubtaskResults` 回传
5. 后端 `rank_external_offers` 排序(1688 offer `priceValue`=最低档、`unitComparable=false`)→ 落 DONE 子任务
6. 前端轮询 `getComparisonTask` → 卡片展示 1688 列(「阿里巴巴1688」标签 + 「¥2.50起 / ≥100件」)

## SearchTerms dict 迁移 + 存量兼容

- `ComparisonSearchTerms` 内部 `dict[str, list[str]]`。取词统一 `terms.get(platform, [])`。
- **存量兼容零迁移**:DB 里旧 draft 的 `search_terms_json` 是 `{"jd":[…],"zkh":[…]}`,反序列化成 dict 天然兼容——缺的键(1688/ehsy)取词时 `.get()` 兜底空列表。不需要数据迁移脚本。
- 删 `_ehsy_search_term` 的偷词逻辑(ehsy 现在有自己的键;若某平台词为空,回退到"任一非空平台的首词"作为通用兜底,替代原来只偷 jd/zkh 的写法)。

## 价格口径(阶梯价)

- 解析器抽最低档单价 → `offer.priceValue`(参与排序)
- `offer.priceText` = "¥2.50起 / ≥100件"(展示原文,含起订量)
- `offer.unitComparable = false` → 现有 `priceSortValue` 用 `priceValue*1.2`、不与零售价做单位归一
- 批发价通常更低会排前,属合理;卡片有平台标签,用户自行权衡批发 vs 零售

## 错误处理 / 登录态

- 1688 未登录 / 触发滑块风控 → 解析器识别登录墙/占位 → 子任务标 `login_required`(复用 zkh 的 `classifyPage` 范式),前端显示「1688:需登录/验证」+ 重试按钮
- 1688 采集失败**绝不影响** jd/zkh/ehsy(各子任务独立 session + 独立回写)
- 登录态探测复用 `loginProbe` 的 30min TTL 缓存(避免每分钟开 1688 页触发风控)

## 测试策略

- **后端**:`build_search_terms` 产四平台词单测;`ComparisonSearchTerms` 读旧格式(仅 jd/zkh)兼容单测;含 1688 的 `start_draft` 建子任务单测(复用 `test_comparison_task_service` 的 FakeSession)
- **扩展**:`alibaba1688Parser` 对样本 HTML 的解析单测(标题/最低档价/起订量提取);登录墙识别单测
- **前端**:`ComparisonPlatform`/`PLATFORM_LABELS` 类型 tsc 通过;`normalizeComparisonTask` 对含 1688 subtask 的 task 单测

## 已知风险

⚠️ **扩展解析器的 DOM 选择器需要真实 1688 搜索结果页来校准**(与 zkh 同):没有真实样本页,选择器无法保证一次写对。首版交付=骨架 + 合理选择器猜测 + `1688-calibrate.console.js` 校准脚本;线上准确度需拿真实页迭代几轮。

⚠️ **扩展改动需发新版**:改了扩展(v0.3.1)要重新打包 + 走 Edge/Chrome 商店审核(注意 Edge 审核的 1.3.1 可测试性要求——需在审核备注提供测试账号)。

## 范围外(YAGNI)

- 淘宝/天猫等其他阿里系平台(本次只 1688)
- 阶梯价"按采购数量匹配对应档"(首版只取最低档 + 标注起订量)
- 1688 服务端 API 接入(风控原因,走扩展)
