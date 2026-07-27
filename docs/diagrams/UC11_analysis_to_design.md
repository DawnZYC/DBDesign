# UC11 "Ask a question in natural language" — OOAD walkthrough

Critical use case chosen because it exercises the whole system: streaming API, multi-agent
orchestration, injection-safe data access, chart generation and cell-level provenance.

| # | Diagram | Question it answers |
|---|---|---|
| 1 | `1_analysis_class_diagram.svg` | **What** business objects exist (domain model) |
| 2 | `2_analysis_sequence_diagram.svg` | **What** the business process is |
| 3 | `3_design_class_diagram.svg` | **How** it is built (view / controller / service / repository / interface) |
| 4 | `4_design_sequence_diagram.svg` | **How** the software actually calls itself |

---

## 1 + 2 — the analysis model

The analysis model uses only the analyst's vocabulary. There is no Controller, Service,
Repository, HTTP, LLM or database in it, on purpose.

- **Domain model**: `Conversation`, `Question`, `Intent`, `AnalysisPlan`, `QuerySpecification`,
  `Metric`, `AnswerSet`, `DataPoint`, `SourceCell`, `Technology`, `TechnologyYear`, `Sector`,
  `Geography`, `Insight`, `Chart`, `KnowledgeDocument` — attributes and associations only, no
  operations.
- **Key invariant**: `DataPoint 1 —— 1 SourceCell`. Every figure the platform shows can be traced
  back to the exact workbook cell. This single association is what later forces `raw_row_id`
  through the query result, the chart dataset and the trace endpoint.
- **Business process**: the analyst asks; the platform understands the question, retrieves data
  *or* consults domain knowledge, explains, optionally charts, and on request reveals provenance.
  `:Strata` is still one black box, and the four workers are *business capabilities*, not classes.

---

## 3 + 4 — transition from analysis to design

Every design element traces back to an analysis element. Nothing was invented.

### Domain objects → software types

| Analysis (domain model) | Design (software) | File |
|---|---|---|
| `Question`, `Conversation` | `ChatRequest.message` / `.history`, `AgentState.messages` | `app/routers/chat.py`, `app/agents/state.py` |
| `Intent` «enumeration» | `AgentState.intent` + `_parse_intent()` | `app/agents/planner.py` |
| `AnalysisPlan` | `AgentState.plan: list[str]` | `app/agents/state.py` |
| `QuerySpecification` | `QueryParams` (Pydantic DTO) | `app/tools/sql_runner.py` |
| `Metric` «enumeration» | `MetricName` Literal + `METRICS` registry | `app/tools/sql_runner.py` |
| `AnswerSet` | `QueryResult` (Pydantic DTO) | `app/tools/sql_runner.py` |
| `DataPoint` | one row in `QueryResult.rows`, carrying `raw_row_id` | `app/tools/sql_runner.py` |
| `SourceCell` | `RawRow` entity + `GET /api/raw-rows/{id}` | `app/models.py`, `app/routers/raw_rows.py` |
| `Technology`, `TechnologyYear`, `Sector`, `Geography` | SQLAlchemy ORM entities | `app/models.py` |
| `Insight` | `AgentState.interpretation` (streamed) | `app/agents/interpreter.py` |
| `Chart` | `AgentState.chart_spec` (ECharts option) | `app/agents/visualizer.py` |
| `KnowledgeDocument` | ChromaDB collection + `lookup_terminology` | `app/rag/`, `app/tools/terminology.py` |

### Business capabilities → layered software structure

