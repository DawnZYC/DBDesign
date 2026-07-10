# Strata — Backend

The FastAPI backend for Strata: a multi-agent analytics API that also imports EcoTEA WP1 Excel files into PostgreSQL (a 15-table schema).

## Directory structure

```
backend/
├── app/                            # application code
│   ├── main.py                     # FastAPI entry point
│   ├── config.py                   # configuration (.env loading)
│   ├── database.py                 # SQLAlchemy engine + Session
│   ├── models.py                   # ORM models for the 15 tables
│   ├── schemas.py                  # Pydantic API models
│   ├── routers/                    # API routes (health / imports / chat / rag / ...)
│   ├── agents/                     # LangGraph agents (planner / sql / tool / interpreter / ...)
│   ├── tools/                      # 6 function-calling tools
│   ├── rag/                        # ChromaDB vector store + embeddings
│   └── services/                   # excel_importer, value_cleaner
├── scripts/                        # one-off CLI scripts (run from backend/)
│   ├── seed_commodities.py         # seed the commodity dictionary
│   ├── seed_rag.py                 # seed the RAG vector store
│   └── verify_*.py                 # acceptance / smoke-check scripts
├── data/
│   └── domain_knowledge.md         # hand-written RAG source content
├── tests/
├── chroma_data/                    # generated vector store (gitignored)
├── requirements.txt
└── .env.example
```

## Quick start

```bash
cd backend

# 1) Activate the conda env and install dependencies
conda activate excelagent
pip install -r requirements.txt

# 2) Initialize the schema (using the DDL under sql/)
#    First create a database in your local PG, e.g. ecotea:
#    psql -U postgres -c "CREATE DATABASE ecotea;"
psql -U postgres -d ecotea -f ../sql/001_init_schema.sql

# 3) Configure environment variables
cp .env.example .env
# Edit .env to set DATABASE_URL to your local PG's actual value

# 4) Start the dev server
uvicorn app.main:app --reload --port 8000
```

> If you don't use conda, venv works too: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`

After starting:
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health (`?check_llm=true` actually hits the LLM once)
- LLM provider list: http://localhost:8000/api/llm/providers
- Preview (get the sheet list, no DB write): `POST http://localhost:8000/api/imports/preview`
- Import: `POST http://localhost:8000/api/imports` (multipart/form-data)

## LLM abstraction layer (M0)

Supports 6 providers, registry pattern; add a new provider with one line:

| provider | adapter | base_url | default model |
|---|---|---|---|
| `openai` (default) | OpenAI protocol | (official) | gpt-4o-mini |
| `deepseek` | OpenAI protocol | api.deepseek.com/v1 | deepseek-chat |
| `qwen` | OpenAI protocol | dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus |
| `moonshot` | OpenAI protocol | api.moonshot.cn/v1 | moonshot-v1-8k |
| `zhipu` | OpenAI protocol | open.bigmodel.cn/api/paas/v4/ | glm-4-plus |
| `anthropic` | standalone SDK | (official) | claude-3-5-haiku-latest |

To switch: set `LLM_PROVIDER=deepseek` in `.env`, fill `DEEPSEEK_API_KEY=...`, and restart.

Business code, uniformly:

```python
from app.llm import get_chat_model
llm = get_chat_model()  # decided by .env, returns a langchain BaseChatModel
result = llm.invoke([HumanMessage(content="...")])
```

Test:

```bash
python -m pytest tests/test_llm_provider.py -v
```

## RAG knowledge base (M1)

A persistent ChromaDB vector store, holding the three dictionaries (commodity / sector / geography) + the hand-written `domain_knowledge.md` (unit conversion / industry terminology / energy-system process classification).

**The embedding provider is also registry-based**; 3 providers go through the LangChain `Embeddings` abstraction:

| provider | description | default model | dimension |
|---|---|---|---|
| `huggingface` (default) | local sentence-transformers, zero cost | all-MiniLM-L6-v2 | 384 |
| `openai` | OpenAI online | text-embedding-3-small | 1536 |
| `qwen` | Tongyi Qianwen DashScope | text-embedding-v3 | 1024 |

After switching provider, note the dimensions differ; you must re-seed with `python scripts/seed_rag.py --reset`.

### One-off seeding

```bash
# 1) First ensure the sector / commodity dictionaries are in PG
psql -U zyc -d ecotea -f ../sql/001_init_schema.sql                  # create tables from scratch
python scripts/seed_commodities.py /path/to/your_source_workbook.xlsx   # ingest full commodity metadata

# 2) Seed the vector store
python scripts/seed_rag.py                      # PG dictionaries + data/domain_knowledge.md
# or
python scripts/seed_rag.py --reset              # use after switching embedding provider
```

The first run downloads the HuggingFace model (~80MB) to the local cache (`~/.cache/huggingface`); offline afterwards.

### Verify recall

