# EcoTEA WP1 Import — Backend

FastAPI 后端，负责把 EcoTEA Excel 文件导入到 PostgreSQL（15 张表 schema）。

## 目录结构

```
backend/
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── config.py                   # 配置（.env 加载）
│   ├── database.py                 # SQLAlchemy engine + Session
│   ├── models.py                   # 15 张表的 ORM 模型
│   ├── schemas.py                  # Pydantic API 模型
│   ├── routers/
│   │   ├── health.py               # GET /api/health
│   │   └── imports.py              # POST /api/imports
│   └── services/
│       ├── value_cleaner.py        # 清洗 '-' / 'NA' / #VALUE! / 混合文本
│       └── excel_importer.py       # 主导入流程
├── requirements.txt
└── .env.example
```

## 快速启动

```bash
cd backend

# 1) 激活 conda 环境并装依赖
conda activate excelagent
pip install -r requirements.txt

# 2) 初始化 schema（用 sql/ 下的 DDL）
#    先在你的本地 PG 里建一个数据库，比如 ecotea：
#    psql -U postgres -c "CREATE DATABASE ecotea;"
psql -U postgres -d ecotea -f ../sql/001_init_schema.sql

# 3) 配置环境变量
cp .env.example .env
# 编辑 .env 把 DATABASE_URL 改成你本地 PG 的实际值

# 4) 启动 dev server
uvicorn app.main:app --reload --port 8000
```

> 如果你不用 conda，也可以用 venv：`python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

启动后：
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/health （`?check_llm=true` 真打一次 LLM）
- LLM provider 列表：http://localhost:8000/api/llm/providers
- 预览（拿 sheet 列表，不入库）：`POST http://localhost:8000/api/imports/preview`
- 导入：`POST http://localhost:8000/api/imports`（multipart/form-data）

## LLM 抽象层（M0）

支持 6 个 provider，注册表模式，加新 provider 改一行：

| provider | 适配器 | base_url | 默认模型 |
|---|---|---|---|
| `openai`（默认） | OpenAI 协议 | (官方) | gpt-4o-mini |
| `deepseek` | OpenAI 协议 | api.deepseek.com/v1 | deepseek-chat |
| `qwen` | OpenAI 协议 | dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| `moonshot` | OpenAI 协议 | api.moonshot.cn/v1 | moonshot-v1-8k |
| `zhipu` | OpenAI 协议 | open.bigmodel.cn/api/paas/v4/ | glm-4-plus |
| `anthropic` | 独立 SDK | (官方) | claude-3-5-haiku-latest |

切换：`.env` 改 `LLM_PROVIDER=deepseek`，填 `DEEPSEEK_API_KEY=...`，重启即可。

业务代码统一：

```python
from app.llm import get_chat_model
llm = get_chat_model()  # 按 .env 决定，返回 langchain BaseChatModel
result = llm.invoke([HumanMessage(content="...")])
```

测试：

```bash
python -m pytest tests/test_llm_provider.py -v
```

## RAG 知识库（M1）

ChromaDB 持久化向量库，承载 commodity / sector / geography 三张字典 + 手写 `domain_knowledge.md`（单位换算 / 行业术语 / SG-TIMES 工艺分类）。

**Embedding provider 同样是注册表模式**，3 个 provider 走 LangChain `Embeddings` 抽象：

| provider | 说明 | 默认模型 | 维度 |
|---|---|---|---|
| `huggingface`（默认） | 本地 sentence-transformers，零成本 | all-MiniLM-L6-v2 | 384 |
| `openai` | OpenAI 在线 | text-embedding-3-small | 1536 |
| `qwen` | 通义千问 DashScope | text-embedding-v3 | 1024 |

切 provider 后注意维度不同，需 `python seed_rag.py --reset` 重新灌库。

### 一次性灌库

```bash
# 1) 先确保 PG 里 sector / commodity 字典已就位
psql -U zyc -d ecotea -f ../sql/001_init_schema.sql           # 全新建表
python seed_commodities.py /path/to/VT_SG_PWR_GREF.xlsx        # 灌入 commodity 完整元数据

# 2) 灌入向量库
python seed_rag.py                              # PG 字典 + domain_knowledge.md
# 或
python seed_rag.py --reset                      # 切了 embedding provider 后用
```

首次运行会下载 HuggingFace 模型（~80MB）到本机缓存（`~/.cache/huggingface`），之后离线可用。

### 验证 recall

```bash
python verify_rag.py                            # 跑 15 个金标问题
```

期望输出：

```
recall@1  = 12/15 = 80%
recall@3  = 14/15 = 93%
```

### API 端点