| Analysis (capability) | Design (layer + class) |
|---|---|
| `:Strata` black box | **Controller** `chat.py::chat_stream` + **Application** `CompiledGraph` |
| `:QuestionUnderstanding` | **Service** `planner_node` |
| `:DataRetrieval` | **Service** `sql_agent_node` + **Repository** `run_sql` |
| `:InsightGeneration` | **Service** `interpreter_node` |
| `:Visualisation` | **Service** `visualizer_node` + **Policy** `recommend_chart` |
| `:DomainKnowledge` | **Service** `tool_agent_node` + `AUX_TOOLS` registry |
| `:TechnologyDataset` | **Repository** `run_sql` over **Entity** `models.*` / `SessionLocal` |
| (implicit: the analyst's screen) | **View** `ChatPage` / `ChartBubble`, **View-model** `useStreamChat`, **Gateway** `streamChat()` |

### Five decisions that only exist in the design model

1. **Sixteen domain classes collapsed into one `AgentState`.**
   Analysis treats each artefact as its own object. LangGraph needs a single state object flowing
   between nodes, so `AnalysisPlan`, `QuerySpecification`, `AnswerSet`, `Insight` and `Chart`
   became *fields* of one TypedDict — a Blackboard. The domain boundaries survive as field groups.

2. **The black box split into controller + orchestrator.**
   Analysis gave `:Strata` the whole use case. Design separates *transport* (`chat.py` turns graph
   events into SSE) from *control flow* (`graph.py` decides which node runs next), so the pipeline
   is testable with no HTTP involved.

3. **"Express the plan as a QuerySpecification" became a typed structured output.**
   Design forbids the model from producing SQL at all: `llm.with_structured_output(QueryParams)`
   lets the LLM fill only whitelisted fields, which `_build_query()` compiles into a parameterised
   `select()`. The injection-safety property is a *design* decision, invisible in analysis.

4. **Request/response became streaming.**
   Analysis shows `explain(AnswerSet)` returning an `Insight`. Design turns it into
   `llm.astream()` → `on_chat_model_stream` → SSE `token` → `onToken` callback so the answer forms
   in front of the user. Same responsibility, different interaction style.

5. **`DataPoint 1—1 SourceCell` became a hidden chart dimension.**
   The invariant is realised by keeping `raw_row_id` in every raw query row, carrying it into the
   ECharts `dataset.dimensions`, and exposing `GET /api/raw-rows/{id}`. The association drove three
   separate design choices across three layers.

---

## Use of design patterns

| Pattern | Where it lives | What it buys |
|---|---|---|
| **Layered architecture** | view → controller → application → domain service → repository → infrastructure | Each layer only knows the one below; the agent pipeline can be exercised without a browser, and the repository without an LLM. |
| **MVVM (MVC family)** | `ChatPage` (view), `useStreamChat` (view-model, owns `ChatMessage[]`), `streamChat()` (gateway) | Rendering stays free of transport concerns; the SSE protocol can change without touching a component. |
| **Repository** | `run_sql` over `models.*` / `SessionLocal` | The only door into the technology tables. Callers pass a `QueryParams`; no caller ever holds a `Session` or writes SQL. |
| **Abstract Factory + Registry** | `get_chat_model()` over `PROVIDER_REGISTRY`; same shape in `rag/embeddings.py` | Adding a seventh LLM provider is one dict entry plus one settings field — zero call-site changes. |
| **Strategy** | `BaseChatModel` with `ChatOpenAI` / `ChatAnthropic`; `NodeFn` with five node services | Providers and pipeline steps vary independently of the code that orchestrates them. |
| **Blackboard** | `AgentState` | Four specialist services contribute partial results to one shared workspace instead of threading tuples through fixed signatures. |
| **State machine + Chain of Responsibility** | `route_after_planner` / `route_after_sql` / `route_after_interpreter` | Intent branching, bounded retry and skip-chart-if-under-2-rows live in one place as pure functions — unit-testable with no LLM. |
| **Command + Parameter Object** | `QueryParams` | The command is data: validatable, loggable, replayable, and structurally incapable of expressing SQL injection. |
| **Observer / Publish-Subscribe** | `astream_events` → SSE → frontend callbacks | One event stream, three subscriber layers. The tool-call trace UI needed no backend change beyond emitting one more event type. |
| **Decorator** | `@tool` (schema binding) and `@with_observability` (timing + structured logs) | Cross-cutting concerns stay out of tool bodies; every tool gets identical instrumentation. |
| **Singleton** | `get_graph()`, `get_settings()` (`lru_cache`) | The compiled graph is expensive to build and stateless to reuse. |
| **Facade** | `POST /api/chat/stream` | One endpoint hides planner, SQL agent, tool agent, interpreter and visualizer from every client. |
| **Builder** | `_build_query()` → `Select`, `_build_echarts_spec()` → ECharts option | Both assemble a complex object from many optional parts; construction is separated from the parts. |

### How the patterns raise maintainability, extensibility and decoupling

- **Extensibility** — adding an LLM provider (Registry), a function-calling tool (`AUX_TOOLS`
  Command registry), or a chart type (`recommend_chart` policy) is a local, additive change.
- **Decoupling** — the Repository means no layer above `run_sql` knows SQLAlchemy exists; the
  Strategy interface means no layer knows which vendor is answering; the Observer means the
  frontend does not know LangGraph exists.
- **Maintainability** — routing rules, prompt logic, query compilation and rendering are in four
  separate files with four separate test suites (backend 427 tests / 88% coverage).

### Pattern interactions worth calling out

- **Strategy + Registry + Factory** are one mechanism, not three: the registry holds the catalogue,
  the factory resolves it, and everything above only sees `BaseChatModel`.
- **Command + State machine** give the retry loop its safety: because `QueryParams` is a validated
  value with no side effects, a failed attempt is simply discarded and the planner re-runs with
  `retry_count + 1`.
- **Blackboard + Observer** is what makes the live trace UI possible: services write to
  `AgentState`, LangGraph publishes each write, and the frontend renders the reasoning as it
  happens rather than after the fact.
