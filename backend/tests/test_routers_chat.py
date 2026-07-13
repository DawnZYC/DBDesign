"""Chat router (M3/M4) — SSE stream unit tests.

Strategy: patch app.routers.chat.get_graph with a fake graph whose astream_events
yields a scripted LangGraph event sequence, then assert the SSE events produced by
_stream_graph_events (and by the full POST /api/chat/stream endpoint). No LLM, no DB.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import patch

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage

from app.agents.graph import (
    NODE_INTERPRETER,
    NODE_PLANNER,
    NODE_SQL,
    NODE_TOOL_AGENT,
    NODE_VISUALIZER,
)
from app.routers.chat import ChatMessage, ChatRequest, _sse_event, _stream_graph_events


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
class FakeGraph:
    """Minimal stand-in for the compiled LangGraph graph."""

    def __init__(self, events: list[dict], error: Exception | None = None):
        self._events = events
        self._error = error

    async def astream_events(self, _state, version):  # noqa: ANN001
        assert version == "v2"
        for ev in self._events:
            yield ev
        if self._error is not None:
            raise self._error


def _collect(events: list[dict], error: Exception | None = None) -> list[tuple[str, dict]]:
    """Drive _stream_graph_events over a scripted event list; return [(event, payload)]."""

    async def _run() -> list[tuple[str, dict]]:
        req = ChatRequest(message="Power sector capex 2030")
        out = []
        with patch("app.routers.chat.get_graph", return_value=FakeGraph(events, error)):
            async for sse in _stream_graph_events(req, trace_id="t-123"):
                out.append((sse["event"], json.loads(sse["data"])))
        return out

    return asyncio.run(_run())


def _ev(ev_type: str, node: str, name: str = "", data: dict | None = None) -> dict:
    return {
        "event": ev_type,
        "name": name,
        "metadata": {"langgraph_node": node},
        "data": data or {},
    }


# -----------------------------------------------------------------------------
# ChatRequest.lc_messages
# -----------------------------------------------------------------------------
def test_lc_messages_roles_and_current_message():
    req = ChatRequest(
        message="and 2040?",
        history=[
            ChatMessage(role="user", content="capex 2030"),
            ChatMessage(role="assistant", content="It is X."),
        ],
    )
    msgs = req.lc_messages
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert isinstance(msgs[-1], HumanMessage)
    assert msgs[-1].content == "and 2040?"


def test_lc_messages_keeps_only_last_10_history():
    history = [ChatMessage(role="user", content=f"m{i}") for i in range(25)]
    req = ChatRequest(message="latest", history=history)
    msgs = req.lc_messages
    assert len(msgs) == 11  # 10 history + current
    assert msgs[0].content == "m15"


def test_sse_event_serializes_payload():
    ev = _sse_event("token", {"delta": "你好"})
    assert ev["event"] == "token"
    assert json.loads(ev["data"]) == {"delta": "你好"}


# -----------------------------------------------------------------------------
# _stream_graph_events: happy-path event translation
# -----------------------------------------------------------------------------
def test_full_pipeline_event_sequence():
    events = [
        _ev("on_chain_start", NODE_PLANNER, name=NODE_PLANNER),
        _ev("on_chain_end", NODE_PLANNER, data={"output": {"plan": ["query", "chart"]}}),
        _ev("on_chain_start", NODE_SQL, name=NODE_SQL),
        _ev("on_tool_start", NODE_SQL, name="run_sql", data={"input": {"metric": "capex"}}),
        _ev(
            "on_tool_end",
            NODE_SQL,
            name="run_sql",
            data={
                "output": {
                    "row_count": 3,
                    "truncated": False,
                    "metric": "capex",
                    "sql_summary": "capex by year",
                }
            },
        ),
        _ev("on_chain_start", NODE_INTERPRETER, name=NODE_INTERPRETER),
        _ev(
            "on_chat_model_stream",
            NODE_INTERPRETER,
            data={"chunk": AIMessageChunk(content="Capex rises")},
        ),
        _ev("on_chain_start", NODE_VISUALIZER, name=NODE_VISUALIZER),
        _ev(
            "on_chain_end",
            NODE_VISUALIZER,
            data={"output": {"chart_spec": {"_meta": {"chart_type": "line"}}, "error": None}},
        ),
    ]
    out = _collect(events)
    types = [t for t, _ in out]

    assert types[0] == "agent_start"
    assert "plan" in types
    assert "tool_call" in types
    assert "tool_result" in types
    assert "token" in types
    assert "chart" in types
    assert types[-1] == "done"
    assert types[-2] == "agent_end"

    payloads = dict(out)
    assert payloads["plan"] == {"steps": ["query", "chart"]}
    assert payloads["tool_call"] == {"tool": "run_sql", "args": {"metric": "capex"}}
    assert payloads["tool_result"]["row_count"] == 3
    assert payloads["token"] == {"delta": "Capex rises"}
    assert payloads["chart"]["spec"]["_meta"]["chart_type"] == "line"
    assert payloads["done"] == {"trace_id": "t-123"}


def test_agent_end_emitted_between_nodes():
    events = [
        _ev("on_chain_start", NODE_PLANNER, name=NODE_PLANNER),
        _ev("on_chain_start", NODE_SQL, name=NODE_SQL),
    ]
    out = _collect(events)
    types = [t for t, _ in out]
    # planner start -> planner end -> sql start -> (final) sql end -> done
    assert types == ["agent_start", "agent_end", "agent_start", "agent_end", "done"]
    assert out[1][1] == {"node": NODE_PLANNER}
    assert out[3][1] == {"node": NODE_SQL}


def test_inner_chain_end_with_non_dict_output_is_ignored():
    """on_chain_end whose output is an AIMessage (inner LLM chain) must not emit a plan."""
    events = [
        _ev("on_chain_start", NODE_PLANNER, name=NODE_PLANNER),
        _ev("on_chain_end", NODE_PLANNER, data={"output": AIMessage(content="not a dict")}),
    ]
    out = _collect(events)
    assert "plan" not in [t for t, _ in out]


def test_aux_tool_result_uses_output_summary():
    events = [
        _ev("on_chain_start", NODE_TOOL_AGENT, name=NODE_TOOL_AGENT),
        _ev(
            "on_tool_end",
            NODE_TOOL_AGENT,
            name="convert_unit",
            data={"output": {"value": 23.88, "unit": "ktoe"}},
        ),
    ]
    out = _collect(events)
    payloads = dict(out)
    assert payloads["tool_result"]["tool"] == "convert_unit"
    assert "23.88" in payloads["tool_result"]["output_summary"]


def test_interpreter_fallback_token_when_no_stream():
    """If no on_chat_model_stream fired, the interpreter's final text goes out as one token."""
    events = [
        _ev("on_chain_start", NODE_INTERPRETER, name=NODE_INTERPRETER),
        _ev(
            "on_chain_end",
            NODE_INTERPRETER,
            data={"output": {"interpretation": "full answer"}},
        ),
    ]
    out = _collect(events)
    payloads = dict(out)
    assert payloads["token"] == {"delta": "full answer"}


