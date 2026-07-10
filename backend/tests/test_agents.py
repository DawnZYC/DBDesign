"""M3 — Agent orchestration unit tests.

Testing strategy:
  - Replace the real LLM calls with FakeListChatModel / patch, so all tests run offline
  - Test planner_node: inputs / output structure / parsing logic
  - Test sql_agent_node: error path (structured output fails -> error field)
  - Test route_after_sql: conditional-edge routing logic
  - Test visualizer_node: no-data / with-data paths
  - Test graph compilation: confirm build_graph() works (without calling the LLM)
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Make the app package importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


# =============================================================================
# Helpers
# =============================================================================


def _make_state(**overrides) -> dict:
    """Build a minimal valid AgentState dict (for unit tests)."""
    from langchain_core.messages import HumanMessage

    base = {
        "messages": [HumanMessage(content="Power sector capex in 2030")],
        "plan": [],
        "sql_params": None,
        "sql_result": None,
        "interpretation": None,
        "chart_spec": None,
        "retry_count": 0,
        "error": None,
    }
    base.update(overrides)
    return base


def _fake_llm(responses: list[str]):
    """Return a fake LLM that supports invoke() (FakeListChatModel)."""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    return FakeListChatModel(responses=responses)


# =============================================================================
# planner_node
# =============================================================================


class TestPlannerNode:
    """Test planner_node's inputs / output structure / retry-note injection."""

    def test_normal_output_structure(self):
        """A normal call should return a dict with plan and error=None."""
        fake_response = "- Query Power sector capex\n- Aggregate by year\n- Produce a line chart"
        with patch("app.agents.planner.get_chat_model", return_value=_fake_llm([fake_response])):
            from app.agents.planner import planner_node

            result = planner_node(_make_state())

        assert isinstance(result, dict)
        assert "plan" in result
        assert isinstance(result["plan"], list)
        assert len(result["plan"]) == 3
        assert result["error"] is None

    def test_no_user_message_returns_error(self):
        """Without a HumanMessage, an error field should be returned."""
        from langchain_core.messages import AIMessage

        state = _make_state(messages=[AIMessage(content="hello")])
        with patch("app.agents.planner.get_chat_model"):
            from app.agents.planner import planner_node

            result = planner_node(state)

        assert result["error"] is not None
        assert "missing" in result["error"]

    def test_retry_appends_error_note(self):
        """On a retry, the prompt should include the previous error message."""
        captured_messages = []

        def fake_factory():
            llm = MagicMock()

            def fake_invoke(msgs):
                captured_messages.extend(msgs)
                from langchain_core.messages import AIMessage

                return AIMessage(content="- Re-query")

            llm.invoke = fake_invoke
            return llm

        state = _make_state(retry_count=1, error="SQL execution failed: column not found")
        with patch("app.agents.planner.get_chat_model", side_effect=fake_factory):
            from app.agents.planner import planner_node

            planner_node(state)

        # Verify some message contains the retry hint
        all_content = " ".join(str(m.content) for m in captured_messages)
        assert "Retry hint" in all_content or "SQL execution failed" in all_content

    def test_parse_numbered_list_fallback(self):
        """Fallback: a numbered-list LLM output is also parsed."""
        fake_response = "1. Query data\n2. Aggregate\n3. Produce chart"
        with patch("app.agents.planner.get_chat_model", return_value=_fake_llm([fake_response])):
            from app.agents.planner import planner_node

            result = planner_node(_make_state())

        assert len(result["plan"]) == 3
        assert "Query data" in result["plan"][0]

    def test_llm_failure_returns_error(self):
        """When the LLM call raises, it should be caught and returned as an error field, not propagated."""

        def exploding_factory():
            llm = MagicMock()
            llm.invoke.side_effect = RuntimeError("LLM timeout")
            return llm

        with patch("app.agents.planner.get_chat_model", side_effect=exploding_factory):
            from app.agents.planner import planner_node

            result = planner_node(_make_state())

        assert result["error"] is not None
        assert "Planner" in result["error"]
        assert result["plan"] == []


