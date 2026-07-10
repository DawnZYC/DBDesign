"""Interpreter node — translate SQL query results into natural-language analysis.

Responsibilities:
  1. Read AgentState.sql_result (the serialized QueryResult dict).
  2. Use llm.astream to stream the analysis text, pushing it token by token to SSE.
  3. Write the full text into AgentState.interpretation.

Streaming strategy:
  * The Interpreter is the only node in the pipeline that streams at the token level.
  * The other nodes (Planner / SQL / Visualizer) use invoke (wait for full output).
  * The router (chat.py) listens to graph stream_mode="values" + stream_events and
    converts on_chat_model_stream events into SSE token events for the frontend.

Data trimming:
  * SQL results can have hundreds of rows; sending them all would exceed the context window.
  * Only the first MAX_ROWS_FOR_LLM rows + a stats summary are sent, to avoid excess token usage.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.llm.provider import get_chat_model

logger = logging.getLogger(__name__)

MAX_ROWS_FOR_LLM = (
    30  # Send at most this many rows to the LLM; the rest is replaced by a stats summary
)


def _language_directive(state: AgentState) -> str:
    """Return a system-prompt suffix forcing the reply language, or '' for auto (match the question)."""
    lang = (state.get("language") or "").strip()
    if not lang:
        return ""
    return (
        f"\n\nIMPORTANT: Write your entire reply in {lang}, regardless of the language of the "
        "question or the data. Keep codes, units, and identifiers (e.g. commodity codes, capex, PJ) as-is."
    )


# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """You are the data interpretation expert of the EcoTEA platform.
Interpret SQL query results clearly and professionally, in English, with
useful insights.

Requirements:
1. Open with one sentence summarizing the topic and the headline finding
2. Call out key patterns (max/min, growth/decline, inflection points)
3. If the data is truncated (truncated=True), say so explicitly
4. Use Markdown; bold the key numbers
5. Keep it to roughly 120-250 words
6. Do not repeat raw rows -- analyze the patterns
"""


def _summarize_result(sql_result: dict[str, Any]) -> str:
    """Compress the SQL result into a text summary the LLM can digest."""
    rows: list[dict] = sql_result.get("rows", [])
    row_count = sql_result.get("row_count", len(rows))
    metric = sql_result.get("metric", "unknown")
    aggregation = sql_result.get("aggregation", "raw")
    metric_unit = sql_result.get("metric_unit", "")
    sql_summary = sql_result.get("sql_summary", "")
    truncated = sql_result.get("truncated", False)

    # Only the first MAX_ROWS_FOR_LLM rows are sent to the LLM
    sample = rows[:MAX_ROWS_FOR_LLM]
    sample_json = json.dumps(sample, ensure_ascii=False, indent=2, default=str)

    lines = [
        f"Query summary: {sql_summary}",
        f"Metric: {metric} (unit: {metric_unit or 'unknown'}) | aggregation: {aggregation}",
        f"Total rows: {row_count}{' (truncated at limit)' if truncated else ''}",
        "",
        f"Data sample (first {len(sample)} rows):",
        sample_json,
    ]
    if row_count > MAX_ROWS_FOR_LLM:
        lines.append(f"\n[Note: {row_count} rows total; only the first {MAX_ROWS_FOR_LLM} shown]")

    return "\n".join(lines)


# -----------------------------------------------------------------------------
# Node function (async, supports token streaming)
# -----------------------------------------------------------------------------
async def interpreter_node(state: AgentState) -> dict:
    """LangGraph node: Interpreter (async version).

    Uses llm.astream to stream output; LangGraph astream_events(version="v2") captures
    the on_chat_model_stream events, which the router layer converts into SSE tokens for
    the frontend (typewriter effect).

    For synchronous calls (tests / graph.invoke), LangGraph awaits it automatically in the event loop.
    """
    logger.info("interpreter_node: start (intent=%s)", state.get("intent"))

    # Direct-answer mode (Planner classified it as small talk / concept question): does not
    # depend on SQL results, answers via a chat prompt with streaming. Tokens are emitted
    # exactly the same way as in data-interpretation mode.
    if state.get("intent") == "direct_answer":
        return await _direct_answer(state)

    # Tool-query mode: compose the final streamed answer grounded ONLY in the function-calling
    # tool results the Tool Agent collected (terminology / unit / emission / forecast).
    if state.get("intent") == "tool_query":
        return await _interpret_tool_results(state)

    sql_result = state.get("sql_result")
    if not sql_result:
        # Distinguish a real failure (the SQL step errored, even after retries) from a
        # valid query that simply matched 0 rows — otherwise failures masquerade as "no data".
        err = state.get("error")
        if err:
            return {
                "interpretation": (
                    f"I couldn't run that query — the data step failed: {err}. "
                    "Try rephrasing, narrowing the sector/years, or asking a simpler question."
                ),
                "error": err,
            }
        return {
            "interpretation": (
                "The query ran but matched no rows. Try widening the filters "
                "(e.g. a broader year range or a different sector/technology)."
            ),
            "error": None,
        }

    result_summary = _summarize_result(sql_result)
    llm = get_chat_model()

    messages = [
        SystemMessage(content=_SYSTEM + _language_directive(state)),
        HumanMessage(content=f"Interpret the following query result:\n\n{result_summary}"),
    ]

    try:
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            content = chunk.content
            if isinstance(content, str):
                chunks.append(content)
        text = "".join(chunks)
        logger.info("interpreter_node: generated %d chars", len(text))
        return {"interpretation": text, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("interpreter_node: LLM call failed")
        return {
            "interpretation": f"Failed to generate the interpretation: {exc!s}",
            "error": f"Interpreter failed: {exc!s}",
        }


_TOOL_INTERP_SYSTEM = """You are the answer composer of the EcoTEA platform.
Answer the user's question using ONLY the tool results provided below.

