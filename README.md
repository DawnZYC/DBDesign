# SG-TIMES Multi-Agent 智能分析平台

> 原 EcoTEA WP1 数据导入工具的升级版。研究员通过自然语言对话，驱动四节点 LangGraph 流水线完成跨年份、跨情景的数据查询与可视化，完整保留原有数据导入 / 冲突复核 / 浏览视图功能。

---

## 里程碑进度

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| **M0** | LLM Provider 抽象层（OpenAI / DeepSeek / Qwen / Anthropic 热切换） | ✅ 完成 |
| **M1** | ChromaDB 领域词汇 RAG（sentence-transformers 本地 Embedding） | ✅ 完成 |
| **M2** | 6 类 Function-Calling 工具（run_sql / stat_analysis / recommend_chart 等） | ✅ 完成 |
| **M3** | LangGraph 四 Agent 图 + SSE 流式后端（`POST /api/chat/stream`） | ✅ 完成 |
| **M4** | Chat 前端（打字机流 / ECharts 图表 / 工具调用 Trace / 源单元格反查） | ✅ 完成 |
| **M5** | Schema-Mapping Agent + 冲突复核 UI 改造 | 🚧 规划中 |
| **M6** | Docker Compose + GitHub Actions CI + eval 黄金问题集 | 🚧 规划中 |

---

## 技术栈

### 后端（Python 3.11+）

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.115 + sse-starlette |
| ORM / 数据库 | SQLAlchemy 2.0、psycopg v3、PostgreSQL 16 |
| Agent 编排 | LangGraph 0.2.62（StateGraph，4 节点流水线） |
| LLM | langchain-core 0.3.29 / langchain-openai / langchain-anthropic |
| 向量库 | ChromaDB + sentence-transformers（本地 Embedding，零成本） |
| 数据校验 | Pydantic v2 / pydantic-settings |
| 文件解析 | openpyxl 3.1 |

### 前端（Node 20+）

| 类别 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript 5 + Vite 5 |
| 图表 | ECharts（via echarts-for-react） |
| SSE 流 | 原生 fetch + ReadableStream 手动解析 |
| Markdown | react-markdown + remark-gfm |

---

## 项目结构

```
DBDesign/
├── sql/
│   └── 001_init_schema.sql          # 15 张表 DDL（含约束 / 索引 / sector 预置数据）
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI 入口，挂载所有 router
│   │   ├── config.py                # pydantic-settings，从 .env 加载配置
│   │   ├── database.py              # SQLAlchemy engine + session 工厂
│   │   ├── models.py                # 15 张表 ORM
│   │   ├── schemas.py               # API Pydantic schema
│   │   ├── llm/
│   │   │   └── provider.py          # LLM 工厂（OpenAI / DeepSeek / Qwen / Anthropic）
│   │   ├── rag/                     # ChromaDB 向量检索（M1）
│   │   ├── tools/                   # Function-Calling 工具实现（M2）
│   │   │   ├── sql_runner.py        # run_sql：安全执行 SELECT + 截断保护
│   │   │   ├── stat_analysis.py     # 统计分析工具
│   │   │   ├── chart.py             # recommend_chart：图表类型推荐
│   │   │   └── ...
│   │   ├── agents/                  # LangGraph 四 Agent 图（M3）
│   │   │   ├── graph.py             # StateGraph 定义 + 条件边
│   │   │   ├── state.py             # AgentState TypedDict
│   │   │   ├── planner.py           # Planner：意图理解 → 执行计划
│   │   │   ├── sql_agent.py         # SQL Agent：生成并执行 SQL
│   │   │   ├── interpreter.py       # Interpreter：流式文本解读（astream）
│   │   │   └── visualizer.py        # Visualizer：生成 ECharts spec
│   │   ├── routers/
│   │   │   ├── health.py            # GET /api/health
│   │   │   ├── imports.py           # POST /api/imports（导入 / 冲突复核）
│   │   │   ├── browse.py            # GET /api/technologies, /api/sectors 等
│   │   │   ├── chat.py              # POST /api/chat/stream（SSE，M3）
│   │   │   ├── raw_rows.py          # GET /api/raw-rows/{id}（反查源单元格，M4）
│   │   │   └── rag.py               # RAG 相关端点（M1）
│   │   └── services/
│   │       ├── excel_importer.py    # Excel 导入主逻辑（含 savepoint 行级回滚）
│   │       └── value_cleaner.py     # 占位符 / 公式错误 / 混合文本清洗
│   ├── requirements.txt
│   └── .env                         # 本地配置（不入 git）
├── frontend/
│   ├── src/
│   │   ├── api.ts                   # 所有后端调用（含 SSE streamChat）
│   │   ├── types.ts                 # 全局 TypeScript 类型
│   │   ├── pages/
│   │   │   └── ChatPage.tsx         # AI 助手 Chat 界面（M4）
│   │   └── chat/
│   │       ├── useStreamChat.ts     # SSE 流管理 hook
│   │       ├── MessageList.tsx      # 消息列表（含 Markdown 渲染）
│   │       ├── MessageBubble.tsx    # 单条消息气泡
│   │       ├── ToolCallTrace.tsx    # 工具调用 Trace 展开面板
│   │       └── ChartBubble.tsx      # ECharts 图表气泡
│   ├── vite.config.ts               # SSE 代理配置（no-buffer）
│   └── package.json
├── others/
│   └── PlanReadme.md                # 完整改造路线图
└── README.md（本文件）
```

