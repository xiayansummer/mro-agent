# MRO 工业品 AI 采购助手

智能工业品推荐系统，面向 MRO（维护、维修、运营）采购场景。系统基于自然语言理解、SKU 检索、竞品检索、用户偏好记忆和批量询价能力，帮助用户从商品库中快速定位可采购物料。

**在线体验**：[https://mro.fultek.ai](https://mro.fultek.ai)

## 功能特性

- **自然语言找货**：支持“固定钢板用什么螺丝”“M8 不锈钢六角螺栓”“SMC 气缸”这类采购表达。
- **先搜再问**：宽泛需求会先展示候选商品，再通过参数卡片引导用户补充规格、品牌、用途等信息。
- **多轮上下文**：会话历史保存在 MySQL，Agent 冷启动或多副本切流后会从服务端历史恢复最近上下文。
- **流式回答**：`POST /api/chat` 通过 SSE 输出 thinking、SKU 结果、竞品结果、文本片段和结束事件。
- **服务端聊天历史**：用户登录后可跨设备查看、删除、重命名会话。
- **用户偏好记忆**：通过 Memos 保存会话摘要、SKU 反馈、ERP 导入偏好，并在后续搜索中影响排序和追问。
- **批量询价**：上传 `.xlsx` / `.xls` / `.csv` 询价表，批量匹配 SKU；支持下载询价模板。
- **图片/视觉输入**：聊天请求支持 `image_base64`，用于带图片的需求理解。

## 技术架构

```
┌────────────────────┐      /api       ┌──────────────────────────────────────┐
│ React + Vite SPA   │ ───────────────▶ │ FastAPI Backend                      │
│ Nginx static/proxy │ ◀── SSE stream ─ │ Auth / Chat / Inquiry / Profile      │
└────────────────────┘                  │ Agent orchestration                  │
                                        │ Intent parser / SKU search / Response│
                                        └──────────────┬──────────────┬────────┘
                                                       │              │
                                                   MySQL SKU      Memos memory
                                                   + history      + preference
```

### 前端

| 技术 | 用途 |
|---|---|
| React 18 + TypeScript | SPA UI |
| Tailwind CSS | 样式 |
| react-markdown + remark-gfm | Markdown 渲染 |
| Vite | 本地开发和构建 |
| Nginx | 生产静态托管和 `/api` 反向代理 |

### 后端

| 技术 | 用途 |
|---|---|
| FastAPI | API / SSE |
| SQLAlchemy async + aiomysql | MySQL 访问 |
| OpenAI SDK | OpenAI-compatible AI 接口 |
| Memos | 长期记忆和偏好存储 |
| openpyxl / xlrd | Excel 询价和 ERP 导入解析 |
| BeautifulSoup + httpx | 竞品检索 |

## 项目结构

```
mro-agent/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── migrations/
│   │   ├── 001_create_users.sql
│   │   ├── 002_create_chat_history.sql
│   │   └── 003_add_slot_clarification.sql
│   ├── static/询价选型模板.xls
│   └── app/
│       ├── main.py                  # FastAPI 入口和路由注册
│       ├── config.py                # 环境配置和生产校验
│       ├── db/mysql.py              # MySQL async session
│       ├── routers/
│       │   ├── auth.py              # 手机号注册/登录/token 校验
│       │   ├── chat.py              # SSE 聊天接口
│       │   ├── chat_history.py      # 服务端会话历史
│       │   ├── competitor.py        # 竞品检索接口
│       │   ├── feedback.py          # SKU 反馈写入 Memos
│       │   ├── inquiry.py           # 批量询价上传/模板下载
│       │   └── profile.py           # ERP 采购历史导入
│       └── services/
│           ├── agent.py             # Agent 主流程编排
│           ├── chat_history_service.py
│           ├── intent_parser.py
│           ├── sku_search.py
│           ├── response_gen.py
│           ├── memory_service.py
│           ├── competitor_search.py
│           ├── erp_importer.py
│           ├── preference_ranker.py
│           ├── standard_mapping.py
│           └── normalization.py
└── frontend/
    ├── Dockerfile
    ├── nginx.conf
    ├── package.json
    └── src/
        ├── App.tsx
        ├── components/
        │   ├── AuthModal.tsx
        │   ├── ChatWindow.tsx
        │   ├── ChatInput.tsx
        │   ├── MessageBubble.tsx
        │   ├── Sidebar.tsx
        │   ├── SkuCard.tsx
        │   ├── SlotClarificationCard.tsx
        │   └── InquiryPage.tsx
        └── services/
            ├── api.ts               # SSE chat + feedback
            ├── auth.ts              # auth token localStorage
            └── chatHistory.ts       # server-side sessions
└── extension/
    └── chrome/                      # Chrome Manifest V3 比价扩展
```

## 快速部署

### 前置要求

- Docker + Docker Compose
- MySQL 数据库，至少包含商品表 `t_item_sample` 和文件表 `t_item_file_sample`
- AI API Key，需兼容 OpenAI API 格式
- 可选：Memos 服务，用于长期记忆和偏好学习

### 1. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

`backend/.env` 示例：

```env
# Runtime
APP_ENV=development
CORS_ORIGINS=http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173

# MySQL
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=mro_agent_dev

# AI API (OpenAI-compatible)
AI_API_KEY=your_api_key
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
AI_MODEL=qwen-plus
AI_VISION_MODEL=qwen-vl-plus

# Memos memory service
MEMOS_URL=http://localhost:5230
MEMOS_ACCESS_TOKEN=
MEMOS_USERNAME=mro-admin
MEMOS_PASSWORD=

# Registration invite token
REGISTER_TOKEN=
```

支持的 AI 服务示例：

| 服务 | `AI_BASE_URL` | `AI_MODEL` |
|---|---|---|
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic-compatible proxy | 代理地址 | 代理支持的模型名 |

### 2. 初始化业务表

商品主表和文件表需要由业务数据源提供：

- `t_item_sample`
- `t_item_file_sample`

应用自有表通过迁移 SQL 初始化：

```bash
mysql -h <host> -P <port> -u <user> -p <database> < backend/migrations/001_create_users.sql
mysql -h <host> -P <port> -u <user> -p <database> < backend/migrations/002_create_chat_history.sql
mysql -h <host> -P <port> -u <user> -p <database> < backend/migrations/003_add_slot_clarification.sql
```

### 3. 启动服务

```bash
docker compose up -d --build
```

服务地址：

- 前端：`http://localhost:3000`
- 后端：`http://localhost:8000`
- 健康检查：`http://localhost:8000/health`
- Memos：`http://localhost:5230`

### 4. 生产配置要求

生产环境建议显式设置：

```env
APP_ENV=production
CORS_ORIGINS=https://mro.fultek.ai
REGISTER_TOKEN=<strong-invite-token>
MEMOS_ACCESS_TOKEN=<memos-access-token>
```

生产模式下后端会校验关键配置：

- `REGISTER_TOKEN` 必须非空，避免开放注册。
- `CORS_ORIGINS` 必须非空，只允许真实前端域名。
- 如果启用 `MEMOS_URL`，必须配置 `MEMOS_ACCESS_TOKEN`，或同时配置 `MEMOS_USERNAME` + `MEMOS_PASSWORD`。
- 后端默认 DB 指向本机开发库，不会默认连接远程样例库。

## 认证模型

当前认证是手机号 + 服务端随机 token：

1. `POST /api/auth/register` 注册用户。
2. `POST /api/auth/login` 登录并刷新 `auth_token`。
3. 前端把 `auth_token` 存在 `localStorage`。
4. 业务接口通过 `Authorization: Bearer <auth_token>` 鉴权。

注册接口支持邀请码：

- 开发环境：`REGISTER_TOKEN` 为空时允许开放注册。
- 生产环境：`APP_ENV=production` 且 `REGISTER_TOKEN` 为空时拒绝注册。

## Memos 长期记忆

Memos 用于保存和读取用户偏好：

- 每轮对话结束后写入 `#session` 摘要。
- 用户对 SKU 点赞/点踩后写入 `#feedback`。
- 每累计 10 次会话自动聚合 `#preference` 摘要。
- ERP 历史导入会写入 `#preference #erp-import`。
- Agent 每轮解析前读取近期 session、feedback、preference 作为上下文。

认证方式优先级：

1. `MEMOS_ACCESS_TOKEN`
2. `MEMOS_USERNAME` + `MEMOS_PASSWORD`

如果未配置 Memos 认证，记忆功能会降级失败并记录日志，不阻塞主聊天流程。

## API 接口

所有业务接口默认需要 `Authorization: Bearer <auth_token>`，除注册、登录、健康检查外。

### 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/auth/register` | 手机号注册，支持邀请码 |
| `POST` | `/api/auth/login` | 手机号登录，刷新 token |
| `GET` | `/api/auth/me` | 校验 token 并返回当前用户 |

### 聊天和历史

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/chat` | SSE 流式聊天 |
| `GET` | `/api/chat/sessions` | 会话列表 |
| `GET` | `/api/chat/sessions/{session_id}` | 会话详情 |
| `PATCH` | `/api/chat/sessions/{session_id}` | 重命名会话 |
| `DELETE` | `/api/chat/sessions/{session_id}` | 删除会话 |

`POST /api/chat` 请求示例：

```json
{
  "session_id": "abc123",
  "message": "M8 不锈钢六角螺栓",
  "image_base64": "optional-base64-image"
}
```

SSE 事件：

| 事件 | 数据 | 说明 |
|---|---|---|
| `thinking` | 文本 | 当前处理阶段 |
| `slot_clarification` | JSON | 参数补全卡片 |
| `sku_results` | JSON 数组 | 本站 SKU 匹配结果 |
| `competitor_results` | JSON 数组 | 竞品检索结果 |
| `text` | JSON 字符串 | 流式回答片段 |
| `done` | 空 | 响应结束 |
| `error` | 文本 | 错误信息 |

### 询价、偏好和竞品

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/inquiry/upload` | 上传 Excel/CSV，批量匹配 SKU，最多 200 行 |
| `GET` | `/api/inquiry/template` | 下载询价模板 |
| `POST` | `/api/feedback` | 保存 SKU 点赞/点踩反馈到 Memos |
| `POST` | `/api/profile/import` | 导入 ERP 采购历史并生成偏好摘要 |
| `GET` | `/api/competitor/search?q=...` | 检索竞品数据 |

### Chrome 扩展

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/api/extension/pairing-code` | Web 登录用户生成 5 分钟配对码 |
| `POST` | `/api/extension/register` | 扩展用配对码注册并换取 `extToken` |
| `GET` | `/api/extension/status` | Web 查询当前 active 扩展状态 |
| `POST` | `/api/extension/status` | 扩展上报心跳、版本、设备名和平台登录态 |

Chrome 扩展源码位于 `extension/chrome`，本地通过 `chrome://extensions/` 加载 unpacked 目录。

## AI 处理流程

```
用户消息 / 图片
  │
  ▼
加载上下文
  ├─ MySQL 最近会话消息（冷启动/多副本）
  └─ Memos 用户偏好/近期采购记录
  │
  ▼
意图解析 intent_parser
  ├─ 品类 / 关键词 / 品牌 / 规格
  ├─ query_type: precise / broad_spec / application / vague
  └─ slot_clarification 参数卡片
  │
  ▼
SKU 搜索 sku_search
  ├─ 精确型号 fast path
  ├─ 分类 + 关键词 + 规格 + 品牌变体
  ├─ relaxed_search 渐进降级
  └─ 等效标准替代搜索
  │
  ▼
竞品检索 + 偏好排序
  │
  ▼
流式响应 response_gen
  │
  ▼
保存聊天历史 + Memos 会话摘要
```

## 数据库表

业务数据表：

| 表 | 说明 |
|---|---|
| `t_item_sample` | 商品主表，包含编码、名称、品牌、规格、分类、属性、型号等字段 |
| `t_item_file_sample` | 商品文件表，包含技术资料、证书、检测报告等附件 |

应用自有表：

| 表 | 说明 |
|---|---|
| `t_user` | 手机号用户、token、会话计数 |
| `t_chat_session` | 服务端会话列表 |
| `t_chat_message` | 用户/助手消息、图片、SKU 结果、竞品结果、参数卡片 |

## 本地开发

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

Vite 开发服务默认在 `http://localhost:5173`，生产容器通过 Nginx 提供前端并代理 `/api` 到后端。

### 测试

```bash
PYTHONPATH=backend pytest backend/tests -q
```

当前测试覆盖：品牌/品类归一化、品牌聚类、标准映射、偏好排序、ERP 导入、Agent 上下文恢复等。

## 维护注意事项

- 不要把 `backend/.env`、`frontend/node_modules/`、`frontend/dist/`、`.DS_Store` 提交进仓库。
- `backend/app/services/agent.py` 仍保留进程内热缓存，但冷启动和多副本上下文来源是 `backend/app/services/chat_history_service.py` 读取的 MySQL 聊天历史。
- Memos 是增强能力，不应成为主聊天链路的硬依赖；相关异常应保持非阻塞。
- README 中的商品表字段是业务表最低依赖，真实库可以包含更多字段。

## License

MIT
