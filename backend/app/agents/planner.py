"""Planner 节点 — 把用户问题分解为有序步骤列表。

职责：
  1. 读取对话历史中的最新用户消息
  2. 用 LLM 生成 3-5 条执行步骤（Markdown bullet list）
  3. 把步骤写入 AgentState.plan；清空 error 字段

特点：
  * 普通 llm.invoke，不需要工具或结构化输出
  * 输出 Markdown bullet list，后续节点解析为 plan: list[str]
  * 调用方（graph.py）负责把步骤作为 SSE agent_start 事件推给前端
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.llm.provider import get_chat_model

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """你是 SG-TIMES 数据分析平台的 Planner。
你的任务：把用户的自然语言问题拆解为 3-5 条简洁的执行步骤，步骤之间有顺序依赖。

输出格式要求（严格遵守）：
- 用 Markdown 无序列表，每行一个步骤
- 步骤从动词开始，简洁明确
- 不超过 5 条，每条不超过 30 个字
- 只输出步骤列表，不要解释或额外文字

数据库中可用的指标：capex, fixed_opex, variable_opex, emission_factor,
tax_cost, subsidy_cost, efficiency_value, technology_efficiency, heat_rate,
capacity_to_activity_factor, capacity, commodity_demand_value

示例输出：
- 查询 Power 部门 2018-2050 年的 capex 原始数据
- 按年份对 capex 求和聚合
- 用折线图展示趋势
"""


def _parse_plan(raw: str) -> list[str]:
    """把 LLM 输出的 Markdown bullet list 转为 list[str]。"""
    steps: list[str] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith(("- ", "* ", "• ")):
            step = line[2:].strip()
        elif line and line[0].isdigit() and ". " in line:
            # 兜底：处理 "1. xxx" 格式
            step = line.split(". ", 1)[-1].strip()
        else:
            continue
        if step:
            steps.append(step)
    return steps or [raw.strip()]  # 如果解析失败，把全文当一步兜底


# -----------------------------------------------------------------------------
# 节点函数
# -----------------------------------------------------------------------------
def planner_node(state: AgentState) -> dict:
    """LangGraph 节点：Planner。

    入参：AgentState（取 messages）
    出参：{ plan, error }（partial state update）
    """
    logger.info("planner_node: start (retry_count=%d)", state.get("retry_count", 0))

    # 取最近一条用户消息作为核心问题
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        logger.warning("planner_node: no HumanMessage found in state")
        return {"plan": ["无法理解问题，请重新提问"], "error": "missing user message"}

    latest_question = user_messages[-1].content

    # 如果是重试（retry_count > 0），把上一次的错误附在 prompt 里告知 LLM
    retry_note = ""
    if state.get("retry_count", 0) > 0 and state.get("error"):
        retry_note = (
            f"\n\n[重试提示] 上一次执行失败，错误：{state['error']}\n"
            "请调整查询策略，尝试更宽泛的过滤条件或换一种聚合方式。"
        )

    llm = get_chat_model()
    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=str(latest_question) + retry_note),
    ]

    try:
        response = llm.invoke(messages)
        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        plan = _parse_plan(raw_text)
        logger.info("planner_node: generated %d steps", len(plan))
        return {"plan": plan, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("planner_node: LLM call failed")
        return {"plan": [], "error": f"Planner 失败: {exc!s}"}
