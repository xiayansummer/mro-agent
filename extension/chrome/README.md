# MRO Chrome 扩展

第一版扩展负责绑定 Web 用户、保存扩展令牌、定时上报心跳、检测平台登录态。搜索结果页采集适配器在后续 CMP-303/CMP-501 接入。

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

## 登录态检测原则

- 不读取或上传 cookie
- 不上传 localStorage
- 不上传 HTML 原文
- 页面特征不足或探测失败时返回 unknown，不误报已登录
- Popup 提供 JD/ZKH 登录页入口，登录完成后可手动重新上报状态

## 当前限制

- 仅 Chrome Manifest V3
- 暂未拉取比价子任务
- 暂未解析 JD/ZKH 搜索结果页