# =============================================================================
# _parse_plan (internal function)
# =============================================================================


class TestParsePlan:
    """Test the _parse_plan parsing logic in isolation."""

    def test_bullet_dash(self):
        from app.agents.planner import _parse_plan

        raw = "- step one\n- step two\n- step three"
        assert _parse_plan(raw) == ["step one", "step two", "step three"]

    def test_bullet_asterisk(self):
        from app.agents.planner import _parse_plan

        raw = "* step one\n* step two"
        assert _parse_plan(raw) == ["step one", "step two"]

    def test_numbered_list(self):
        from app.agents.planner import _parse_plan

        raw = "1. first\n2. second\n3. third"
        assert _parse_plan(raw) == ["first", "second", "third"]

    def test_empty_string_fallback(self):
        from app.agents.planner import _parse_plan

        raw = "unparseable content"
        result = _parse_plan(raw)
        # When no bullets are parsed, return an empty list; the "whole text as one step"
        # fallback moved up to planner_node (only triggered on data_query intent, to avoid
        # treating the INTENT line as a step)
        assert result == []

    def test_ignores_blank_lines(self):
        from app.agents.planner import _parse_plan

        raw = "- step1\n\n- step2\n  \n- step3"
        assert _parse_plan(raw) == ["step1", "step2", "step3"]


# =============================================================================
# route_after_sql (conditional edge)
# =============================================================================


class TestRouteAfterSql:
    """Test the three branches of the conditional-edge routing function."""

    def setup_method(self):
        # Ensure settings.agent_max_retries has a value
        os.environ["AGENT_MAX_RETRIES"] = "2"

    def test_success_routes_to_interpreter(self):
        from app.agents.graph import NODE_INTERPRETER, route_after_sql

        state = _make_state(sql_result={"rows": [], "row_count": 0}, error=None)
        assert route_after_sql(state) == NODE_INTERPRETER

    def test_error_within_retry_routes_to_planner(self):
        from app.agents.graph import NODE_PLANNER, route_after_sql

        state = _make_state(error="SQL failed", retry_count=0)
        result = route_after_sql(state)
        assert result == NODE_PLANNER

    def test_error_at_max_retry_routes_to_interpreter(self):
        from app.config import get_settings

        get_settings.cache_clear()
        from app.agents.graph import NODE_INTERPRETER, route_after_sql

        # retry_count equals max_retries (default 2), no more retries
        state = _make_state(error="SQL failed", retry_count=2)
        assert route_after_sql(state) == NODE_INTERPRETER

    def test_no_error_ignores_retry_count(self):
        """Even with retry_count > 0, as long as there is no error it should go to interpreter."""
        from app.agents.graph import NODE_INTERPRETER, route_after_sql

        state = _make_state(sql_result={"rows": []}, error=None, retry_count=1)
        assert route_after_sql(state) == NODE_INTERPRETER


# =============================================================================
# visualizer_node
# =============================================================================


