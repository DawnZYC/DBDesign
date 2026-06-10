"""M3 — Agent 编排单测。

测试策略：
  - 用 FakeListChatModel / patch 替换真实 LLM 调用，所有测试离线可运行
  - 测 planner_node：入参 / 输出结构 / 解析逻辑
  - 测 sql_agent_node：错误路径（structured output 失败 → error 字段）
  - 测 route_after_sql：条件边路由逻辑
  - 测 visualizer_node：无数据 / 有数据两条路径
  - 测 graph 编译：确认 graph 可正常 build_graph()（不调 LLM）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# 让 app 包可 import
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake")
os.environ.setdefault("LLM_PROVIDER", "openai")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")


# =============================================================================
# Helpers
# =============================================================================


def _make_state(**overrides) -> dict:
    """构造最小合法的 AgentState dict（用于单元测试）。"""
    from langchain_core.messages import HumanMessage

    base = {
        "messages": [HumanMessage(content="Power 部门 2030 年 capex")],
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
    """返回一个能 invoke() 的假 LLM（FakeListChatModel）。"""
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    return FakeListChatModel(responses=responses)


# =============================================================================
# planner_node
# =============================================================================


class TestPlannerNode:
    """测 planner_node 的入参 / 输出结构 / 重试提示注入。"""

    def test_normal_output_structure(self):
        """正常调用应返回含 plan 和 error=None 的 dict。"""
        fake_response = "- 查询 Power 部门 capex\n- 按年份聚合\n- 生成折线图"
        with patch("app.agents.planner.get_chat_model", return_value=_fake_llm([fake_response])):
            from app.agents.planner import planner_node

            result = planner_node(_make_state())

        assert isinstance(result, dict)
        assert "plan" in result
        assert isinstance(result["plan"], list)
        assert len(result["plan"]) == 3
        assert result["error"] is None

    def test_no_user_message_returns_error(self):
        """没有 HumanMessage 时应返回 error 字段。"""
        from langchain_core.messages import AIMessage

        state = _make_state(messages=[AIMessage(content="hello")])
        with patch("app.agents.planner.get_chat_model"):
            from app.agents.planner import planner_node

            result = planner_node(state)

        assert result["error"] is not None
        assert "missing" in result["error"]

    def test_retry_appends_error_note(self):
        """重试时，prompt 应包含上次错误信息。"""
        captured_messages = []

        def fake_factory():
            llm = MagicMock()

            def fake_invoke(msgs):
                captured_messages.extend(msgs)
                from langchain_core.messages import AIMessage

                return AIMessage(content="- 重新查询")

            llm.invoke = fake_invoke
            return llm

        state = _make_state(retry_count=1, error="SQL 执行失败: column not found")
        with patch("app.agents.planner.get_chat_model", side_effect=fake_factory):
            from app.agents.planner import planner_node

            planner_node(state)

        # 验证有某条 message 包含重试提示
        all_content = " ".join(str(m.content) for m in captured_messages)
        assert "重试" in all_content or "SQL 执行失败" in all_content

    def test_parse_numbered_list_fallback(self):
        """兜底：LLM 输出数字列表格式也能解析。"""
        fake_response = "1. 查询数据\n2. 聚合汇总\n3. 生成图表"
        with patch("app.agents.planner.get_chat_model", return_value=_fake_llm([fake_response])):
            from app.agents.planner import planner_node

            result = planner_node(_make_state())

        assert len(result["plan"]) == 3
        assert "查询数据" in result["plan"][0]

    def test_llm_failure_returns_error(self):
        """LLM 调用抛异常时，应捕获并返回 error 字段，不向上传播。"""

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
# _parse_plan（内部函数）
# =============================================================================


class TestParsePlan:
    """独立测 _parse_plan 解析逻辑。"""

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

        raw = "无法解析的内容"
        result = _parse_plan(raw)
        # 解析不到 bullet 时返回空列表；「全文当一步」的兜底上移到了
        # planner_node（仅 data_query 意图时触发，避免把 INTENT 行当步骤）
        assert result == []

    def test_ignores_blank_lines(self):
        from app.agents.planner import _parse_plan

        raw = "- step1\n\n- step2\n  \n- step3"
        assert _parse_plan(raw) == ["step1", "step2", "step3"]


# =============================================================================
# route_after_sql（条件边）
# =============================================================================


class TestRouteAfterSql:
    """测条件边路由函数的三条分支。"""

    def setup_method(self):
        # 保证 settings 的 agent_max_retries 有值
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

        # retry_count 等于 max_retries（默认 2），不再重试
        state = _make_state(error="SQL failed", retry_count=2)
        assert route_after_sql(state) == NODE_INTERPRETER

    def test_no_error_ignores_retry_count(self):
        """即使 retry_count > 0，只要没 error 就应走 interpreter。"""
        from app.agents.graph import NODE_INTERPRETER, route_after_sql

        state = _make_state(sql_result={"rows": []}, error=None, retry_count=1)
        assert route_after_sql(state) == NODE_INTERPRETER


# =============================================================================
# visualizer_node
# =============================================================================


class TestVisualizerNode:
    """测 visualizer_node 的有数据 / 无数据路径。"""

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
        """有数据行时，应生成含 dataset / series / _meta 的 spec。"""
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
        """ECharts dataset 的 dimensions 必须包含 raw_row_id（反查用）。"""
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
# graph.build_graph（编译正确性）
# =============================================================================


class TestBuildGraph:
    """仅测图可以成功编译，不执行任何 LLM 调用。"""

    def test_graph_compiles_without_error(self):
        from app.agents.graph import build_graph

        g = build_graph()
        assert g is not None

    def test_graph_has_expected_nodes(self):
        from app.agents.graph import (
            NODE_INTERPRETER,
            NODE_PLANNER,
            NODE_SQL,
            NODE_VISUALIZER,
            build_graph,
        )

        g = build_graph()
        node_names = set(g.nodes)
        assert NODE_PLANNER in node_names
        assert NODE_SQL in node_names
        assert NODE_INTERPRETER in node_names
        assert NODE_VISUALIZER in node_names

    def test_get_graph_returns_singleton(self):
        from app.agents.graph import get_graph

        g1 = get_graph()
        g2 = get_graph()
        assert g1 is g2


# =============================================================================
# 意图分流（修复「闲聊也跑 SQL + 画图」）
# =============================================================================


class TestIntentRouting:
    """Planner 意图解析 + 两条条件边的路由逻辑。"""

    def test_parse_intent_chat(self):
        from app.agents.planner import INTENT_DIRECT_ANSWER, _parse_intent

        assert _parse_intent("INTENT: chat") == INTENT_DIRECT_ANSWER
        assert _parse_intent("intent: chat\n") == INTENT_DIRECT_ANSWER

    def test_parse_intent_data_query(self):
        from app.agents.planner import INTENT_DATA_QUERY, _parse_intent

        assert _parse_intent("INTENT: data_query\n- 查询 capex") == INTENT_DATA_QUERY
        # 缺失 INTENT 行 → 保守默认 data_query（保持旧行为）
        assert _parse_intent("- 查询 capex\n- 画图") == INTENT_DATA_QUERY

    def test_planner_chat_intent(self):
        """LLM 判定闲聊 → intent=direct_answer 且无步骤。"""
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
            factory.return_value = _fake_llm(["INTENT: data_query\n- 查询 capex\n- 画折线图"])
            result = planner_node(_make_state())
        assert result["intent"] == INTENT_DATA_QUERY
        assert result["plan"] == ["查询 capex", "画折线图"]

    def test_route_after_planner(self):
        from app.agents.graph import NODE_INTERPRETER, NODE_SQL, route_after_planner

        assert route_after_planner(_make_state(intent="direct_answer")) == NODE_INTERPRETER
        assert route_after_planner(_make_state(intent="data_query")) == NODE_SQL
        assert route_after_planner(_make_state()) == NODE_SQL  # intent 缺失 → 旧行为

    def test_route_after_interpreter_skips_chart(self):
        from langgraph.graph import END

        from app.agents.graph import NODE_VISUALIZER, route_after_interpreter

        # 闲聊 → 不画图
        assert route_after_interpreter(_make_state(intent="direct_answer")) == END
        # 单行聚合结果 → 不画图
        one_row = {"rows": [{"value": 42}]}
        assert route_after_interpreter(_make_state(sql_result=one_row)) == END
        # 多行数据 → 画图
        many = {"rows": [{"y": 2020, "v": 1}, {"y": 2030, "v": 2}]}
        assert route_after_interpreter(_make_state(sql_result=many)) == NODE_VISUALIZER

    def test_chat_message_end_to_end_skips_sql_and_chart(self):
        """全图执行：闲聊消息 → planner→interpreter→END，不碰 SQL、不产图。"""
        import asyncio

        from langchain_core.messages import HumanMessage

        from app.agents.graph import build_graph

        with (
            patch("app.agents.planner.get_chat_model") as planner_factory,
            patch("app.agents.interpreter.get_chat_model") as interp_factory,
        ):
            planner_factory.return_value = _fake_llm(["INTENT: chat"])
            interp_factory.return_value = _fake_llm(["你好！我是 SG-TIMES 数据助手。"])
            g = build_graph()
            final = asyncio.run(g.ainvoke(_make_state(messages=[HumanMessage(content="你好")])))

        assert final.get("sql_params") is None, "闲聊不应触发 SQL Agent"
        assert final.get("chart_spec") is None, "闲聊不应产出图表"
        assert "SG-TIMES" in (final.get("interpretation") or "")
