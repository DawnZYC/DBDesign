"""Agent 编排模块（M3）。

对外暴露：
  build_graph()  — 构造编译好的 LangGraph CompiledGraph
  AgentState     — 图节点共用的状态 TypedDict
"""
from app.agents.graph import build_graph
from app.agents.state import AgentState

__all__ = ["AgentState", "build_graph"]
