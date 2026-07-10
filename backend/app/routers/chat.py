"""Chat router (M3) — POST /api/chat/stream.

Endpoint semantics:
  Receives the user message + conversation history, drives the LangGraph 4-agent graph,
  and pushes each stage's events to the frontend in real time via Server-Sent Events (SSE).

SSE event protocol (the M4 frontend parses by this):
  event: agent_start   data: {"node": "planner"|"sql_gen"|"interpreter"|"visualizer"}
  event: plan          data: {"steps": ["step1", "step2", ...]}
  event: token         data: {"delta": "..."}             <- Interpreter streaming tokens
  event: tool_call     data: {"tool": "run_sql", "args": {...}}
  event: tool_result   data: {"tool": "run_sql", "row_count": 12, "truncated": false}
  event: chart         data: {"spec": {...echarts option...}}
  event: agent_end     data: {"node": "..."}
  event: error         data: {"message": "..."}
  event: done          data: {"trace_id": "..."}

Implementation:
  * graph.astream_events(state, version="v2") subscribes to all events
  * filter the event types of interest by name / metadata.langgraph_node
  * sse_starlette.sse.EventSourceResponse wraps the async generator and pushes to the client
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app.agents.graph import (
    NODE_INTERPRETER,
    NODE_PLANNER,
    NODE_SQL,
    NODE_TOOL_AGENT,
    NODE_VISUALIZER,
    get_graph,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# -----------------------------------------------------------------------------
# Request / response schema
# -----------------------------------------------------------------------------
class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="The user's current message")
    history: list[ChatMessage] = Field(
        default_factory=list,
        description="Conversation history (excluding the current message), last 10 kept",
    )
    language: str | None = Field(
        default=None,
        description="Language the assistant should reply in (e.g. 'English', 'Chinese'). "
        "Empty/None = match the question's language.",
    )

    @property
    def lc_messages(self) -> list:
        """Convert history + current message into a list of LangChain BaseMessages."""
        msgs = []
        # Keep only the last 10 history messages (to avoid an overly long context)
        for cm in self.history[-10:]:
            if cm.role == "user":
                msgs.append(HumanMessage(content=cm.content))
            else:
                msgs.append(AIMessage(content=cm.content))
        msgs.append(HumanMessage(content=self.message))
        return msgs


# -----------------------------------------------------------------------------
# SSE event serialization helper
# -----------------------------------------------------------------------------
def _sse_event(event_type: str, data: Any) -> dict:
    """Format into the dict shape sse_starlette expects."""
    return {
        "event": event_type,
        "data": json.dumps(data, ensure_ascii=False, default=str),
    }


# -----------------------------------------------------------------------------
# Core async generator: drive the graph, convert LangGraph events to SSE events
# -----------------------------------------------------------------------------
async def _stream_graph_events(
    req: ChatRequest,
    trace_id: str,
) -> AsyncIterator[dict]:
    """Listen to LangGraph astream_events and convert events of interest into SSE dicts."""

    graph = get_graph()

    # Initial state
    initial_state = {
        "messages": req.lc_messages,
        "plan": [],
        "sql_params": None,
        "sql_result": None,
        "tool_context": None,
        "interpretation": None,
        "chart_spec": None,
        "language": req.language,
        "retry_count": 0,
        "error": None,
    }

    # Track the previous node, to emit agent_end
    current_node: str | None = None
    # Whether tokens were already pushed via on_chat_model_stream (avoid duplicate on_chain_end fallback)
    tokens_sent: bool = False

    try:
        async for event in graph.astream_events(initial_state, version="v2"):
            ev_type: str = event.get("event", "")
            metadata: dict = event.get("metadata", {})
            node: str = metadata.get("langgraph_node", "")

            logger.debug("LG event: type=%s node=%s name=%s", ev_type, node, event.get("name", ""))

            # ---- Node start ----
            if ev_type == "on_chain_start" and node and node != current_node:
                if node in (
                    NODE_PLANNER,
                    NODE_SQL,
                    NODE_TOOL_AGENT,
                    NODE_INTERPRETER,
                    NODE_VISUALIZER,
                ):
                    if current_node:
                        yield _sse_event("agent_end", {"node": current_node})
                    current_node = node
                    if node == NODE_INTERPRETER:
                        tokens_sent = False  # reset when entering a new interpreter node
                    yield _sse_event("agent_start", {"node": node})
                    logger.debug("SSE agent_start: node=%s", node)

            # ---- Planner done: push the plan ----
            # Note: on_chain_end fires once for each inner chain inside a node (LLM call /
            # prompt chain etc.), whose output is an AIMessage etc. rather than a dict. Only
            # handle the real node exit (output is a dict containing the 'plan' key).
            elif ev_type == "on_chain_end" and node == NODE_PLANNER:
                output = event.get("data", {}).get("output")
                if isinstance(output, dict):
                    plan = output.get("plan", [])
                    if plan:
                        yield _sse_event("plan", {"steps": plan})
                        logger.debug("SSE plan: steps=%d", len(plan))

            # ---- Tool call (SQL Agent's run_sql, or the Tool Agent's function-calling tools) ----
            elif ev_type == "on_tool_start" and node in (NODE_SQL, NODE_TOOL_AGENT):
                tool_name = event.get("name", "tool")
                tool_input = event.get("data", {}).get("input", {})
                yield _sse_event("tool_call", {"tool": tool_name, "args": tool_input})
                logger.debug("SSE tool_call: %s", tool_name)

            elif ev_type == "on_tool_end" and node in (NODE_SQL, NODE_TOOL_AGENT):
                tool_name = event.get("name", "tool")
                tool_output = event.get("data", {}).get("output", {})
                payload: dict[str, Any] = {"tool": tool_name}
                if isinstance(tool_output, dict) and "row_count" in tool_output:
                    # run_sql: rich, structured summary
                    payload.update(
                        {
                            "row_count": tool_output.get("row_count", 0),
                            "truncated": tool_output.get("truncated", False),
                            "metric": tool_output.get("metric"),
                            "sql_summary": tool_output.get("sql_summary", ""),
                        }
                    )
                else:
                    # aux tools: a short readable summary of the output
                    summary = json.dumps(tool_output, ensure_ascii=False, default=str)
                    payload["output_summary"] = summary[:200]
                yield _sse_event("tool_result", payload)
                logger.debug("SSE tool_result: %s", tool_name)

            # ---- Interpreter: streaming tokens (typewriter effect) ----
            elif ev_type == "on_chat_model_stream" and node == NODE_INTERPRETER:
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    delta = chunk.content if hasattr(chunk, "content") else str(chunk)
                    if delta:
                        tokens_sent = True
                        yield _sse_event("token", {"delta": delta})

            # ---- Interpreter done: if streaming tokens never fired, send the full text as fallback ----
            # Likewise, exclude the inner chain's (LLM's) on_chain_end whose output is an AIMessage, not a dict
            elif ev_type == "on_chain_end" and node == NODE_INTERPRETER:
                output = event.get("data", {}).get("output")
                if isinstance(output, dict) and not tokens_sent:
                    interpretation = output.get("interpretation") or ""
                    if interpretation:
                        logger.info("SSE token fallback: sending interpretation as single token")
                        yield _sse_event("token", {"delta": interpretation})
                        tokens_sent = True

            # ---- Visualizer done: push the chart ----
            elif ev_type == "on_chain_end" and node == NODE_VISUALIZER:
                output = event.get("data", {}).get("output")
                if isinstance(output, dict):
                    chart_spec = output.get("chart_spec")
                    if chart_spec:
                        yield _sse_event("chart", {"spec": chart_spec})
                        logger.debug(
                            "SSE chart: chart_type=%s",
                            chart_spec.get("_meta", {}).get("chart_type"),
                        )
                    # Check for an error
                    error = output.get("error")
                    if error:
                        yield _sse_event("error", {"message": error})

        # ---- End: agent_end for the last node ----
        if current_node:
            yield _sse_event("agent_end", {"node": current_node})

        yield _sse_event("done", {"trace_id": trace_id})
        logger.info("SSE stream done: trace_id=%s", trace_id)

    except Exception as exc:  # noqa: BLE001
        logger.exception("SSE stream error: trace_id=%s", trace_id)
        yield _sse_event("error", {"message": f"Server error: {exc!s}"})
        yield _sse_event("done", {"trace_id": trace_id})


# -----------------------------------------------------------------------------
# FastAPI endpoint
# -----------------------------------------------------------------------------
@router.post("/stream", summary="AI assistant streaming chat (SSE)")
async def chat_stream(req: ChatRequest) -> EventSourceResponse:
    """POST /api/chat/stream

    Receives the user message, drives the LangGraph 4-agent graph, and pushes execution
    events in real time via SSE.

    SSE event types:
    - agent_start / agent_end: node lifecycle
    - plan: Planner execution steps
    - tool_call / tool_result: tool-call trace
    - token: Interpreter streaming tokens (typewriter effect)
    - chart: full ECharts option
    - error: a local error (the stream continues)
    - done: stream-end signal
    """
    trace_id = str(uuid.uuid4())
    logger.info("chat_stream: start trace_id=%s message_len=%d", trace_id, len(req.message))

    return EventSourceResponse(
        _stream_graph_events(req, trace_id),
        media_type="text/event-stream",
    )
