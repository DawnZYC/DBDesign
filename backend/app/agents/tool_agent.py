"""Tool Agent node (M3+) — real function-calling over the auxiliary tools.

This is what makes "6 function-calling tools" literally true: for a tool_query intent
(terminology lookup, unit conversion, emission factor, trend forecast), the LLM is given
the tools via bind_tools and DECIDES which to call. We execute the chosen tools, feed the
results back, and loop until the model stops requesting tools.

Why only the auxiliary tools (not run_sql / recommend_chart):
  * run_sql goes through the structured SQL Agent (with_structured_output) for injection
    safety — we don't want the LLM free-filling SQL params.
  * recommend_chart is a rule engine called directly by the Visualizer.

Output: a human-readable transcript of (tool, args, result) written to AgentState.tool_context.
The Interpreter then composes the final, streamed answer grounded ONLY in that transcript,
so terminology answers come from RAG / the DB rather than the model's imagination.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.agents.context import with_context
from app.agents.state import AgentState
from app.llm.provider import get_chat_model
from app.tools import AUX_TOOLS

logger = logging.getLogger(__name__)

# Guard against a runaway tool loop (a misbehaving model that never stops calling tools).
MAX_TOOL_ITERS = 4

_TOOL_MAP = {t.name: t for t in AUX_TOOLS}

_SYSTEM = """You are the Tool Agent of the EcoTEA data analysis platform.
You have these tools; call the most appropriate one(s) to answer the user's question:
- lookup_terminology(term): explain a commodity / sector / technology code or domain term
  (RAG + dictionary lookup). Use for "what is X?" / "which technologies use X?".
- convert_unit(value, from_unit, to_unit): exact energy (PJ/ktoe/GWh/...) or CO2 (kt/Mt/...) conversion.
- lookup_emission_factor(technology_code, year): a technology's emission factor for a year.
- forecast_trend(series, horizon, method): extrapolate a numeric (year, value) series the user gives.

Rules:
1. Prefer calling a tool over answering from memory — never invent a commodity definition,
   a conversion factor, or an emission value.
2. Call only the tools you actually need; you may call several.
3. Once you have the tool results, stop calling tools. The final answer is composed separately.
"""


def _render_transcript(steps: list[tuple[str, dict, Any]], draft: str) -> str:
    """Render the tool calls + results (and the model's draft) into text for the Interpreter."""
    lines: list[str] = []
    if steps:
        lines.append("[Tool results]")
        for i, (name, args, output) in enumerate(steps, 1):
            args_str = json.dumps(args, ensure_ascii=False, default=str)
            out_str = json.dumps(output, ensure_ascii=False, default=str)
            lines.append(f"{i}. {name}({args_str}) -> {out_str}")
    else:
        lines.append("[No tool was called]")
    if draft.strip():
        lines.append("")
        lines.append(f"[Model draft answer]\n{draft.strip()}")
    return "\n".join(lines)


def tool_agent_node(state: AgentState) -> dict:
    """LangGraph node: function-calling tool agent.

    In:  AgentState (reads messages)
    Out: { tool_context, error } (partial state update)
    """
    logger.info("tool_agent_node: start")

    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    question = str(user_messages[-1].content) if user_messages else "(unknown)"
    question = with_context(question, state["messages"])

    llm = get_chat_model().bind_tools(AUX_TOOLS)
    messages: list[Any] = [SystemMessage(content=_SYSTEM), HumanMessage(content=question)]
    steps: list[tuple[str, dict, Any]] = []
    draft = ""

    try:
        for _ in range(MAX_TOOL_ITERS):
            ai: AIMessage = llm.invoke(messages)
            messages.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            if not tool_calls:
                draft = ai.content if isinstance(ai.content, str) else str(ai.content)
                break
            for tc in tool_calls:
                name = tc.get("name", "")
                args = tc.get("args", {}) or {}
                tool = _TOOL_MAP.get(name)
                if tool is None:
                    output: Any = {"error": f"unknown tool '{name}'"}
                else:
                    try:
                        output = tool.invoke(args)
                    except Exception as exc:  # noqa: BLE001
                        output = {"error": f"{type(exc).__name__}: {exc!s}"}
                steps.append((name, args, output))
                messages.append(
                    ToolMessage(
                        content=json.dumps(output, ensure_ascii=False, default=str),
                        tool_call_id=tc.get("id", name),
                    )
                )
        logger.info("tool_agent_node: %d tool call(s)", len(steps))
        return {"tool_context": _render_transcript(steps, draft), "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool_agent_node: failed")
        return {"tool_context": None, "error": f"Tool agent failed: {exc!s}"}