---

## 快速启动

### 1. 准备 PostgreSQL

```bash
# 新建数据库（替换为你自己的用户名）
psql -U zyc -c "CREATE DATABASE ecotea;"
psql -U zyc -d ecotea -f sql/001_init_schema.sql
```

执行成功后最后一行为 `COMMIT`，`sector` 表自动预置 10 行行业数据。

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env   # 若无 .env.example 则直接编辑 .env
```

`.env` 最小配置（其余字段保持默认即可）：

```env
# 数据库连接
DATABASE_URL=postgresql+psycopg://zyc:123456@localhost:5432/ecotea

# LLM（主 provider）
LLM_PROVIDER=openai
LLM_MODEL=                    # 留空使用默认 gpt-4o-mini
OPENAI_API_KEY=sk-...         # 填入你的 OpenAI API Key

# 可选：切换国产模型（取消注释任意一项）
# LLM_PROVIDER=deepseek
# DEEPSEEK_API_KEY=...

# Embedding（默认本地，零成本）
EMBEDDING_PROVIDER=huggingface

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### 3. 启动后端

```bash
cd backend
conda activate excelagent       # 或：python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 必须在 backend/ 目录下启动，否则 .env 路径解析异常
uvicorn app.main:app --reload --port 8000
```

启动后验证：

- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health → 应返回 `{"status":"ok","database":"ok"}`

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev
```

打开 http://localhost:5173，包含三个标签页：

- **AI 助手**：自然语言对话，驱动 4-Agent 流水线查询 / 可视化
- **导入数据**：拖入 Excel → 选 sheet → 导入 → 冲突复核
- **浏览数据**：技术列表（行业 / 地区 / 关键词筛选 + 分页）

---

## 四 Agent 流水线

```
用户提问
    │
    ▼
┌─────────┐   执行计划   ┌───────────┐   QueryParams   ┌─────────────┐
│ Planner │ ──────────► │ SQL Agent │ ──────────────► │ Interpreter │
│  意图理解 │             │ SQL 生成/执行│                │  流式文本解读 │
└─────────┘             └───────────┘                 └──────┬──────┘
                              │                              │ interpretation
                              │ sql_result                   ▼
                              │                       ┌────────────┐
                              └──────────────────────► │ Visualizer │
                                                       │ ECharts 生成│
                                                       └────────────┘