- `POST /api/rag/search` — 语义检索
  ```bash
  curl -X POST http://localhost:8000/api/rag/search \
    -H "Content-Type: application/json" \
    -d '{"query": "natural gas power", "k": 3}'
  ```
- `GET /api/rag/info` — 向量库大小 + embedding provider 状态

业务代码统一：

```python
from app.rag import search
hits = search("carbon capture", k=5)
for h in hits:
    print(h.text, h.score, h.metadata)
```

### 测试

```bash
python -m pytest tests/test_rag.py -v
```

## Function-Calling 工具集（M2）

6 个工具，每个 = Pydantic args_schema + 纯 Python 实现 + LangChain `@tool` 包装。
LLM Agent 通过 function-calling 自动决定何时调用哪个。

| # | 工具 | 输入 | 用途 |
|---|---|---|---|
| ① | `lookup_terminology` | term, k | RAG + PG 字典查商品 / 行业 / 地区 |
| ② | `convert_unit` | value, from_unit, to_unit | 能源 (PJ/ktoe/GWh/...) 与 CO₂ (kt/Mt/...) 跨单位换算 |
| ③ | `run_sql` | QueryParams（metric / 过滤 / 聚合 / group_by） | **Pydantic 强类型参数化 SQL**，杜绝注入；结果带 `raw_row_id` 反查 |
| ④ | `lookup_emission_factor` | tech_code, year | 查某技术某年排放因子（年份不存在自动回退最近年） |
| ⑤ | `forecast_trend` | series, horizon, method | numpy.polyfit 线性 / 二次外推 |
| ⑥ | `recommend_chart` | data_shape, intent | 规则引擎，输出 ECharts option 骨架 |

### `run_sql` 安全要点

- **不接收原始 SQL 字符串**，只接收 Pydantic `QueryParams`
- metric / aggregation / group_by 都是 `Literal` 枚举（白名单）
- WHERE 全部走 SQLAlchemy 2.0 `bindparam`
- 默认 `LIMIT 1000`，硬上限 `MAX_LIMIT=10000`
- raw 模式下结果一定带 `raw_row_id` 字段，供 M4 图表反查源单元格

支持的 metric（12 个）涵盖 EcoTEA / WP / Constraint / Commodity 全部数值字段：
`capex / fixed_opex / variable_opex / emission_factor / tax_cost / subsidy_cost /
efficiency_value / technology_efficiency / heat_rate / capacity_to_activity_factor /
capacity / commodity_demand_value`。

### Agent 集成（M3 用）

```python
from app.tools import ALL_TOOLS

# 直接绑给 LangChain LLM
llm_with_tools = llm.bind_tools(ALL_TOOLS)
response = llm_with_tools.invoke([HumanMessage(content="2030 年 Power 部门 CAPEX 总和")])
# response.tool_calls 自动包含 LLM 决定调用 run_sql 的入参
```

### 测试

```bash
# 6 个工具的全部单测
python -m pytest tests/test_tool_*.py -v
```

## 命令行直接调用（不走前端）

预览（看文件里有哪些 sheet）：
```bash
curl -X POST http://localhost:8000/api/imports/preview \
  -F "file=@../EcoTEA Endo WP1.xlsx" | python -m json.tool
```

导入全部 sheet：
```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "imported_by=zyc" \
  -F "note=first run"
```

只导入指定 sheet（白名单逗号分隔）：
```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "sheets=Power,Industry"
```

## 设计要点

- **数据清洗 3 类规则**（与 ER 图 v2 一致）：
  - 占位符（`-`、`NA`、空）→ 直接 `NULL`，不留痕
  - 公式错误（`#VALUE!`、`#REF!` 等）→ 主表 `NULL` + 写 `data_quality_issue` 记录原值
  - 混合语义文本（`COP: 3.91`）→ 拆出 `_value` / `_text` / `_unit`
- **粒度**：每条 `technology_year` = `(technology_id, data_year)`，5 张 satellite 都挂在它下面。
- **upsert 策略**：sector / geography / commodity / data_source / technology_process 全部按业务唯一键 upsert；同一个文件重复导入不会爆唯一约束。
- **审计**：每行原始 Excel 数据完整保留在 `raw_excel_row.raw_cells` (JSONB)。

## 验证已写入数据

```sql
-- 最近一次导入的概况
SELECT * FROM import_batch ORDER BY imported_at DESC LIMIT 5;

-- 各 sheet 写入了多少行
SELECT source_sheet_name, COUNT(*)
FROM raw_excel_row
WHERE import_batch_id = (SELECT MAX(import_batch_id) FROM import_batch)
GROUP BY source_sheet_name;

-- 异常追踪
SELECT * FROM data_quality_issue ORDER BY issue_id DESC LIMIT 20;
```
