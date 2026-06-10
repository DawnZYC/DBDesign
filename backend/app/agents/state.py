"""AgentState — LangGraph 图节点之间共享的状态结构。

设计原则：
  * 只存节点之间需要传递的「跨越节点边界」的数据
  * messages 走 LangChain add_messages reducer（append-only）
  * 其余字段用最后写入值（LangGraph 默认 last-write-wins）
  * 所有可选字段默认 None，节点负责填写并向后传
"""

from __future__ import annotations

from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """4-Agent 流水线的全局状态。

    字段流向：
        messages      — 对话历史（用户 + assistant），add_messages 累加
        plan          — Planner 输出的步骤列表（自然语言 / Markdown bullet）
        sql_params    — SQL Agent 输出的结构化查询参数（QueryParams 序列化后的 dict）
        sql_result    — run_sql 工具的执行结果（QueryResult.model_dump()）
        interpretation — Interpreter 输出的自然语言分析文本
        chart_spec    — Visualizer 输出的 ECharts spec（完整 option dict）
        retry_count   — 当前已重试次数（SQL 失败 → 回 Planner）
        error         — 最新错误描述；节点正常完成后清为 None
    """

    # 对话历史：使用 add_messages reducer，每次 update 是 append 而非覆盖
    messages: Annotated[list[BaseMessage], add_messages]

    # Planner 产物
    plan: list[str]

    # SQL Agent 产物
    sql_params: dict[str, Any] | None  # app.tools.sql_runner.QueryParams.model_dump()

    # run_sql 工具产物
    sql_result: dict[str, Any] | None  # QueryResult.model_dump()

    # Interpreter 产物
    interpretation: str | None

    # Visualizer 产物
    chart_spec: dict[str, Any] | None  # EChartsSpec.model_dump()

    # 流控
    retry_count: int
    error: str | None