def test_no_duplicate_fallback_after_streamed_tokens():
    events = [
        _ev("on_chain_start", NODE_INTERPRETER, name=NODE_INTERPRETER),
        _ev(
            "on_chat_model_stream",
            NODE_INTERPRETER,
            data={"chunk": AIMessageChunk(content="streamed")},
        ),
        _ev(
            "on_chain_end",
            NODE_INTERPRETER,
            data={"output": {"interpretation": "streamed"}},
        ),
    ]
    out = _collect(events)
    tokens = [p for t, p in out if t == "token"]
    assert tokens == [{"delta": "streamed"}]


def test_visualizer_error_is_forwarded():
    events = [
        _ev("on_chain_start", NODE_VISUALIZER, name=NODE_VISUALIZER),
        _ev(
            "on_chain_end",
            NODE_VISUALIZER,
            data={"output": {"chart_spec": None, "error": "boom"}},
        ),
    ]
    out = _collect(events)
    payloads = dict(out)
    assert payloads["error"] == {"message": "boom"}
    assert "chart" not in [t for t, _ in out]


def test_graph_exception_yields_error_then_done():
    events = [_ev("on_chain_start", NODE_PLANNER, name=NODE_PLANNER)]
    out = _collect(events, error=RuntimeError("graph exploded"))
    types = [t for t, _ in out]
    assert "error" in types
    assert types[-1] == "done"
    payloads = dict(out)
    assert "graph exploded" in payloads["error"]["message"]


# -----------------------------------------------------------------------------
# Endpoint smoke: POST /api/chat/stream returns a well-formed SSE body
# -----------------------------------------------------------------------------
def test_chat_stream_endpoint(client):
    events = [
        _ev("on_chain_start", NODE_PLANNER, name=NODE_PLANNER),
        _ev("on_chain_end", NODE_PLANNER, data={"output": {"plan": ["step"]}}),
    ]
    with patch("app.routers.chat.get_graph", return_value=FakeGraph(events)):
        resp = client.post("/api/chat/stream", json={"message": "hello", "history": []})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert "event: agent_start" in resp.text
    assert "event: plan" in resp.text
    assert "event: done" in resp.text


def test_chat_stream_rejects_empty_message(client):
    resp = client.post("/api/chat/stream", json={"message": "", "history": []})
    assert resp.status_code == 422