class TestVisualizerNode:
    """Test visualizer_node's with-data / no-data paths."""

    def test_no_sql_result_returns_none_spec(self):
        from app.agents.visualizer import visualizer_node

        state = _make_state(sql_result=None)
        result = visualizer_node(state)
        assert result["chart_spec"] is None
        assert result["error"] is None

    def test_empty_rows_returns_none_spec(self):
        from app.agents.visualizer import visualizer_node

        sql_result = {
            "rows": [],
            "row_count": 0,
            "metric": "capex",
            "aggregation": "raw",
            "metric_unit": "M$",
        }
        state = _make_state(sql_result=sql_result)
        result = visualizer_node(state)
        assert result["chart_spec"] is None
        assert result["error"] is None

    def test_with_rows_produces_chart_spec(self):
        """With data rows, it should produce a spec containing dataset / series / _meta."""
        from app.agents.visualizer import visualizer_node

        sql_result = {
            "rows": [
                {"data_year": 2025, "sector_code": "POWER", "value": 100.0, "raw_row_id": 1},
                {"data_year": 2030, "sector_code": "POWER", "value": 150.0, "raw_row_id": 2},
                {"data_year": 2035, "sector_code": "POWER", "value": 200.0, "raw_row_id": 3},
            ],
            "row_count": 3,
            "metric": "capex",
            "aggregation": "raw",
            "metric_unit": "M$",
            "sql_summary": "metric=capex",
            "truncated": False,
        }
        state = _make_state(sql_result=sql_result)
        result = visualizer_node(state)

        assert result["error"] is None
        spec = result["chart_spec"]
        assert spec is not None
        assert "dataset" in spec
        assert "series" in spec
        assert "_meta" in spec
        assert spec["_meta"]["metric"] == "capex"

    def test_dataset_includes_raw_row_id(self):
        """The ECharts dataset dimensions must include raw_row_id (for trace-back)."""
        from app.agents.visualizer import visualizer_node

        sql_result = {
            "rows": [
                {"data_year": 2025, "value": 100.0, "raw_row_id": 42},
            ],
            "row_count": 1,
            "metric": "capex",
            "aggregation": "raw",
            "metric_unit": None,
            "sql_summary": "",
            "truncated": False,
        }
        state = _make_state(sql_result=sql_result)
        result = visualizer_node(state)
        spec = result["chart_spec"]
        dimensions = spec["dataset"]["dimensions"]
        assert "raw_row_id" in dimensions


# =============================================================================
# Tool Agent (function-calling over the auxiliary tools)
# =============================================================================


class TestToolAgent:
    """The tool_query path: Planner classifies it, the graph routes to the Tool Agent,
    and the Tool Agent actually executes the tool the (fake) LLM chose."""

    def test_parse_intent_tool_query(self):
        from app.agents.planner import INTENT_TOOL_QUERY, _parse_intent

        assert _parse_intent("INTENT: tool_query") == INTENT_TOOL_QUERY
        assert _parse_intent("intent: tool_query\n") == INTENT_TOOL_QUERY

    def test_route_after_planner_tool(self):
        from app.agents.graph import NODE_TOOL_AGENT, route_after_planner

        assert route_after_planner(_make_state(intent="tool_query")) == NODE_TOOL_AGENT

    def test_tool_agent_runs_chosen_tool(self):
        """The fake LLM requests convert_unit; the node must really run it and capture the result."""
        from langchain_core.messages import AIMessage, HumanMessage

        from app.agents.tool_agent import tool_agent_node

        calls = {"n": 0}

        class _Bound:
            def invoke(self, _messages):
                calls["n"] += 1
                if calls["n"] == 1:
                    return AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "convert_unit",
                                "args": {"value": 1, "from_unit": "PJ", "to_unit": "ktoe"},
                                "id": "call_1",
                                "type": "tool_call",
                            }
                        ],
                    )
                return AIMessage(content="1 PJ is about 23.885 ktoe.")

        class _LLM:
            def bind_tools(self, _tools):
                return _Bound()

        with patch("app.agents.tool_agent.get_chat_model", return_value=_LLM()):
            state = _make_state(messages=[HumanMessage(content="convert 1 PJ to ktoe")])
            out = tool_agent_node(state)

        assert out["error"] is None
        assert "convert_unit" in out["tool_context"]
        assert "ktoe" in out["tool_context"]
        assert calls["n"] >= 2  # called the tool, then composed (stopped requesting tools)

    def test_tool_agent_handles_no_tool_call(self):
        """If the LLM answers without calling a tool, tool_context still carries its draft."""
        from langchain_core.messages import AIMessage, HumanMessage

        from app.agents.tool_agent import tool_agent_node

        class _Bound:
            def invoke(self, _messages):
                return AIMessage(content="Hello, I can look up codes and convert units.")

        class _LLM:
            def bind_tools(self, _tools):
                return _Bound()

        with patch("app.agents.tool_agent.get_chat_model", return_value=_LLM()):
            out = tool_agent_node(_make_state(messages=[HumanMessage(content="hi")]))
        assert out["error"] is None
        assert "No tool was called" in out["tool_context"]


