"""Agent orchestration package.

Contains two decoupled kinds of Agent:
  * Query side (M3): Planner -> SQL -> Interpreter -> Visualizer, orchestrated by
    LangGraph. Exposed via build_graph() / AgentState.
  * Ingestion side (M5): schema_mapper — aligns column layout at import time, and is
    NOT part of the M3 graph.

So the ingestion side (which only depends on openpyxl/pydantic) can be imported
independently in environments without langgraph, the M3 entry points use PEP 562 lazy
loading: langgraph-related modules are imported only when build_graph/AgentState is
actually accessed. `from app.agents import schema_mapper` does not pull in those heavy
dependencies.
"""

from __future__ import annotations

from typing import Any

__all__ = ["AgentState", "build_graph", "schema_mapper"]


def __getattr__(name: str) -> Any:  # PEP 562
    if name == "build_graph":
        from app.agents.graph import build_graph

        return build_graph
    if name == "AgentState":
        from app.agents.state import AgentState

        return AgentState
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