Requirements:
1. Ground every claim in the tool output -- quote the concrete value/definition it returned
   (code meaning, conversion factor, emission value, forecast points).
2. If a tool returned not_found or an error, say so plainly; do NOT guess or invent data.
3. English, Markdown, concise. Bold the key number / answer.
"""


async def _interpret_tool_results(state: AgentState) -> dict:
    """Compose the final streamed answer from the Tool Agent's function-calling results."""
    tool_context = state.get("tool_context")
    if not tool_context:
        # Tool agent failed before producing anything.
        err = state.get("error") or "no tool result"
        return {
            "interpretation": f"Could not complete the request via the tools: {err}",
            "error": state.get("error"),
        }

    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    question = str(user_messages[-1].content) if user_messages else "(unknown)"

    llm = get_chat_model()
    messages = [
        SystemMessage(content=_TOOL_INTERP_SYSTEM + _language_directive(state)),
        HumanMessage(content=f"User question: {question}\n\n{tool_context}"),
    ]
    try:
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            content = chunk.content
            if isinstance(content, str):
                chunks.append(content)
        text = "".join(chunks)
        logger.info("interpreter_node(tool): generated %d chars", len(text))
        return {"interpretation": text, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("interpreter_node(tool): LLM call failed")
        return {
            "interpretation": f"Failed to compose the answer: {exc!s}",
            "error": f"Interpreter failed: {exc!s}",
        }


_DIRECT_SYSTEM = """You are the AI assistant of the EcoTEA energy data
analysis platform. Be friendly and concise.

What you can do (mention when asked):
- Query energy-system model data in natural language: capex, O&M
  costs, emission factors, capacity and more, across 10 sectors (Power,
  Industry, Transport, ...) and years, with comparisons and trend charts
- Explain terminology (e.g. commodity codes), convert units
  (PJ/ktoe/GWh), and forecast trends -- these run through dedicated tools

Style: answer in English and keep it short (1-3 sentences for small talk).
If the question actually needs data, invite the user to ask a concrete data
question and give one example. Never fabricate database values."""


async def _direct_answer(state: AgentState) -> dict:
    """Conversational direct answer (no DB query). Reuses astream so the frontend gets streamed tokens.

    Passes the last few Human/AI messages to the LLM as-is — the natural form of multi-turn
    conversation — so the "assistant asks -> user follows up" handoff doesn't lose context.
    """
    from app.agents.context import recent_messages

    history = recent_messages(state["messages"], limit=8)
    if not history:
        history = [HumanMessage(content="Hello")]

    llm = get_chat_model()
    messages = [SystemMessage(content=_DIRECT_SYSTEM + _language_directive(state)), *history]
    try:
        chunks: list[str] = []
        async for chunk in llm.astream(messages):
            content = chunk.content
            if isinstance(content, str):
                chunks.append(content)
        text = "".join(chunks)
        logger.info("interpreter_node(direct): generated %d chars", len(text))
        return {"interpretation": text, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("interpreter_node(direct): LLM call failed")
        return {
            "interpretation": f"Failed to generate the answer: {exc!s}",
            "error": f"Interpreter failed: {exc!s}",
        }
