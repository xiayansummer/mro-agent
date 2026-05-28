# MRO Chrome 扩展

第一版扩展负责绑定 Web 用户、保存扩展令牌、定时上报心跳、检测平台登录态，并执行 JD 搜索结果页采集任务。ZKH 搜索结果页适配器在后续 CMP-501 接入。

## 本地加载

1. 打开 Chrome：`chrome://extensions/`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择目录：`extension/chrome`

## 本地绑定

1. 启动后端：`uvicorn app.main:app --reload --port 8000`
2. Web 端登录后调用 `POST /api/extension/pairing-code` 生成配对码
3. 打开扩展 popup
4. 后端地址保持 `http://localhost:8000/api`
5. 输入 6 位配对码并绑定

绑定成功后：

- 扩展把 `extToken` 保存到 `chrome.storage.local`
- 后端只保存 `extToken` 的 SHA-256 hash
- 旧 active 扩展会被撤销
- 扩展每 1 分钟上报一次心跳
- 心跳会轻量打开 JD/ZKH 首页后台 tab，检测登录/未登录页面特征后关闭 tab
- 已绑定后，扩展会随心跳拉取比价子任务并执行 JD 搜索结果页前 10 条采集

## 登录态检测原则

- 不读取或上传 cookie
- 不上传 localStorage
- 不上传 HTML 原文
- 页面特征不足或探测失败时返回 unknown，不误报已登录
- Popup 提供 JD/ZKH 登录页入口，登录完成后可手动重新上报状态

## JD 真实页面验收

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

## 当前限制

- 仅 Chrome Manifest V3
- Chrome MV3 alarm 当前按 1 分钟心跳轮询任务，不做 3 秒常驻轮询
- 已接入 JD 搜索结果页；暂未解析 ZKH 搜索结果页
