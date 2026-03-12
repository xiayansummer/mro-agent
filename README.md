# MRO 紧固件 AI 助手

智能工业品推荐系统 — 基于 AI 的 MRO（维护、维修、运营）紧固件采购助手，覆盖 200 万+ SKU，支持自然语言搜索、多轮对话、流式输出。

**在线体验**：[https://mro.fultek.ai](https://mro.fultek.ai)

---

## 功能特性

- **自然语言搜索** — 输入"M8不锈钢六角螺栓"或"固定钢板用什么螺丝"，AI 理解需求并推荐产品
- **先搜再问策略** — 需求宽泛时先展示一批候选产品，再引导用户细化参数
- **多轮对话** — 支持上下文理解，逐步缩小范围（如"有没有品牌好一点的"）
- **流式输出** — SSE 实时推送，打字机效果，可随时停止生成
- **聊天历史** — 侧边栏管理多个会话，localStorage 持久化，刷新不丢失
- **产品卡片** — 展示编码、品牌、规格、分类、属性、技术文件链接
- **Markdown 渲染** — 支持加粗、列表、表格、代码块等格式
- **响应式设计** — 桌面端侧边栏常驻，移动端 overlay 抽屉模式

## 技术架构

```
┌─────────────┐     ┌─────────────────────────────────────┐
│   Nginx     │     │           FastAPI Backend            │
│  (Frontend) │────▶│                                     │
│  Port 3000  │ /api│  Intent Parser ──▶ SKU Search       │
│             │     │       │               │              │
│  React SPA  │◀────│  Response Gen  ◀── MySQL (200万 SKU) │
│  Tailwind   │ SSE │                                     │
└─────────────┘     └─────────────────────────────────────┘
                              Port 8000
```

### 前端

| 技术 | 用途 |
|------|------|
| React 18 + TypeScript | UI 框架 |
| Tailwind CSS 3 | 样式 |
| react-markdown + remark-gfm | Markdown 渲染 |
| Vite 6 | 构建工具 |
| Nginx Alpine | 静态托管 + 反向代理 |

### 后端

| 技术 | 用途 |
|------|------|
| FastAPI | Web 框架 |
| SQLAlchemy + aiomysql | 异步 MySQL ORM |
| OpenAI SDK | AI 接口（兼容 Qwen/Claude/OpenAI） |
| SSE (Server-Sent Events) | 流式响应 |
| Uvicorn | ASGI 服务器 |

## 项目结构

```
mro-agent/
├── docker-compose.yml          # 编排配置
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example            # 环境变量模板
│   └── app/
│       ├── main.py             # FastAPI 入口
│       ├── config.py           # 配置管理
│       ├── db/
│       │   └── mysql.py        # 数据库连接池
│       ├── models/
│       │   └── sku.py          # SQLAlchemy 模型
│       ├── routers/
│       │   └── chat.py         # /api/chat SSE 端点
│       └── services/
│           ├── agent.py        # 主流程编排
│           ├── intent_parser.py # AI 意图解析
│           ├── sku_search.py   # 多字段搜索 + 渐进降级
│           └── response_gen.py # 流式响应生成
└── frontend/
    ├── Dockerfile
    ├── nginx.conf              # Nginx 反向代理配置
    ├── package.json
    └── src/
        ├── App.tsx             # 会话管理 + 布局
        ├── index.css           # 全局样式 + Markdown
        ├── types/index.ts      # TypeScript 类型定义
        ├── services/api.ts     # SSE 客户端
        └── components/
            ├── Sidebar.tsx     # 聊天历史侧边栏
            ├── ChatWindow.tsx  # 聊天主窗口
            ├── ChatInput.tsx   # 输入框 + 发送/停止按钮
            ├── MessageBubble.tsx # 消息气泡 + Markdown
            └── SkuCard.tsx     # 产品卡片
```

## 快速部署

### 前置要求

- Docker + Docker Compose
- MySQL 数据库（含 `t_item_sample` 和 `t_item_file_sample` 表）
- AI API Key（支持 OpenAI、Anthropic Claude、阿里通义千问等兼容接口）

### 1. 克隆项目

```bash
git clone https://github.com/xiayansummer/mro-agent.git
cd mro-agent
```

### 2. 配置环境变量

```bash
cp backend/.env.example backend/.env
```

编辑 `backend/.env`：

```env
# MySQL 数据库
DB_HOST=your_mysql_host
DB_PORT=3306
DB_USER=your_user
DB_PASSWORD=your_password
DB_NAME=your_database

# AI API（兼容 OpenAI 接口格式）
AI_API_KEY=your_api_key
AI_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # 通义千问示例
AI_MODEL=qwen-plus
```

**支持的 AI 服务**：

| 服务 | AI_BASE_URL | AI_MODEL |
|------|-------------|----------|
| 通义千问 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-sonnet-4-5-20250929` |

### 3. 启动服务

```bash
docker compose up -d --build
```

服务启动后：
- 前端：`http://localhost:3000`
- 后端 API：`http://localhost:8000`
- 健康检查：`http://localhost:8000/health`

### 4. 仅重建某个服务

```bash
# 只重建前端
docker compose up -d --build frontend

# 只重建后端
docker compose up -d --build backend
```

## 数据库表结构

### t_item_sample（商品主表）

| 字段 | 类型 | 说明 |
|------|------|------|
| item_code | VARCHAR(50) | 商品编码（主键） |
| item_name | VARCHAR(500) | 商品名称 |
| brand_name | VARCHAR(200) | 品牌 |
| specification | VARCHAR(500) | 规格型号 |
| unit | VARCHAR(50) | 单位 |
| l1_category_name | VARCHAR(200) | 一级分类 |
| l2_category_name | VARCHAR(200) | 二级分类 |
| l3_category_name | VARCHAR(200) | 三级分类 |
| l4_category_name | VARCHAR(200) | 四级分类 |
| attribute_details | TEXT | 属性详情（key:value 管道分隔） |

### t_item_file_sample（商品文件表）

| 字段 | 类型 | 说明 |
|------|------|------|
| item_code | VARCHAR(50) | 商品编码 |
| origin_file_name | VARCHAR(500) | 文件名 |
| file_path | VARCHAR(500) | 文件 URL |
| file_type | VARCHAR(10) | 301=技术资料 302=认证证书 303=检测报告 305=相关文档 |
| is_published | INT | 1=已发布 |

## API 接口

### POST /api/chat

流式聊天接口，返回 SSE 事件流。

**请求体**：

```json
{
  "session_id": "abc123",
  "message": "M8不锈钢六角螺栓"
}
```

**SSE 事件类型**：

| 事件 | 数据 | 说明 |
|------|------|------|
| `thinking` | 状态文本 | "正在搜索产品..." |
| `sku_results` | JSON 数组 | 匹配到的 SKU 列表 |
| `text` | 文本片段 | AI 推荐文本（逐块流式） |
| `done` | 空 | 响应结束 |
| `error` | 错误信息 | 出错时返回 |

## AI 处理流程

```
用户消息
  │
  ▼
意图解析（intent_parser）
  │  提取：分类、关键词、规格参数、品牌
  │  判断：need_clarification?
  │
  ▼
SKU 搜索（sku_search）
  │  1. 精确搜索：分类 + 名称关键词 + 规格参数
  │  2. 渐进降级：去规格 → 去细分类 → 去分类 → 单关键词
  │
  ▼
响应生成（response_gen）
  ├─ 精确匹配 → 标准推荐（排序 + 对比 + 建议）
  ├─ 宽泛匹配 → 概览 + 引导细化
  ├─ 无结果 + 追问 → 纯引导
  └─ 无结果 → 建议调整搜索
```

## 本地开发

### 后端

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 编辑配置
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev  # http://localhost:5173，自动代理 /api 到 :8000
```

## License

MIT
