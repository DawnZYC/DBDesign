# SG-TIMES Multi-Agent 智能分析平台

> 原 EcoTEA WP1 数据导入工具的升级版。研究员通过自然语言对话，驱动四节点 LangGraph 流水线完成跨年份、跨情景的数据查询与可视化；同时提供 VT 模型文件转换（Convert）、数据导入（含 Schema-Mapping 列对齐）与数据浏览的完整工作流。

---

## 里程碑进度

| 里程碑 | 内容 | 状态 |
|--------|------|------|
| **M0** | LLM Provider 抽象层（OpenAI / DeepSeek / Qwen / Moonshot / 智谱 / Anthropic 热切换） | ✅ 完成 |
| **M1** | ChromaDB 领域词汇 RAG（sentence-transformers 本地 Embedding，可切云端） | ✅ 完成 |
| **M2** | 6 类 Function-Calling 工具（terminology / unit_convert / run_sql / emission / forecast / chart） | ✅ 完成 |
| **M3** | LangGraph 四 Agent 图 + SSE 流式后端（`POST /api/chat/stream`） | ✅ 完成 |
| **M4** | Chat 前端（打字机流 / ECharts 图表 / 工具调用 Trace / 源单元格反查） | ✅ 完成 |
| **M5** | Schema-Mapping Agent（列对齐 + 置信度三档 + 质量门槛 + 人工复核 UI） | ✅ 完成 |
| **M6** | Docker Compose + GitHub Actions CI + eval 黄金问题集 | ✅ 完成 |
| **Convert** | VT 模型文件 → EcoTEA 标准工作簿转换（来自 main 分支） | ✅ 完成 |

---

## 界面：四步工作流

打开 http://localhost:5173，左侧边栏四个步骤：

| 步骤 | 功能 |
|------|------|
| **01 AI Assistant** | 自然语言对话，驱动 4-Agent 流水线查询 / 可视化（默认页） |
| **02 Convert** | 上传 VT 模型文件（VT_SG_PWR / VT_SG_PRI），转换为 EcoTEA 标准工作簿，可一键交接到 Import |
| **03 Import** | 拖入 Excel → 选 sheet → M5 列对齐复核（表头非标准时） → 导入 → sector 冲突复核 |
| **04 Browse** | 技术列表（行业 / 地区 / 关键词筛选 + 分页）+ 年份参数详情 |

---

## 技术栈

### 后端（Python 3.11+）

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI 0.115 + sse-starlette |
| ORM / 数据库 | SQLAlchemy 2.0、psycopg v3、PostgreSQL 16+ |
| Agent 编排 | LangGraph 0.2.62（StateGraph，4 节点流水线） |
| LLM | langchain-core 0.3.29 / langchain-openai / langchain-anthropic |
| 向量库 | ChromaDB + sentence-transformers（本地 Embedding，零成本，可切 OpenAI / DashScope） |
| 数据校验 | Pydantic v2 / pydantic-settings |
| 文件解析 | openpyxl 3.1（Convert 另用 pandas + xlrd） |
| Lint / 测试 | ruff + pytest（345+ 用例，CI 强制） |

> **依赖分两份**：`requirements.txt`（基础，CI / 云端 embedding 够用）+ `requirements-ml.txt`（本地 HuggingFace embedding 需要的 torch 系，~2GB）。

### 前端（Node 20+）

| 类别 | 技术 |
|------|------|
| 框架 | React 18 + TypeScript 5 + Vite 5 |
| 图表 | ECharts（via echarts-for-react） |
| SSE 流 | 原生 fetch + ReadableStream 手动解析 |
| Markdown | react-markdown + remark-gfm |
| 测试 | vitest + Testing Library（144 用例，CI 强制） |

---

## 快速启动（方式一：Docker，推荐）

```bash
# 1. 在项目根目录放一个 .env（或导出环境变量），至少包含：
#    OPENAI_API_KEY=sk-...
# 2. 一键起 postgres + backend + frontend：
docker compose up -d --build

# 3. 首次启动后，在容器内灌字典与 RAG 知识库：
docker compose exec backend python seed_commodities.py
docker compose exec backend python seed_rag.py
```

- 前端：http://localhost:5173（nginx 已配置 SSE 不缓冲，AI 流式正常）
- API 文档：http://localhost:8000/docs
- 建表 SQL 在 Postgres 容器首次启动时自动执行；ChromaDB 数据持久化在 `chroma_data` volume

## 快速启动（方式二：本地开发）

### 1. 准备 PostgreSQL

```bash
psql -U <你的用户名> -c "CREATE DATABASE ecotea;"
psql -U <你的用户名> -d ecotea -f sql/001_init_schema.sql
```

### 2. 配置环境变量

```bash
cd backend
cp .env.example .env
```

`.env` 最小配置：

```env
DATABASE_URL=postgresql+psycopg://<用户名>:<密码>@localhost:5432/ecotea
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_PROVIDER=huggingface
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### 3. 启动后端

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-ml.txt   # 本地 embedding 需要 ml 包
python seed_commodities.py && python seed_rag.py          # 首次：灌字典 + RAG
uvicorn app.main:app --reload --port 8000                 # 必须在 backend/ 目录下启动
```

### 4. 启动前端

```bash
cd frontend
npm install
npm run dev      # 必须在 frontend/ 目录下，SSE 代理才生效
```

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

