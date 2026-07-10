"""AgentState — shared state structure passed between LangGraph nodes.

Design principles:
  * Only store data that needs to cross node boundaries.
  * messages use the LangChain add_messages reducer (append-only).
  * Other fields use last-write-wins (LangGraph default).
  * All optional fields default to None; nodes fill them in and pass them forward.
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Global state for the 4-agent pipeline.

    Field flow:
        messages       — conversation history (user + assistant), accumulated via add_messages
        plan           — step list produced by the Planner (natural language / Markdown bullets)
        sql_params     — structured query params from the SQL Agent (serialized QueryParams dict)
        sql_result     — result of the run_sql tool (QueryResult.model_dump())
        interpretation — natural-language analysis text from the Interpreter
        chart_spec     — ECharts spec from the Visualizer (full option dict)
        retry_count    — current retry count (SQL failure -> back to Planner)
        error          — latest error description; cleared to None once a node finishes normally
    """

    # Conversation history: uses the add_messages reducer, so each update appends instead of overwriting.
    messages: Annotated[list[BaseMessage], add_messages]

    # Planner output
    plan: list[str]
    # Intent: "data_query" (needs a DB query, full SQL pipeline) / "tool_query" (terminology /
    # unit conversion / emission factor / forecast, handled by the function-calling tool agent) /
    # "direct_answer" (small talk, answered directly by the Interpreter without tools).
    # None is treated as data_query.
    intent: str | None

    # SQL Agent output
    sql_params: dict[str, Any] | None  # app.tools.sql_runner.QueryParams.model_dump()

    # run_sql tool output
    sql_result: dict[str, Any] | None  # QueryResult.model_dump()

    # Tool Agent output: a human-readable transcript of the function-calling tools the LLM
    # chose to run (name, args, result), consumed by the Interpreter for the final answer.
    tool_context: str | None

    # Interpreter output
    interpretation: str | None

    # Visualizer output
    chart_spec: dict[str, Any] | None  # EChartsSpec.model_dump()

    # User preference: the language the assistant should reply in (e.g. "English",
    # "Chinese"). Empty / None means "match the language of the question" (auto).
    language: str | None

    # Flow control
    retry_count: int
    error: str | None
