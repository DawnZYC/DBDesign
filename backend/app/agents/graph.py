"""LangGraph 编排 — 4-Agent 状态图。

图结构：
  START → planner → sql_gen → [条件边] → interpreter → visualizer → END
                                    ↓ (失败且未超重试上限)
                                  planner（重试）

条件边逻辑（route_after_sql）：
  - sql_result 存在且无 error → interpreter
  - error 存在且 retry_count < max_retries → planner（重试，retry_count+1）
  - error 存在且已达上限 → interpreter（带错误信息，让 Interpreter 告知用户）

使用方式：
  from app.agents.graph import build_graph

  graph = build_graph()

  # 同步调用（用于简单测试）
  result = graph.invoke({"messages": [HumanMessage(content="...")], ...})

  # 异步 + 事件流（SSE 端点用）
  async for event in graph.astream_events(initial_state, version="v2"):
      ...
"""
from __future__ import annotations

import logging

from langgraph.graph import END, START, StateGraph

from app.agents.planner import planner_node
from app.agents.sql_agent import sql_agent_node
from app.agents.interpreter import interpreter_node
from app.agents.visualizer import visualizer_node
from app.agents.state import AgentState
from app.config import get_settings

logger = logging.getLogger(__name__)

# 节点名称常量（避免魔法字符串散落各处）
NODE_PLANNER = "planner"
NODE_SQL = "sql_gen"
NODE_INTERPRETER = "interpreter"
NODE_VISUALIZER = "visualizer"


# -----------------------------------------------------------------------------
# 条件边：SQL 节点完成后的路由
# -----------------------------------------------------------------------------
def route_after_sql(state: AgentState) -> str:
    """决定 sql_gen 节点执行完后流向哪个节点。

    返回值必须是 graph.add_conditional_edges 的 path_map 中的 key。
    """
    settings = get_settings()
    has_error = bool(state.get("error"))
    retry_count = state.get("retry_count", 0)

    if not has_error:
        # 成功：走正常路径
        logger.debug("route_after_sql → interpreter (ok)")
        return NODE_INTERPRETER

    if retry_count < settings.agent_max_retries:
        # 有错误但还有重试机会：回 Planner
        logger.info(
            "route_after_sql → planner (retry %d/%d, error=%s)",
            retry_count + 1,
            settings.agent_max_retries,
            state.get("error", "")[:80],
        )
        return NODE_PLANNER

    # 已达重试上限：强制走 interpreter（让它告知用户失败）
    logger.warning(
        "route_after_sql → interpreter (max retries exhausted, error=%s)",
        state.get("error", "")[:80],
    )
    return NODE_INTERPRETER


# -----------------------------------------------------------------------------
# 重试计数包装
# -----------------------------------------------------------------------------
def _sql_gen_with_retry_increment(state: AgentState) -> dict:
    """在 sql_agent_node 外层套一个重试计数：失败时 retry_count + 1。

    LangGraph 不支持在条件边里修改 state，所以在节点出口处处理。
    """
    result = sql_agent_node(state)
    if result.get("error"):
        result["retry_count"] = state.get("retry_count", 0) + 1
    return result


# -----------------------------------------------------------------------------
# 图构造
# -----------------------------------------------------------------------------
def build_graph() -> "CompiledGraph":  # type: ignore[name-defined]
    """构造并编译 LangGraph 状态图。

    每次调用都新建（不缓存），调用方负责复用已编译的图。
    实际上 build_graph() 本身很快（不涉及 I/O），router 层用模块级单例即可。
    """
    graph = StateGraph(AgentState)

    # ---- 注册节点 ----
    graph.add_node(NODE_PLANNER, planner_node)
    graph.add_node(NODE_SQL, _sql_gen_with_retry_increment)
    graph.add_node(NODE_INTERPRETER, interpreter_node)
    graph.add_node(NODE_VISUALIZER, visualizer_node)

    # ---- 固定边 ----
    graph.add_edge(START, NODE_PLANNER)
    graph.add_edge(NODE_PLANNER, NODE_SQL)
    graph.add_edge(NODE_INTERPRETER, NODE_VISUALIZER)
    graph.add_edge(NODE_VISUALIZER, END)

    # ---- 条件边：sql_gen 完成后路由 ----
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
# 模块级单例（路由层复用，避免重复编译）
# -----------------------------------------------------------------------------
# 延迟初始化：首次 import 时不执行（避免测试环境无 DB 时报错）
_graph_instance = None


def get_graph():
    """获取（或延迟初始化）模块级图单例。"""
    global _graph_instance
    if _graph_instance is None:
        _graph_instance = build_graph()
    return _graph_instance