```

所有阶段通过 `POST /api/chat/stream` 以 SSE 实时推送给前端，共 8 种事件类型：

| 事件 | 含义 |
|------|------|
| `agent_start` | 某节点开始执行 |
| `agent_end` | 某节点执行完毕 |
| `plan` | Planner 输出的执行步骤列表 |
| `tool_call` | SQL Agent 发起工具调用 |
| `tool_result` | 工具调用返回结果摘要 |
| `token` | Interpreter 流式输出的单个 token（打字机效果） |
| `chart` | Visualizer 输出的完整 ECharts spec |
| `error` | 局部错误（流仍继续） |
| `done` | 流结束信号（含 trace_id） |

---

## API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查 |
| `POST` | `/api/chat/stream` | AI 对话（SSE 流式） |
| `GET` | `/api/raw-rows/{id}` | 反查源 Excel 单元格 |
| `POST` | `/api/imports/preview` | 预览 Excel sheet 列表（不入库） |
| `POST` | `/api/imports` | 上传 Excel 并触发导入 |
| `GET` | `/api/imports/conflicts` | 列出待复核冲突 |
| `POST` | `/api/imports/conflicts/resolve` | 提交冲突复核结果 |
| `GET` | `/api/sectors` | 所有行业 |
| `GET` | `/api/geographies` | 所有地区 |
| `GET` | `/api/technologies` | 技术列表（支持分页 / 筛选） |
| `GET` | `/api/technologies/{id}` | 技术详情 |

---

## LLM Provider 切换

修改 `.env` 中的两个字段即可热切换，无需改代码：

```env
# OpenAI（默认）
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=sk-...

# DeepSeek（OpenAI 兼容）
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=...

# 通义千问（DashScope）
LLM_PROVIDER=qwen
LLM_MODEL=qwen-plus
DASHSCOPE_API_KEY=...

# Anthropic Claude（独立 SDK）
LLM_PROVIDER=anthropic
LLM_MODEL=claude-3-5-haiku-latest
ANTHROPIC_API_KEY=...
```

---

## 数据清洗规则

代码位于 `backend/app/services/value_cleaner.py`：

| 输入 | 处理 | 是否写 data_quality_issue |
|------|------|--------------------------|
| `'-'` / `'NA'` / 空字符串 / 空白 | → `NULL` | 否 |
| `#VALUE!` / `#REF!` / `#DIV/0!` 等 | 主表 → `NULL` | **是**（含原值 + 行号 + 列号） |
| `0.497` 纯数字 | 直接存 | 否 |
| `'COP: 3.91'` / `'13.33 km/litre'` | 拆为 `_value` + `_text` + `_unit` | 否（efficiency 列） |
| `'PWRBMS+PWACOA'` / `'20%+80%'` | 按 `+` 拆成多条 `technology_year_commodity` | 否 |

---

## 常见问题

**`role "postgres" does not exist`** → 修改 `.env` 的 `DATABASE_URL`，改为你本机实际的 PG 用户名。

**AI 助手没有任何输出** → 检查两点：① 后端 `.env` 中 `OPENAI_API_KEY` 字段是否正确填入（不是 `LLM_MODEL`）；② Vite 代理必须从 `frontend/` 目录执行 `npm run dev`，SSE 代理配置已在 `vite.config.ts` 中设置。

**pip install 冲突** → 确保使用 `requirements.txt` 中锁定的版本，核心约束：`langgraph==0.2.62` 要求 `langchain-core>=0.3.29`，不兼容 `0.3.0–0.3.22` 区间。

**前端报 `Failed to fetch`** → 确认后端已在 8000 端口启动，且必须在 `backend/` 目录下执行 `uvicorn`（pydantic-settings 从相对路径加载 `.env`）。

**重复导入同一文件** → 不会报错；sector / commodity / technology_process / technology_year 全部走 upsert，仅新增一份 `import_batch` + `raw_excel_row` 记录。

---

## 设计文档

- `others/PlanReadme.md` — 完整改造路线图（M0–M6 技术决策 + 实施细节）
- `EcoTEA_WP1_ER_Diagram_v2.html` — 修正版 ER 图（15 张表 + 变更标记）
- `EcoTEA_Design_Review.html` — 实际数据对 schema 的核查报告
- `EcoTEA_Sample_Row_Mapping.html` — 单行 Power 数据 Excel → 数据库填表演示