# =============================================================================
# graph.build_graph (compilation correctness)
# =============================================================================


class TestBuildGraph:
    """Only test that the graph compiles successfully, without any LLM calls."""

    def test_graph_compiles_without_error(self):
        from app.agents.graph import build_graph

        g = build_graph()
        assert g is not None

    def test_graph_has_expected_nodes(self):
        from app.agents.graph import (
            NODE_INTERPRETER,
            NODE_PLANNER,
            NODE_SQL,
            NODE_TOOL_AGENT,
            NODE_VISUALIZER,
            build_graph,
        )

        g = build_graph()
        node_names = set(g.nodes)
        assert NODE_PLANNER in node_names
        assert NODE_SQL in node_names
        assert NODE_TOOL_AGENT in node_names
        assert NODE_INTERPRETER in node_names
        assert NODE_VISUALIZER in node_names

    def test_get_graph_returns_singleton(self):
        from app.agents.graph import get_graph

        g1 = get_graph()
        g2 = get_graph()
        assert g1 is g2


# =============================================================================
# Intent routing (fixes "small talk also runs SQL + charts")
# =============================================================================


class TestIntentRouting:
    """Planner intent parsing + the routing logic of the two conditional edges."""

    def test_parse_intent_chat(self):
        from app.agents.planner import INTENT_DIRECT_ANSWER, _parse_intent

        assert _parse_intent("INTENT: chat") == INTENT_DIRECT_ANSWER
        assert _parse_intent("intent: chat\n") == INTENT_DIRECT_ANSWER

    def test_parse_intent_data_query(self):
        from app.agents.planner import INTENT_DATA_QUERY, _parse_intent

        assert _parse_intent("INTENT: data_query\n- query capex") == INTENT_DATA_QUERY
        # Missing INTENT line -> conservative default data_query (preserves old behavior)
        assert _parse_intent("- query capex\n- draw chart") == INTENT_DATA_QUERY

    def test_planner_chat_intent(self):
        """The LLM classifies small talk -> intent=direct_answer with no steps."""
        from app.agents.planner import INTENT_DIRECT_ANSWER, planner_node

        with patch("app.agents.planner.get_chat_model") as factory:
            factory.return_value = _fake_llm(["INTENT: chat"])
            result = planner_node(_make_state())
        assert result["intent"] == INTENT_DIRECT_ANSWER
        assert result["plan"] == []
        assert result["error"] is None

    def test_planner_data_intent_keeps_steps(self):
        from app.agents.planner import INTENT_DATA_QUERY, planner_node

        with patch("app.agents.planner.get_chat_model") as factory:
            factory.return_value = _fake_llm(
                ["INTENT: data_query\n- query capex\n- draw a line chart"]
            )
            result = planner_node(_make_state())
        assert result["intent"] == INTENT_DATA_QUERY
        assert result["plan"] == ["query capex", "draw a line chart"]

    def test_route_after_planner(self):
        from app.agents.graph import NODE_INTERPRETER, NODE_SQL, route_after_planner

        assert route_after_planner(_make_state(intent="direct_answer")) == NODE_INTERPRETER
        assert route_after_planner(_make_state(intent="data_query")) == NODE_SQL
        assert route_after_planner(_make_state()) == NODE_SQL  # missing intent -> old behavior

    def test_route_after_interpreter_skips_chart(self):
        from langgraph.graph import END

        from app.agents.graph import NODE_VISUALIZER, route_after_interpreter

        # small talk -> no chart
        assert route_after_interpreter(_make_state(intent="direct_answer")) == END
        # single-row aggregate result -> no chart
        one_row = {"rows": [{"value": 42}]}
        assert route_after_interpreter(_make_state(sql_result=one_row)) == END
        # multi-row data -> chart
        many = {"rows": [{"y": 2020, "v": 1}, {"y": 2030, "v": 2}]}
        assert route_after_interpreter(_make_state(sql_result=many)) == NODE_VISUALIZER

    def test_chat_message_end_to_end_skips_sql_and_chart(self):
        """Full-graph run: a small-talk message -> planner->interpreter->END, never touching SQL or charts."""
        import asyncio

        from langchain_core.messages import HumanMessage

        from app.agents.graph import build_graph

        with (
            patch("app.agents.planner.get_chat_model") as planner_factory,
            patch("app.agents.interpreter.get_chat_model") as interp_factory,
        ):
            planner_factory.return_value = _fake_llm(["INTENT: chat"])
            interp_factory.return_value = _fake_llm(["Hello! I'm the ESM data assistant."])
            g = build_graph()
            final = asyncio.run(g.ainvoke(_make_state(messages=[HumanMessage(content="hi")])))

        assert final.get("sql_params") is None, "small talk should not trigger the SQL Agent"
        assert final.get("chart_spec") is None, "small talk should not produce a chart"
        assert "ESM" in (final.get("interpretation") or "")