SSE 事件：`agent_start` / `agent_end` / `plan` / `tool_call` / `tool_result` / `token` / `chart` / `error` / `done`。

图表数据点携带 `raw_row_id`，点击即可反查源 Excel 单元格（`GET /api/raw-rows/{id}`）。

---

## M5：Schema-Mapping 列对齐

SG-TIMES 版本迭代会导致 Excel 列改名 / 换位。导入时：

1. **快路径**：表头与标准模板一致 → 不调 Agent，按原硬编码列位导入（日常情况，零成本）
2. **慢路径**：表头对不上 → Agent 给每列匹配建议 + 置信度（确定性后端默认零成本；`use_llm_mapping=true` 切 LLM 后端）
   - ≥0.9 自动应用；0.6–0.9 进前端「列对齐复核」人工确认；<0.6 不导入
3. **质量门槛**：核心列（technology_code / data_year）缺失或覆盖率 <50% → 拒绝导入（HTTP 422），提示走 preview 人工复核
4. 低置信列写入 `data_quality_issue`，并通过 `ImportResult.column_warnings` 直接可见

---

## 评估（eval）

```bash
# 后端起好、数据导入后：
python eval/runner.py                      # 22 个黄金问题，逐题打分
python eval/runner.py --json report.json   # 机器可读报告
```

按关键词命中 / 工具调用 / 图表类型三个维度打分，通过率低于阈值（默认 80%）退出码非零，可挂 CI 非阻塞 job。

---

## API 参考

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/health` | 健康检查（`?check_llm=true` 真打 LLM 连通测试） |
| `GET` | `/api/llm/providers` | 6 个 LLM provider 配置状态 |
| `POST` | `/api/chat/stream` | AI 对话（SSE 流式） |
| `GET` | `/api/raw-rows/{id}` | 反查源 Excel 单元格 |
| `POST` | `/api/rag/search` | RAG 语义检索 |
| `GET` | `/api/convert/models` | 可用 VT 转换器列表 |
| `POST` | `/api/convert` | VT 文件 → EcoTEA 工作簿 |
| `GET` | `/api/convert/download/{token}` | 下载转换产物 |
| `POST` | `/api/imports/preview` | 预览 sheet 列表 + M5 列对齐建议（不入库） |
| `POST` | `/api/imports` | 上传导入（支持 `column_overrides` / `use_llm_mapping`） |
| `POST` | `/api/imports/preview/from-conversion` | 按 token 预览转换产物 |
| `POST` | `/api/imports/from-conversion` | 按 token 导入转换产物 |
| `GET` | `/api/imports/conflicts` | 列出待复核 sector 冲突 |
| `POST` | `/api/imports/conflicts/resolve` | 提交冲突复核结果 |
| `GET` | `/api/sectors` · `/api/geographies` · `/api/technologies` · `/api/technologies/{id}` | 浏览数据 |

---

## LLM Provider 切换

改 `.env` 两个字段即可热切换：

```env
LLM_PROVIDER=openai      # openai / deepseek / qwen / moonshot / zhipu / anthropic
LLM_MODEL=               # 留空用 provider 默认值
OPENAI_API_KEY=sk-...    # 对应 provider 的 key
```

除 Anthropic 外全部走 OpenAI-compatible 协议（同一个 `ChatOpenAI` 类 + base_url），新增 provider ≈ 注册表加一行。

---

## CI / CD

- `.github/workflows/ci.yml`：后端 ruff lint + format check + pytest（PG 17 service，带覆盖率）；前端 eslint + tsc + vitest + build
- `.github/workflows/build-images.yml`：构建并推送 backend / frontend 镜像到 GHCR + Trivy 扫描
- 后端镜像默认带 CPU-only torch（`--build-arg INSTALL_ML=false` 可进一步瘦身）
- 详见 `CI_CD_SETUP.md`

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

**`role "postgres" does not exist`** → 修改 `.env` 的 `DATABASE_URL` 为本机实际 PG 用户名。

**AI 助手没有任何输出** → ① 检查 `OPENAI_API_KEY` 是否填对；② 本地开发必须从 `frontend/` 目录跑 `npm run dev`（SSE 代理在 `vite.config.ts`）；Docker 部署的 SSE 不缓冲已在 `nginx.conf` 配好。

**导入返回 422「列布局自动对齐被拒绝」** → 文件表头与标准模板差异过大（核心列没对上）。先调 `POST /api/imports/preview` 查看列对齐建议，人工确认后带 `column_overrides` 重新导入。

**pip install 冲突** → 用 `requirements.txt` 锁定版本；`langgraph==0.2.62` 要求 `langchain-core>=0.3.29`。本地 embedding 另装 `requirements-ml.txt`（建议先装 CPU 版 torch：`pip install torch --index-url https://download.pytorch.org/whl/cpu`）。

**前端报 `Failed to fetch`** → 后端是否在 8000 端口、且从 `backend/` 目录启动（`.env` 按相对路径加载）。

**重复导入同一文件** → 不报错；字典与主表全部 upsert，仅新增一份 `import_batch` + `raw_excel_row`。

---

## 设计文档

- `others/PlanReadme.md` — 完整改造路线图（M0–M6 技术决策 + 实施细节）
- `CI_CD_SETUP.md` — CI/CD 流水线说明
- `eval/golden_questions.yaml` — 评估黄金问题集
- `others/EcoTEA_WP1_ER_Diagram_v2.html` — ER 图（15 张表）