```bash
python scripts/verify_rag.py                    # run 15 golden questions
```

Expected output:

```
recall@1  = 12/15 = 80%
recall@3  = 14/15 = 93%
```

### API endpoints

- `POST /api/rag/search` — semantic search
  ```bash
  curl -X POST http://localhost:8000/api/rag/search \
    -H "Content-Type: application/json" \
    -d '{"query": "natural gas power", "k": 3}'
  ```
- `GET /api/rag/info` — vector-store size + embedding provider status

Business code, uniformly:

```python
from app.rag import search
hits = search("carbon capture", k=5)
for h in hits:
    print(h.text, h.score, h.metadata)
```

### Test

```bash
python -m pytest tests/test_rag.py -v
```

## Function-calling tool set (M2)

6 tools, each = Pydantic args_schema + pure-Python implementation + LangChain `@tool` wrapper.
The LLM Agent uses function-calling to decide when to call which.

| # | Tool | Input | Purpose |
|---|---|---|---|
| 1 | `lookup_terminology` | term, k | RAG + PG dictionary lookup of commodity / sector / region |
| 2 | `convert_unit` | value, from_unit, to_unit | Cross-unit conversion for energy (PJ/ktoe/GWh/...) and CO2 (kt/Mt/...) |
| 3 | `run_sql` | QueryParams (metric / filters / aggregation / group_by) | **Pydantic strongly-typed parameterized SQL**, injection-proof; results carry `raw_row_id` for trace-back |
| 4 | `lookup_emission_factor` | tech_code, year | Look up a technology's emission factor for a year (falls back to the nearest year if missing) |
| 5 | `forecast_trend` | series, horizon, method | numpy.polyfit linear / quadratic extrapolation |
| 6 | `recommend_chart` | data_shape, intent | Rule engine, outputs an ECharts option skeleton |

### `run_sql` safety points

- **Does not accept raw SQL strings**; only a Pydantic `QueryParams`
- metric / aggregation / group_by are all `Literal` enums (whitelist)
- All WHERE clauses go through SQLAlchemy 2.0 `bindparam`
- Default `LIMIT 1000`, hard cap `MAX_LIMIT=10000`
- In raw mode, results always carry a `raw_row_id` field, for the M4 chart source-cell trace-back

The supported metrics (12) cover all numeric fields of EcoTEA / WP / Constraint / Commodity:
`capex / fixed_opex / variable_opex / emission_factor / tax_cost / subsidy_cost /
efficiency_value / technology_efficiency / heat_rate / capacity_to_activity_factor /
capacity / commodity_demand_value`.

### Agent integration (used in M3)

```python
from app.tools import ALL_TOOLS

# Bind directly to a LangChain LLM
llm_with_tools = llm.bind_tools(ALL_TOOLS)
response = llm_with_tools.invoke([HumanMessage(content="Total CAPEX of the Power sector in 2030")])
# response.tool_calls automatically contains the args the LLM decided to call run_sql with
```

### Test

```bash
# All unit tests for the 6 tools
python -m pytest tests/test_tool_*.py -v
```

## Command-line invocation (without the frontend)

Preview (see which sheets are in the file):
```bash
curl -X POST http://localhost:8000/api/imports/preview \
  -F "file=@../EcoTEA Endo WP1.xlsx" | python -m json.tool
```

Import all sheets:
```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "imported_by=zyc" \
  -F "note=first run"
```

Import only specific sheets (comma-separated allowlist):
```bash
curl -X POST http://localhost:8000/api/imports \
  -F "file=@../EcoTEA Endo WP1.xlsx" \
  -F "sheets=Power,Industry"
```

## Design highlights

- **3 data-cleaning rule classes** (consistent with ER diagram v2):
  - Placeholders (`-`, `NA`, empty) -> straight `NULL`, no trace
  - Formula errors (`#VALUE!`, `#REF!`, etc.) -> master table `NULL` + write `data_quality_issue` recording the original value
  - Mixed-semantic text (`COP: 3.91`) -> split into `_value` / `_text` / `_unit`
- **Granularity**: each `technology_year` = `(technology_id, data_year)`; all 5 satellites hang off it.
- **Upsert strategy**: sector / geography / commodity / data_source / technology_process are all upserted by business unique key; re-importing the same file won't blow a unique constraint.
- **Audit**: each raw Excel row is fully preserved in `raw_excel_row.raw_cells` (JSONB).

## Verify written data

```sql
-- Overview of the most recent import
SELECT * FROM import_batch ORDER BY imported_at DESC LIMIT 5;

-- How many rows were written per sheet
SELECT source_sheet_name, COUNT(*)
FROM raw_excel_row
WHERE import_batch_id = (SELECT MAX(import_batch_id) FROM import_batch)
GROUP BY source_sheet_name;

-- Exception tracing
SELECT * FROM data_quality_issue ORDER BY issue_id DESC LIMIT 20;
```
