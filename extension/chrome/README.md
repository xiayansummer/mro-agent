# MRO Chrome 扩展

第一版扩展负责绑定 Web 用户、保存扩展令牌、定时上报心跳、检测平台登录态，并执行 JD / ZKH 搜索结果页采集任务。

## 本地加载

1. 打开 Chrome：`chrome://extensions/`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择目录：`extension/chrome`

## 线上绑定

1. 打开 `https://mro.fultek.ai/` 并登录
2. 在 Web 端生成配对码
3. 打开扩展 popup
4. 输入 6 位配对码并绑定

扩展后端地址固定为 `https://mro.fultek.ai/api`，用户无需填写。

绑定成功后：

- 扩展把 `extToken` 保存到 `chrome.storage.local`
- 后端只保存 `extToken` 的 SHA-256 hash
- 旧 active 扩展会被撤销
- 扩展每 1 分钟上报一次心跳（只与本服务后端通信，不打开任何平台页）
- 登录态探测（需真打开 JD/ZKH 后台 tab）与心跳**解耦**：每个平台最多每 30 分钟才真探一次（`LOGIN_PROBE_TTL_MINUTES`），TTL 内的心跳复用上次结果、不开页；真实搜索任务会回写登录态缓存，活跃使用期间几乎无需主动探测。**这样避免每分钟访问京东触发风控**
- 手动「立即上报状态」会强制即时探测一次（绕过 TTL）
- 已绑定后，扩展会随心跳拉取比价子任务并执行 JD / ZKH 搜索结果页前 10 条采集

## 登录态检测原则

- 不读取或上传 cookie
- 不上传 localStorage
- 不上传 HTML 原文
- 页面特征不足或探测失败时返回 unknown，不误报已登录
- Popup 提供 JD/ZKH 登录页入口，登录完成后可手动重新上报状态

## JD / ZKH 真实页面验收

CMP-303 使用本机 Chrome + DevTools Protocol 验收真实 JD 工业搜索结果页，不进入详情页，不上传 cookie、localStorage 或 HTML 原文。

```bash
node extension/chrome/scripts/validate-jd-search.mjs
```

JD 搜索页通常要求登录。建议第一次用独立验证 profile 跑可见 Chrome，完成登录后复用该 profile：

```bash
node extension/chrome/scripts/validate-jd-search.mjs \
  --headless false \
  --user-data-dir /tmp/mro-jd-validation-profile \
  --login-wait-ms 120000
```

默认验证 5 个关键词：

- `M8 304 外六角螺栓`
- `3M 口罩 N95`
- `德力西 断路器 2P 32A`
- `SKF 轴承 6205`
- `世达 内六角扳手套装`

脚本会生成本地报告 `extension/chrome/validation/jd-search-real-report.json`，该报告默认不纳入 Git。可用 `--keyword "关键词"` 覆盖默认关键词；如果 JD 对 headless Chrome 限制较严，可加 `--headless false` 用可见 Chrome 跑验收。

CMP-501 的 ZKH 适配器复用扩展任务协议，第一版按搜索结果页前 10 条做保守解析；如果震坤行页面结构变更，需用真实页面补充 fixture 回归。

## 当前限制

- 仅 Chrome Manifest V3
- Chrome MV3 alarm 当前按 1 分钟心跳轮询任务，不做 3 秒常驻轮询
- 已接入 JD / ZKH 搜索结果页；ZKH 单位价格默认不可比
