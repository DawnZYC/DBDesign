"""LangGraph ReAct Agent for energy data analysis.

Architecture
-----------
* LLM   : Qwen (via DashScope OpenAI-compatible endpoint)
* Tools : 4 tools that query PostgreSQL / ChromaDB
* Graph : LangGraph StateGraph with tool_node + conditional routing
* Output: async generator of SSE-friendly dicts
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Sequence

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from app.config import get_settings
from app.database import SessionLocal
from app.services.chroma_service import semantic_search

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@tool
def query_technologies(
    keyword: str = "",
    sector_id: int | None = None,
    geography_id: int | None = None,
    limit: int = 20,
) -> str:
    """Search technology_process records in PostgreSQL.

    Args:
        keyword: Free-text search against technology_code or technology_description.
        sector_id: Filter by sector ID (optional).
        geography_id: Filter by geography ID (optional).
        limit: Maximum rows to return (default 20).

    Returns:
        JSON-serialised list of matching technologies.
    """
    from sqlalchemy import or_, text

    db = SessionLocal()
    try:
        query = "SELECT technology_id, technology_code, technology_description, sector_id, geography_id, technology_start_year, technology_lifetime_years, grade FROM technology_process WHERE 1=1"
        params: dict = {}

        if keyword:
            query += " AND (technology_code ILIKE :kw OR technology_description ILIKE :kw)"
            params["kw"] = f"%{keyword}%"
        if sector_id is not None:
            query += " AND sector_id = :sector_id"
            params["sector_id"] = sector_id
        if geography_id is not None:
            query += " AND geography_id = :geography_id"
            params["geography_id"] = geography_id

        query += f" LIMIT {min(limit, 50)}"

        rows = db.execute(text(query), params).mappings().all()
        result = [dict(r) for r in rows]
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.error("query_technologies error: %s", exc)
        return json.dumps({"error": str(exc)})
    finally:
        db.close()


@tool
def get_cost_data(
    technology_code: str = "",
    year_from: int | None = None,
    year_to: int | None = None,
    limit: int = 30,
) -> str:
    """Retrieve CAPEX, fixed OPEX, variable OPEX and emission factor for technologies.

    Args:
        technology_code: Technology code filter (partial match).
        year_from: Start of year range (inclusive).
        year_to: End of year range (inclusive).
        limit: Maximum rows to return.

    Returns:
        JSON list with year, capex, fixed_opex, variable_opex, emission_factor per row.
    """
    from sqlalchemy import text

    db = SessionLocal()
    try:
        query = """
            SELECT
                tp.technology_code,
                tp.technology_description,
                ty.data_year,
                p.capex,
                p.capex_unit,
                p.fixed_opex,
                p.fixed_opex_unit,
                p.variable_opex,
                p.variable_opex_unit,
                p.emission_factor,
                p.emission_factor_unit,
                p.base_currency
            FROM technology_process tp
            JOIN technology_year ty ON ty.technology_id = tp.technology_id
            JOIN technology_year_ecotea_parameter p ON p.technology_year_id = ty.technology_year_id
            WHERE 1=1
        """
        params: dict = {}

        if technology_code:
            query += " AND tp.technology_code ILIKE :code"
            params["code"] = f"%{technology_code}%"
        if year_from is not None:
            query += " AND ty.data_year >= :year_from"
            params["year_from"] = year_from
        if year_to is not None:
            query += " AND ty.data_year <= :year_to"
            params["year_to"] = year_to

        query += " ORDER BY tp.technology_code, ty.data_year"
        query += f" LIMIT {min(limit, 100)}"

        rows = db.execute(text(query), params).mappings().all()
        result = [dict(r) for r in rows]
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.error("get_cost_data error: %s", exc)
        return json.dumps({"error": str(exc)})
    finally:
        db.close()


@tool
def compare_years(technology_code: str, years: list[int]) -> str:
    """Compare cost and efficiency parameters of a technology across specific years.

    Args:
        technology_code: Exact or partial technology code.
        years: List of data years to compare (e.g. [2020, 2025, 2030]).

    Returns:
        JSON with a row per (technology, year) pair showing key cost metrics.
    """
    from sqlalchemy import text

    db = SessionLocal()
    try:
        if not years:
            return json.dumps({"error": "years list is empty"})

        placeholders = ", ".join(f":y{i}" for i in range(len(years)))
        params: dict = {"code": f"%{technology_code}%"}
        for i, yr in enumerate(years):
            params[f"y{i}"] = yr

        query = f"""
            SELECT
                tp.technology_code,
                tp.technology_description,
                ty.data_year,
                p.capex,
                p.capex_unit,
                p.fixed_opex,
                p.fixed_opex_unit,
                p.variable_opex,
                p.variable_opex_unit,
                p.emission_factor,
                p.emission_factor_unit,
                w.efficiency_value,
                w.efficiency_unit,
                w.heat_rate
            FROM technology_process tp
            JOIN technology_year ty ON ty.technology_id = tp.technology_id
            LEFT JOIN technology_year_ecotea_parameter p ON p.technology_year_id = ty.technology_year_id
            LEFT JOIN technology_year_wp_descriptor w ON w.technology_year_id = ty.technology_year_id
            WHERE tp.technology_code ILIKE :code
              AND ty.data_year IN ({placeholders})
            ORDER BY tp.technology_code, ty.data_year
        """

        rows = db.execute(text(query), params).mappings().all()
        result = [dict(r) for r in rows]
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.error("compare_years error: %s", exc)
        return json.dumps({"error": str(exc)})
    finally:
        db.close()


@tool
def search_similar_technologies(query: str, n_results: int = 5) -> str:
    """Semantic search for technologies similar to a natural-language description.

    Uses ChromaDB vector similarity.  Useful for finding technologies by concept
    rather than exact code, e.g. "offshore wind power plant".

    Args:
        query: Natural language description to search for.
        n_results: Number of results to return (default 5).

    Returns:
        JSON list of matching technologies with similarity distance.
    """
    results = semantic_search(query, n_results=n_results)
    return json.dumps(results, default=str)


# Chart colours (categorical palette)
_CHART_COLORS = [
    "#1e3a8a", "#0ea5e9", "#10b981", "#f59e0b",
    "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6",
]


@tool
def create_visualization(
    chart_type: str,
    title: str,
    data: list[dict],
    x_key: str,
    y_keys: list[str],
    y_labels: list[str] | None = None,
) -> str:
    """Render a chart from structured data.  Call this AFTER fetching data with
    get_cost_data or compare_years to produce an inline visualisation.

    Args:
        chart_type: One of "line", "bar", or "area".
        title: Human-readable chart title.
        data: List of data-point dicts (rows from a previous tool call).
        x_key: The dict key to use as the X-axis (e.g. "data_year").
        y_keys: List of dict keys to plot as separate series (e.g. ["capex", "fixed_opex"]).
        y_labels: Optional human-readable labels for each y_key series.

    Returns:
        JSON chart spec (forwarded to the frontend as a visualisation event).
    """
    # Coerce numeric strings to floats so recharts can render them
    cleaned: list[dict] = []
    for row in data:
        point: dict = {}
        for k, v in row.items():
            if k in y_keys:
                try:
                    point[k] = float(v) if v is not None else None
                except (TypeError, ValueError):
                    point[k] = None
            else:
                point[k] = v
        cleaned.append(point)

    labels = y_labels or y_keys
    series = [
        {"key": k, "label": l, "color": _CHART_COLORS[i % len(_CHART_COLORS)]}
        for i, (k, l) in enumerate(zip(y_keys, labels))
    ]

    spec = {
        "chartType": chart_type,
        "title": title,
        "xKey": x_key,
        "series": series,
        "data": cleaned,
    }
    return json.dumps(spec, default=str)


# ---------------------------------------------------------------------------
# LangGraph state & graph construction
# ---------------------------------------------------------------------------

TOOLS = [
    query_technologies,
    get_cost_data,
    compare_years,
    search_similar_technologies,
    create_visualization,
]

SYSTEM_PROMPT = """You are an expert energy data analyst assistant for the EcoTEA WP1 database.
You help researchers query and interpret technology cost and efficiency data.

