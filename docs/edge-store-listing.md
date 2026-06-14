# Edge 加载项商店上架材料（MRO 外部比价助手 v0.3.0）

> 提交入口：Microsoft Partner Center → Microsoft Edge → 扩展（免费，无注册费）
> https://partner.microsoft.com/dashboard/microsoftedge/

## 一、基本信息

| 字段 | 填写内容 |
|---|---|
| 名称 Name | MRO 外部比价助手 |
| 简短描述 Short description | 用你已登录的京东工业品 / 震坤行账号采集搜索结果，做 MRO 工业品比价；不读取或上传 cookie。 |
| 分类 Category | Shopping（购物）或 Productivity（效率） |
| 语言 Language | 中文（简体） |
| 隐私政策 URL（必填） | https://mro.fultek.ai/privacy.html |
| 网站 / 支持 URL | https://mro.fultek.ai |
| 是否收集用户数据 | 是 —— 见隐私政策（仅平台公开商品信息 + 绑定状态，不含 cookie / 个人凭据） |

## 二、详细描述 Detailed description（可直接粘贴）

```
MRO 外部比价助手是工业品采购平台 MRO Agent（mro.fultek.ai）的配套浏览器扩展。

它在你主动发起比价时，用你已登录的京东工业品 / 震坤行账号打开对应平台的搜索结果页，
采集前若干条在售商品的公开信息（标题、品牌、价格、单位、货期、链接），回传给 MRO Agent
做归一、排序和对比，帮你在一处看清同一物料在不同平台的真实在售价。

【使用方式】
1. 在 mro.fultek.ai 登录后发起一次比价，比价卡片里点「生成配对码」
2. 打开本扩展弹窗，输入 6 位配对码完成绑定（后端地址已内置，无需填写）
3. 在比价卡片点「开始比价」，扩展即用你已登录的账号在后台完成采集

【隐私优先】
· 不读取、不上传任何 Cookie
· 不上传 localStorage / 浏览历史 / HTML 原文
· 只回传解析后的结构化比价条目
· 绑定令牌在后端仅以哈希形式存储；可随时在弹窗「解除本机绑定」

【适用场景】
企业采购、工程师选型——快速比对同一工业品在京东工业品、震坤行的在售价与货期。
```

## 三、权限理由 Permission justifications（审核常要逐条说明）

| 权限 | 理由 |
|---|---|
| `storage` | 在本机保存绑定令牌（extToken）与设备设置 |
| `tabs` | 在后台标签页打开京东工业品 / 震坤行的搜索结果页以执行比价 |
| `scripting` | 在上述结果页注入脚本，解析页面上公开的商品标题/价格等比价字段 |
| `alarms` | 定时（约每分钟）上报扩展在线状态、领取待执行的比价子任务 |
| 主机权限 `*.jd.com` / `*.jd.hk` / `*.zkh.com` | 仅在这两个比价平台采集公开商品信息 |
| 主机权限 `mro.fultek.ai` | 与本服务后端通信（绑定、上报状态、回传比价结果） |

> 关键合规说明（如审核追问可引用）：扩展仅在用户已登录、且用户主动发起比价时执行；
> 用用户自己的账号访问其有权访问的页面；不读取 cookie / 凭据，不上传 HTML 原文，
> 不加载远程代码。单一用途：工业品比价。

## 四、需要上传的素材

| 素材 | 文件 | 规格 |
|---|---|---|
| 扩展包 | `mro-extension-v0.3.0.zip`（见下方生成命令） | 解压后根目录含 manifest.json |
| 商店 Logo | `docs/store-assets/edge-logo-300.png` | 300×300 PNG |
| 截图（≥1 张） | 可用 `docs/comparison-draft-task.png` 或手册里的比价卡片图 | 建议 1280×800，至少 640×400 |

## 五、提交前自检

- [x] manifest 含 icons（16/32/48/128），无 localhost 主机权限
- [x] 隐私政策页已上线：https://mro.fultek.ai/privacy.html
- [x] description 不写死“Chrome”，单一用途清晰
- [ ] 在 Edge 里「加载解压缩的扩展」实测一遍绑定+比价无报错（建议提交前自测）
- [ ] Partner Center 上传 zip + logo + 截图 + 隐私政策 URL → 提交审核

## 六、注意

- Edge 与 Chrome 用同一份 MV3 包，本 zip 两边通用；Edge 审核通常更快、门槛更低，适合先行。
- 若审核追问“为何打开后台标签页采集”，引用第三节合规说明即可。
- 上架后用户即可在 Edge 加载项商店「获取」一键安装、自动更新、无开发者模式警告。
