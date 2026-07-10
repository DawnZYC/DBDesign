# Strata — Multi-Agent Energy Model Analytics

> **Strata** turns the **EcoTEA WP1** energy-system model dataset into a conversational
> analytics platform. Researchers ask questions in plain language and a LangGraph multi-agent
> pipeline plans the query, runs safe parameterized SQL (or calls function-calling tools),
> interprets the result, and renders an interactive chart — every data point traceable back to the
> original Excel cell. It also ships a full data-ops workflow: VT model-file **conversion**, Excel
> **import** with automatic column alignment, and a **browse** view over the technology database.

```
 Natural language ─▶ Plan ─▶ SQL / Tools ─▶ Interpret ─▶ Chart ─▶ (click) ─▶ source Excel cell
```

---

## Table of contents

- [What it does](#what-it-does)
- [Key features](#key-features)
- [The four-step UI](#the-four-step-ui)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Quick start (Docker)](#quick-start-docker)
- [Quick start (local dev)](#quick-start-local-dev)
- [How the agent pipeline works](#how-the-agent-pipeline-works)
- [The six function-calling tools](#the-six-function-calling-tools)
- [Schema-Mapping (column alignment)](#schema-mapping-column-alignment)
- [RAG knowledge base](#rag-knowledge-base)
- [Data model](#data-model)
- [API reference](#api-reference)
- [Configuration](#configuration)
- [LLM / embedding provider switching](#llm--embedding-provider-switching)
- [Evaluation](#evaluation)
- [Testing](#testing)
- [CI / CD](#ci--cd)
- [Troubleshooting](#troubleshooting)
- [Design docs](#design-docs)

---

## What it does

Energy-system modellers keep their techno-economic data (capex, O&M, emission factors, capacity,
commodity flows) in large multi-sheet Excel workbooks (EcoTEA WP1). Answering even a simple
cross-year / cross-sector question means manually digging through sheets and columns.

Strata replaces that with a chat box:

- **Ask data questions** — *"Power sector capex trend 2018-2050"* → a streamed explanation **plus**
  a line chart, with each point clickable to reveal the exact source `Sheet!Cell`.
- **Ask domain questions** — *"What does commodity code BIOMASS01 mean, and which technologies use
  it?"* or *"Convert 1 PJ of natural gas to ktoe"* → answered by real **function-calling tools** (RAG
  lookup, exact unit conversion), not the model's imagination.
- **Onboard new data** — convert a VT model file into the standard EcoTEA workbook, import it (with
  automatic column-layout alignment when the template drifts), and browse the result.

---

## Key features

| Area | Highlights |
|------|------------|
| **Multi-agent orchestration** | LangGraph state graph: **Planner → SQL Agent → Interpreter → Visualizer**, plus a **Tool Agent** for function-calling, with intent routing and SQL-failure retries. |
| **Real function-calling** | The LLM autonomously picks among 4 auxiliary tools (terminology / unit / emission / forecast). `run_sql` stays a structured, injection-safe path; `recommend_chart` is a rule engine. |
| **Injection-safe SQL** | The SQL Agent emits a Pydantic `QueryParams` (no raw SQL); queries compile to SQLAlchemy `select()` with bound params, a metric whitelist, and a hard row cap. |
| **Streaming UX** | Server-Sent Events stream the agent trace + typewriter tokens + the final ECharts spec. Stop button, reply-language selector, example prompts, and an "LLM not configured" pre-flight. |
| **Source-cell traceback** | Every raw query row carries `raw_row_id`; clicking a chart point opens the original Excel row (sheet, row number, raw cells, import batch). |
| **RAG knowledge base** | ChromaDB over commodity / sector / geography dictionaries + a hand-written domain manual; local sentence-transformers embeddings by default (zero cost, offline). |
| **Schema-Mapping Agent** | When an uploaded sheet's columns drift from the canonical template, an agent re-aligns them (auto / human-review / reject) so the hard-coded importer keeps working. |
| **VT → EcoTEA conversion** | Pluggable per-model converters (VT_SG_PWR, VT_SG_PRI) produce a standard workbook, with one-click handoff to import. |
| **Provider-agnostic** | OpenAI / DeepSeek / Qwen / Moonshot / Zhipu / Anthropic via a registry + factory; hot-swap with two `.env` lines. |
| **Engineering** | Pinned deps, ruff lint+format, pytest (backend) + vitest (frontend), Docker Compose, GitHub Actions CI, a golden-question eval harness. |

---

## The four-step UI

Open **http://localhost:5173** — the left sidebar is a four-step workflow (views stay mounted, so
chat history / import progress / browse filters survive tab switches):

| Step | View | What it does |
|------|------|--------------|
| **01 AI Assistant** | Chat | Natural-language Q&A driving the agent pipeline (default page). Reply-language selector, stop generation, tool-call trace, embedded charts, source-cell traceback. |
| **02 Convert** | Convert | Upload a VT model file (`.xlsx/.xlsm/.xls`) → standard EcoTEA workbook, with one-click handoff to Import. |
| **03 Import** | Import | Drop an Excel workbook → pick sheets → **column-alignment review** (only if headers drift) → import → **sector-conflict review**. |
| **04 Browse** | Browse | Filter/search technologies (sector / geography / keyword + pagination); click a row, then expand a year for the full parameter set. |

---

## Architecture

```
┌──────────────────────────── Frontend (React + TS + Vite) ───────────────────────────┐
│  AI Assistant · Convert · Import · Browse        ECharts · react-markdown · SSE      │
└───────────────┬──────────────────────────────────────────────────────────────────────┘
                │  POST /api/chat/stream (text/event-stream)   +  REST
┌───────────────▼──────────────────────────── Backend (FastAPI) ───────────────────────┐
│                                                                                       │
│   LangGraph state graph (app/agents/graph.py)                                         │
│                                                                                       │
│                 ┌──────────┐  data_query   ┌───────────┐   ┌─────────────┐  chart      │
│        START ─▶ │ Planner  │ ────────────▶ │ SQL Agent │─▶ │ Interpreter │─▶ Visualizer│
│                 │ (intent) │               │ QueryParams│  │ (stream)    │   (ECharts) │
│                 └────┬─────┘               └─────┬─────┘   └──────┬──────┘             │
│                      │ tool_query                │ retry on error │                    │
│                      ▼                           └────▶ Planner   │                    │
│                 ┌──────────┐  bind_tools                          │                    │
│                 │Tool Agent│ ──(terminology/unit/emission/forecast)─▶ Interpreter ─▶END│
│                 └──────────┘                                                           │
│                      ▲ chat (direct answer) ─────────────────────▶ Interpreter ─▶ END  │
│                                                                                       │
│   Tools (app/tools)   RAG (app/rag, ChromaDB)   LLM provider layer (app/llm)          │
│   Importer + Schema-Mapping (app/services, app/agents/schema_mapper)                  │
│   Converters (app/converters)                                                         │
│                                                                                       │
└───────────────┬───────────────────────────────┬──────────────────────────────────────┘
                │                                │
        PostgreSQL 17 (15-table schema)   ChromaDB (persistent vector store)
```

**SSE event protocol** (emitted by `POST /api/chat/stream`):
`agent_start` · `plan` · `tool_call` · `tool_result` · `token` (streamed) · `chart` · `agent_end` ·
`error` · `done`.

---

## Tech stack

### Backend (Python 3.11+)

| Category | Choice |
|----------|--------|
| Web / streaming | FastAPI `0.115.5`, sse-starlette `2.1.3`, uvicorn |
| ORM / DB | SQLAlchemy `2.0.35` (psycopg v3), **PostgreSQL 17** |
| Agents | LangGraph `0.2.62` (StateGraph, conditional edges) |
| LLM | langchain-core `0.3.29`, langchain-openai `0.2.14`, langchain-anthropic `0.3.0` |
| Vector store | ChromaDB `0.5.23`, langchain-chroma; **sentence-transformers `3.3.1`** (local, default) |
| Validation | Pydantic `2.10.3` / pydantic-settings |
| Excel | openpyxl `3.1.5` (Convert also uses pandas) |
| Numerics | numpy `1.26.4` (forecast tool) |
| Quality | ruff (lint + format), pytest + coverage |

> Dependencies split in two: `requirements.txt` (base, enough for CI / cloud embeddings) +
> `requirements-ml.txt` (the torch stack for local HuggingFace embeddings, ~2 GB).

### Frontend (Node 20+)

| Category | Choice |
|----------|--------|
| Framework | React `18.3`, TypeScript `5`, Vite `5` |
| Charts | ECharts `5.5` via echarts-for-react |
| Streaming | SSE over `fetch` + `ReadableStream` (manual parse, dependency-light) |
| Markdown | react-markdown `9` + remark-gfm |
| Tests | vitest + Testing Library |

---

## Repository layout

```
Strata/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app + CORS + router registration
│   │   ├── config.py            # pydantic-settings (.env)
│   │   ├── database.py          # engine + Session factory
│   │   ├── models.py            # 15-table ORM (anchor / satellite)
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── agents/              # LangGraph nodes
│   │   │   ├── graph.py         #   state graph + intent routing + retries
│   │   │   ├── planner.py       #   intent (data_query / tool_query / chat) + steps
│   │   │   ├── sql_agent.py     #   structured QueryParams → run_sql
│   │   │   ├── tool_agent.py    #   real function-calling over the aux tools
│   │   │   ├── interpreter.py   #   streamed answer (data / tool / chat)
│   │   │   ├── visualizer.py    #   ECharts spec assembly
│   │   │   ├── schema_mapper.py #   M5 column alignment (ingestion-side agent)
│   │   │   ├── context.py       #   multi-turn context helper
│   │   │   └── state.py         #   AgentState TypedDict
│   │   ├── tools/               # 6 function-calling tools
│   │   ├── rag/                 # ChromaDB client, embeddings, ingest, search
│   │   ├── routers/             # health, chat, rag, raw_rows, imports, convert, browse
│   │   ├── services/            # excel_importer, value_cleaner
│   │   ├── converters/          # VT → EcoTEA (engine + per-model adapters)
│   │   └── assets/              # bundled EcoTEA template
│   ├── scripts/                 # seed_commodities, seed_rag, verify_* (run from backend/)
│   ├── data/                    # domain_knowledge.md (RAG source content)
│   ├── tests/                   # pytest suites
│   ├── Dockerfile / requirements*.txt / pyproject.toml
│   └── chroma_data/             # generated vector store (gitignored)
├── frontend/
│   └── src/{pages,chat,components,...}
├── sql/001_init_schema.sql      # PostgreSQL DDL (15 tables)
├── eval/                        # golden_questions.yaml + runner.py
├── docker-compose.yml           # db + backend + frontend
└── others/                      # planning / design docs (Chinese, personal)
```

---

## Quick start (Docker)

```bash
# 1) Put a .env in the repo root (or export the vars), at minimum:
#    OPENAI_API_KEY=sk-...
# 2) Bring up postgres + backend + frontend:
docker compose up -d --build

# 3) On first start, seed the dictionaries and the RAG knowledge base:
docker compose exec backend python scripts/seed_commodities.py
docker compose exec backend python scripts/seed_rag.py
```

- Frontend: **http://localhost:5173** (nginx is configured for SSE no-buffering, so streaming works)
- API docs: **http://localhost:8000/docs**
- The schema SQL runs automatically on the Postgres container's first start. ChromaDB persists in the
  `chroma_data` volume; PostgreSQL in `pg_data`.

---

## Quick start (local dev)

### 1. PostgreSQL

```bash
psql -U <user> -c "CREATE DATABASE ecotea;"
psql -U <user> -d ecotea -f sql/001_init_schema.sql
```

### 2. Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-ml.txt     # ml = local embeddings (torch)
cp .env.example .env                                        # then edit DATABASE_URL + OPENAI_API_KEY
python scripts/seed_commodities.py /path/to/your_source_workbook.xlsx   # ingest commodity metadata
python scripts/seed_rag.py                                  # seed the RAG vector store
uvicorn app.main:app --reload --port 8000                   # MUST run from backend/
```

Minimal `.env`:

```env
DATABASE_URL=postgresql+psycopg://<user>:<pwd>@localhost:5432/ecotea
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_PROVIDER=huggingface
ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

### 3. Frontend

```bash
cd frontend
npm install
npm run dev      # MUST run from frontend/ so the SSE proxy in vite.config.ts applies
```

---

## How the agent pipeline works

The **Planner** classifies each message into one of three intents and routes accordingly:

| Intent | Route | Example |
|--------|-------|---------|
| `data_query` | SQL Agent → Interpreter → Visualizer | "2030 capex by sector" |
| `tool_query` | **Tool Agent** (function-calling) → Interpreter | "What is BIOMASS01?", "1 PJ NG in ktoe" |
| `chat` | Interpreter (direct) | greetings / "what can you do" |

- **SQL Agent** uses `llm.with_structured_output(QueryParams)` — the model fills a typed object, never
  raw SQL. On execution failure it retries via the Planner (bounded by `AGENT_MAX_RETRIES`); after the
  limit it explains the failure honestly (no "0 rows" masquerade).
- **Tool Agent** binds the 4 auxiliary tools and lets the model choose and call them; results are
  composed into the final streamed answer by the Interpreter, grounded only in the tool output.
- **Interpreter** streams tokens (typewriter). A **reply-language** preference (Auto / English / 中文 /
  Español / Français / Deutsch / 日本語) is injected into its prompt.
- **Visualizer** turns the result into an ECharts `option` (line / bar / stacked / grouped), keeping
  `raw_row_id` as a hidden dimension for click-to-trace. Single-value / non-tabular answers skip the chart.

---

## The six function-calling tools

Each tool = a Pydantic input schema + a pure implementation + a LangChain `@tool` wrapper.

| # | Tool | Used via | Purpose |
|---|------|----------|---------|
| 1 | `lookup_terminology` | Tool Agent | Resolve a commodity/sector/tech code or term (exact dict + RAG fallback) |
| 2 | `convert_unit` | Tool Agent | Exact energy (PJ/ktoe/GWh/...) and CO₂ (kt/Mt/...) conversion |
| 3 | `run_sql` | **SQL Agent** | Pydantic-parameterized, injection-safe query; results carry `raw_row_id` |
| 4 | `lookup_emission_factor` | Tool Agent | A technology's emission factor for a year (nearest-year fallback) |
| 5 | `forecast_trend` | Tool Agent | numpy linear / quadratic extrapolation of a series |
| 6 | `recommend_chart` | **Visualizer** | Rule engine → ECharts skeleton |

**Whitelisted metrics** for `run_sql`: `capex`, `fixed_opex`, `variable_opex`, `emission_factor`,
`tax_cost`, `subsidy_cost`, `efficiency_value`, `technology_efficiency`, `heat_rate`,
`capacity_to_activity_factor`, `capacity`, `commodity_demand_value`.

---

## Schema-Mapping (column alignment)

The importer hard-codes column positions (capex = R, ef = O, …). When a workbook's header layout
drifts (a model version renames / reorders / inserts columns), import would silently misalign. The
**Schema-Mapping Agent** sits in front of the importer:

1. **Fast path** — headers match the canonical template → no agent call, import by fixed positions
   (the everyday, zero-cost case).
2. **Slow path** — headers differ → the agent maps each column to one of the 38 standard fields with a
   confidence (deterministic backend by default; LLM backend optional):
   - `≥ 0.9` auto-applied · `0.6–0.9` sent to the frontend **column-alignment review** · `< 0.6` skipped.
3. **Quality gate** — if core columns (`technology_code` / `data_year`) can't be aligned or coverage is
   too low, the import is **rejected (HTTP 422)** with guidance to review via `preview`.
4. Confirmed mappings are passed back as `column_overrides`; values are relocated to canonical
   positions while `raw_cells` keeps the **original** layout for accurate source-cell traceback.

A separate **sector-conflict review** handles rows whose column-A sector text disagrees with the sheet
name.

---

## RAG knowledge base

A persistent ChromaDB collection holds the commodity / sector / geography dictionaries plus the
hand-written `backend/data/domain_knowledge.md` (unit conversions, terminology, process taxonomy).
Embeddings go through a registry (same pattern as the LLM layer):

| Provider | Model | Notes |
|----------|-------|-------|
| `huggingface` (default) | `all-MiniLM-L6-v2` (384-d) | local, zero cost, offline |
| `openai` | `text-embedding-3-small` (1536-d) | cloud |
| `qwen` | `text-embedding-v3` (1024-d) | DashScope |

Seed with `python scripts/seed_rag.py` (`--reset` after switching provider, since dimensions differ).
Verify recall with `python scripts/verify_rag.py`. Users can also upload extra `.md/.txt` knowledge via
`POST /api/rag/documents`.

---

## Data model

A long-table PostgreSQL schema (15 tables) in an **anchor / satellite** style:

- **Anchor** `technology_year` = `(technology_id, data_year)`; re-importing the same `(tech, year)` is
  idempotent (satellites are cleared and rewritten).
- **Satellites** hang off it: `ecotea_parameter` (capex/opex/ef/…), `wp_descriptor` (efficiency/heat
  rate/…), `commodity` (flow shares + demand), `constraint` + `constraint_detail`.
- **Dictionaries**: `sector` (10), `geography`, `commodity`.
- **Provenance**: `import_batch`, `raw_excel_row` (full original cells as JSONB), `traceability_record`,
  `data_quality_issue`.

The 10 sectors: Power, Industry, Primary, Transport, Water, Waste, Building, Household, Agri, InfoComm.

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check (`?check_llm=true` actually pings the LLM) |
| `GET` | `/api/llm/providers` | The 6 LLM providers + config status |
| `POST` | `/api/chat/stream` | AI conversation (SSE); body `{message, history, language?}` |
| `GET` | `/api/raw-rows/{id}` | Source Excel row for a chart point |
| `POST` | `/api/rag/search` | Semantic search over the knowledge base |
| `GET` | `/api/rag/info` | Vector-store size + embedding provider |
| `POST`·`GET`·`DELETE` | `/api/rag/documents[/{file}]` | Upload / list / delete knowledge docs |
| `GET` | `/api/convert/models` | Available VT converters |
| `POST` | `/api/convert` | VT file → EcoTEA workbook (returns a token) |
| `GET` | `/api/convert/download/{token}` | Download a converted workbook |
| `POST` | `/api/imports/preview` | Sheet list + M5 column-alignment suggestions |
| `POST` | `/api/imports` | Upload + import (`column_overrides`, `auto_map_columns`, `use_llm_mapping`) |
| `POST` | `/api/imports/preview/from-conversion` · `/from-conversion` | Preview / import a converted workbook by token |
| `GET`·`POST` | `/api/imports/conflicts[/resolve]` | List / resolve sector conflicts |
| `GET` | `/api/sectors` · `/api/geographies` · `/api/technologies` · `/api/technologies/{id}` | Browse data |

Interactive docs at **`/docs`**.

---

## Configuration

All settings come from environment variables (`.env`, see `backend/.env.example`):

| Var | Default | Notes |
|-----|---------|-------|
| `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@localhost:5432/ecotea` | psycopg v3 |
| `ALLOWED_ORIGINS` | `http://localhost:5173,...` | CORS (credentials auto-disabled if set to `*`) |
| `LLM_PROVIDER` / `LLM_MODEL` | `openai` / provider default | hot-swappable |
| `*_API_KEY` | — | one per provider, fill what you use |
| `EMBEDDING_PROVIDER` / `EMBEDDING_MODEL` | `huggingface` / default | |
| `CHROMA_PERSIST_DIR` | `./chroma_data` | vector store path |
| `AGENT_MAX_RETRIES` / `AGENT_NODE_TIMEOUT` | `2` / `30` | SQL retry + node timeout |

---

## LLM / embedding provider switching

Six chat providers via a registry + factory — everything except Anthropic goes through the same
`ChatOpenAI` class with a custom `base_url`, so adding a provider is one registry row:

| Provider | base_url | Default model |
|----------|----------|---------------|
| `openai` (default) | (official) | gpt-4o-mini |
| `deepseek` | api.deepseek.com/v1 | deepseek-chat |
| `qwen` | dashscope…/compatible-mode/v1 | qwen-plus |
| `moonshot` | api.moonshot.cn/v1 | moonshot-v1-8k |
| `zhipu` | open.bigmodel.cn/api/paas/v4/ | glm-4-plus |
| `anthropic` | (official SDK) | claude-3-5-haiku-latest |

Switch by editing two `.env` lines (`LLM_PROVIDER=deepseek`, `DEEPSEEK_API_KEY=...`) and restarting.

---

## Evaluation

```bash
python eval/runner.py                      # golden questions, scored per question
python eval/runner.py --json report.json   # machine-readable report
```

Scored on three axes — keyword hits / tool calls / chart type. Below the pass threshold (default 80%)
the exit code is non-zero, so it can run as a non-blocking CI job.

---

## Testing

```bash
# Backend (from backend/)
python -m pytest                       # unit + integration (SQLite in-memory fixtures)
python scripts/verify_schema_mapping.py    # M5 acceptance (deterministic, no API key)
python scripts/verify_rag.py               # RAG recall@k

# Frontend (from frontend/)
npm test            # vitest
npm run build       # tsc + production build
```

Requires Python 3.11+ (the code uses `datetime.UTC`).

---

## CI / CD

- `.github/workflows/ci.yml` — backend `ruff check` + `ruff format --check` + `pytest` (coverage,
  against a PostgreSQL 17 service); frontend eslint + `tsc` + vitest + build.
- `.github/workflows/build-images.yml` — build & push backend / frontend images to GHCR (+ Trivy scan).
- Backend image is multi-stage; CPU-only torch by default.

---

## Troubleshooting

- **AI replies "the data step failed: Plan is empty"** → the running backend predates the Tool-Agent
  routing. Fully restart it (`pkill -f uvicorn` then start again, or rebuild the Docker image) so the
  current `graph.py` loads.
- **`role "postgres" does not exist`** → set `DATABASE_URL` to your actual local PG user.
- **AI produces nothing** → check `OPENAI_API_KEY`; run `npm run dev` from `frontend/`; the chat shows
  an "LLM not configured" banner when no key is set.
- **Import returns 422 "column alignment rejected"** → headers differ too much from the template.
  Call `POST /api/imports/preview` to inspect suggestions, then re-import with `column_overrides`.
- **`Failed to fetch`** → is the backend on :8000 and started from `backend/` (so `.env` loads)?

---

## Design docs

- `others/PlanReadme.md` — the full M0–M6 reengineering roadmap (technical decisions + details).
- `backend/README.md` — backend-focused setup, LLM/RAG/tools deep dive, SQL inspection queries.
- `eval/golden_questions.yaml` — the evaluation set.
- `CI_CD_SETUP.md` — pipeline notes.