Available tools:
- query_technologies: Search for technology processes in the database
- get_cost_data: Retrieve CAPEX, OPEX, emission factors for technologies
- compare_years: Compare a technology's parameters across multiple years
- search_similar_technologies: Semantic search using natural language
- create_visualization: Render an inline chart from structured data

Visualization guidelines:
- ALWAYS call create_visualization after get_cost_data or compare_years when the user asks
  about trends, comparisons, or time-series data.
- Use chart_type "line" for time-series trends, "bar" for category comparisons,
  "area" for cumulative or stacked data.
- x_key should be "data_year" for time-series; y_keys should be numeric fields
  (capex, fixed_opex, variable_opex, emission_factor, efficiency_value, heat_rate).
- Set y_labels to human-readable names (e.g. ["CAPEX", "Fixed OPEX"]).
- Pass only the rows you want to chart – filter or deduplicate first if needed.

Other guidelines:
- Always present numerical data clearly with units
- When comparing across years, highlight trends and significant changes
- If data is missing or sparse, mention it explicitly
- Format monetary values consistently (include currency and unit)
- For trend analysis, use year milestones e.g. [2020, 2025, 2030, 2035, 2040]

Respond in the same language as the user's question.
"""


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]


def _build_graph() -> object:
    cfg = get_settings()

    llm = ChatOpenAI(
        model=cfg.llm_model,
        openai_api_key=cfg.dashscope_api_key or "EMPTY",
        openai_api_base=cfg.llm_base_url,
        streaming=True,
        temperature=0.1,
    )

    llm_with_tools = llm.bind_tools(TOOLS)
    tool_node = ToolNode(TOOLS)

    def call_model(state: AgentState) -> AgentState:
        messages = state["messages"]
        # Prepend system message if not already present
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=SYSTEM_PROMPT)] + list(messages)
        response = llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def should_continue(state: AgentState) -> str:
        last = state["messages"][-1]
        if isinstance(last, AIMessage) and last.tool_calls:
            return "tools"
        return END

    graph = StateGraph(AgentState)
    graph.add_node("agent", call_model)
    graph.add_node("tools", tool_node)
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")

    return graph.compile()


# Lazily compiled graph
_compiled_graph: object | None = None


def get_graph() -> object:
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph()
    return _compiled_graph


# ---------------------------------------------------------------------------
# Streaming interface
# ---------------------------------------------------------------------------


async def run_agent_stream(
    user_message: str,
    history: list[dict] | None = None,
) -> AsyncGenerator[dict, None]:
    """Stream agent events as SSE-friendly dicts.

    Yields dicts with keys:
      - type: "token" | "tool_start" | "tool_end" | "error" | "done"
      - content: string payload
    """
    graph = get_graph()

    # Build message list from history
    messages: list[BaseMessage] = []
    for msg in (history or []):
        role = msg.get("role", "")
        content = msg.get("content", "")
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_message))

    try:
        async for event in graph.astream_events(
            {"messages": messages},
            version="v2",
            config={"recursion_limit": 50},
        ):
            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    yield {"type": "token", "content": chunk.content}

            elif kind == "on_tool_start":
                tool_input = event.get("data", {}).get("input", {})
                yield {
                    "type": "tool_start",
                    "content": json.dumps(
                        {"tool": name, "input": tool_input}, ensure_ascii=False
                    ),
                }

            elif kind == "on_tool_end":
                tool_output = event.get("data", {}).get("output", "")
                # on_tool_end returns a ToolMessage object; extract its .content string
                if hasattr(tool_output, "content"):
                    output_str = tool_output.content
                elif isinstance(tool_output, str):
                    output_str = tool_output
                else:
                    output_str = str(tool_output)

                # Emit a dedicated chart event for create_visualization
                if name == "create_visualization":
                    try:
                        chart_spec = json.loads(output_str)
                        yield {"type": "chart", "content": json.dumps(chart_spec, ensure_ascii=False)}
                    except Exception as e:
                        logger.warning("chart spec parse failed: %s | raw=%s", e, output_str[:200])

                yield {
                    "type": "tool_end",
                    "content": json.dumps(
                        {"tool": name, "output": output_str[:500]},
                        ensure_ascii=False,
                    ),
                }

        yield {"type": "done", "content": ""}

    except Exception as exc:
        logger.error("Agent stream error: %s", exc, exc_info=True)
        yield {"type": "error", "content": str(exc)}