# =============================================================================
# Multi-turn context (fixes "said power last turn, replied capex this turn but it was forgotten")
# =============================================================================


class TestConversationContext:
    def _relay_messages(self):
        from langchain_core.messages import AIMessage, HumanMessage

        return [
            HumanMessage(content="help me look at power data"),
            AIMessage(content="Which metric would you like? e.g. capex, O&M cost, etc."),
            HumanMessage(content="capex"),
        ]

    def test_render_context_excludes_current_message(self):
        from app.agents.context import render_context

        ctx = render_context(self._relay_messages())
        assert "power" in ctx
        assert "metric" in ctx
        # The current message (capex) should not appear in the context block
        assert "User: capex" not in ctx

    def test_with_context_wraps_question(self):
        from app.agents.context import with_context

        prompt = with_context("capex", self._relay_messages())
        assert "[Conversation context]" in prompt
        assert "power" in prompt
        assert prompt.rstrip().endswith("capex")

    def test_with_context_no_history_returns_question(self):
        from langchain_core.messages import HumanMessage

        from app.agents.context import with_context

        assert with_context("hello", [HumanMessage(content="hello")]) == "hello"

    def test_planner_prompt_carries_history(self):
        """The "capex" follow-up message: the Planner prompt must include power from the previous turn."""
        from app.agents.planner import planner_node

        captured: list = []

        def fake_factory():
            llm = MagicMock()

            def fake_invoke(msgs):
                captured.extend(msgs)
                from langchain_core.messages import AIMessage

                return AIMessage(content="INTENT: data_query\n- Query Power sector capex")

            llm.invoke = fake_invoke
            return llm

        state = _make_state(messages=self._relay_messages())
        with patch("app.agents.planner.get_chat_model", side_effect=fake_factory):
            result = planner_node(state)

        human_prompt = str(captured[-1].content)
        assert (
            "power" in human_prompt
        ), "the Planner prompt should include power from the previous turn"
        assert result["intent"] == "data_query"

    def test_sql_agent_prompt_carries_history(self):
        """The SQL Agent's structured-output prompt must also carry the context."""
        from app.agents.sql_agent import sql_agent_node

        captured: list = []

        def fake_factory():
            llm = MagicMock()
            structured = MagicMock()

            def fake_invoke(msgs):
                captured.extend(msgs)
                raise RuntimeError(
                    "stop here"
                )  # only verify the prompt, don't actually run the query

            structured.invoke = fake_invoke
            llm.with_structured_output.return_value = structured
            return llm

        state = _make_state(messages=self._relay_messages(), plan=["query capex"])
        with patch("app.agents.sql_agent.get_chat_model", side_effect=fake_factory):
            sql_agent_node(state)

        human_prompt = str(captured[-1].content)
        assert (
            "power" in human_prompt
        ), "the SQL Agent prompt should include power from the previous turn"
