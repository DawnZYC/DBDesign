"""Agent 编排模块。

包含两类彼此解耦的 Agent：
  * 查询侧（M3）：Planner → SQL → Interpreter → Visualizer，LangGraph 编排。
    通过 build_graph() / AgentState 暴露。
  * 接入侧（M5）：schema_mapper —— 导入时对齐列布局，**不在** M3 的图里。

为让接入侧（仅依赖 openpyxl/pydantic）能在没装 langgraph 的环境里独立 import，
M3 的入口走 PEP 562 惰性加载：只有真正访问 build_graph/AgentState 时才 import
langgraph 相关模块。`from app.agents import schema_mapper` 不会触发这些重依赖。
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
