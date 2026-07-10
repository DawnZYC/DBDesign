"""LangGraph orchestration — the 4-agent state graph.

Graph structure:
  START -> planner -> sql_gen -> [conditional edge] -> interpreter -> visualizer -> END
                                      v (on failure, retries not exhausted)
                                    planner (retry)

Conditional edge logic (route_after_sql):
  - sql_result present and no error -> interpreter
  - error present and retry_count < max_retries -> planner (retry, retry_count + 1)
  - error present and limit reached -> interpreter (carries the error so it can tell the user)

Usage:
  from app.agents.graph import build_graph

  graph = build_graph()

  # Synchronous call (for simple tests)
  result = graph.invoke({"messages": [HumanMessage(content="...")], ...})

  # Async + event stream (used by the SSE endpoint)
  async for event in graph.astream_events(initial_state, version="v2"):
      ...
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from langgraph.graph import END, START, StateGraph

if TYPE_CHECKING:
    from langgraph.graph.graph import CompiledGraph

from app.agents.interpreter import interpreter_node
from app.agents.planner import planner_node
from app.agents.sql_agent import sql_agent_node
from app.agents.state import AgentState
from app.agents.tool_agent import tool_agent_node
from app.agents.visualizer import visualizer_node
from app.config import get_settings

logger = logging.getLogger(__name__)

# Node name constants (avoid magic strings scattered around)
NODE_PLANNER = "planner"
NODE_SQL = "sql_gen"
NODE_TOOL_AGENT = "tool_agent"
NODE_INTERPRETER = "interpreter"
NODE_VISUALIZER = "visualizer"


# -----------------------------------------------------------------------------
# Conditional edge: routing after the SQL node completes
# -----------------------------------------------------------------------------
def route_after_planner(state: AgentState) -> str:
    """Intent routing after the Planner.

    * data_query (default) -> SQL Agent, the full data pipeline
    * tool_query           -> Tool Agent (function-calling), then Interpreter
    * direct_answer        -> straight to the Interpreter for a conversational answer
                              (no tools, no DB query, no chart)
    """
    intent = state.get("intent")
    if intent == "direct_answer":
        logger.debug("route_after_planner -> interpreter (direct answer)")
        return NODE_INTERPRETER
    if intent == "tool_query":
        logger.debug("route_after_planner -> tool_agent (tool query)")
        return NODE_TOOL_AGENT
    return NODE_SQL


def route_after_interpreter(state: AgentState) -> str:
    """Decide whether to enter the Visualizer after the Interpreter.

    Skip charting when:
    * direct-answer / tool-query mode (no tabular data to plot)
    * no SQL result, or fewer than 2 rows (charting a single aggregate number is pointless)
    """
    if state.get("intent") in ("direct_answer", "tool_query"):
        logger.debug("route_after_interpreter -> END (%s)", state.get("intent"))
        return END
    sql_result = state.get("sql_result") or {}
    rows = sql_result.get("rows") or []
    if len(rows) < 2:
        logger.debug("route_after_interpreter -> END (%d rows, chart skipped)", len(rows))
        return END
    return NODE_VISUALIZER


def route_after_sql(state: AgentState) -> str:
    """Decide where to go after the sql_gen node finishes.

    The return value must be a key in the path_map of graph.add_conditional_edges.
    """
    settings = get_settings()
    has_error = bool(state.get("error"))
    retry_count = state.get("retry_count", 0)

    if not has_error:
        # Success: take the normal path
        logger.debug("route_after_sql -> interpreter (ok)")
        return NODE_INTERPRETER

    if retry_count < settings.agent_max_retries:
        # Error but retries remain: go back to the Planner
        logger.info(
            "route_after_sql -> planner (retry %d/%d, error=%s)",
            retry_count + 1,
            settings.agent_max_retries,
            state.get("error", "")[:80],
        )
        return NODE_PLANNER

    # Retry limit reached: force interpreter (so it can tell the user it failed)
    logger.warning(
        "route_after_sql -> interpreter (max retries exhausted, error=%s)",
        state.get("error", "")[:80],
    )
    return NODE_INTERPRETER


# -----------------------------------------------------------------------------
# Retry-count wrapper
# -----------------------------------------------------------------------------
def _sql_gen_with_retry_increment(state: AgentState) -> dict:
    """Wrap sql_agent_node with a retry counter: increment retry_count on failure.

    LangGraph cannot mutate state inside a conditional edge, so we handle it at the
    node exit.
    """
    result = sql_agent_node(state)
    if result.get("error"):
        result["retry_count"] = state.get("retry_count", 0) + 1
    return result


# -----------------------------------------------------------------------------
# Graph construction
# -----------------------------------------------------------------------------
def build_graph() -> CompiledGraph:
    """Build and compile the LangGraph state graph.

    Builds fresh on every call (no caching); the caller is responsible for reusing the
    compiled graph. build_graph() itself is cheap (no I/O), so the router layer uses a
    module-level singleton.
    """
    graph = StateGraph(AgentState)

    # ---- Register nodes ----
    graph.add_node(NODE_PLANNER, planner_node)
    graph.add_node(NODE_SQL, _sql_gen_with_retry_increment)
    graph.add_node(NODE_TOOL_AGENT, tool_agent_node)
    graph.add_node(NODE_INTERPRETER, interpreter_node)
    graph.add_node(NODE_VISUALIZER, visualizer_node)

    # ---- Fixed edges ----
    graph.add_edge(START, NODE_PLANNER)
    graph.add_edge(
        NODE_TOOL_AGENT, NODE_INTERPRETER
    )  # tool results -> Interpreter composes the answer
    graph.add_edge(NODE_VISUALIZER, END)

    # ---- Conditional edge: route by intent after the planner ----
    #   data_query -> SQL pipeline; tool_query -> Tool Agent; chat -> Interpreter
    graph.add_conditional_edges(
        NODE_PLANNER,
        route_after_planner,
        {
            NODE_SQL: NODE_SQL,
            NODE_TOOL_AGENT: NODE_TOOL_AGENT,
            NODE_INTERPRETER: NODE_INTERPRETER,
        },
    )

    # ---- Conditional edge: decide whether to chart after the interpreter ----
    graph.add_conditional_edges(
        NODE_INTERPRETER,
        route_after_interpreter,
        {
            NODE_VISUALIZER: NODE_VISUALIZER,
            END: END,
        },
    )

    # ---- Conditional edge: routing after sql_gen ----
    graph.add_conditional_edges(
        NODE_SQL,
        route_after_sql,
        {
            NODE_INTERPRETER: NODE_INTERPRETER,
            NODE_PLANNER: NODE_PLANNER,
        },
    )

    compiled = graph.compile()
    logger.info("LangGraph compiled: nodes=%s", list(graph.nodes))
    return compiled


# -----------------------------------------------------------------------------
# Module-level singleton (reused by the router layer to avoid recompiling)
# -----------------------------------------------------------------------------
# Lazy init: not executed on first import (avoids errors when the test env has no DB)
_graph_instance = None


def get_graph():
    """Get (or lazily initialize) the module-level graph singleton."""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance
