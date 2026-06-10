"""Planner 节点 — 意图分流 + 把数据问题分解为有序步骤列表。

职责：
  1. 读取对话历史中的最新用户消息
  2. 用 LLM 判断意图（data_query / chat），并为数据问题生成 3-5 条执行步骤
  3. 把意图写入 AgentState.intent，步骤写入 AgentState.plan；清空 error 字段

意图分流（修复「闲聊也跑 SQL + 画图」）：
  * data_query     → 走 SQL Agent → Interpreter → Visualizer 全链路
  * direct_answer  → 直接交给 Interpreter 对话式回答，不查库、不画图

特点：
  * 普通 llm.invoke，意图与步骤在同一次调用中产出（省一次 LLM 往返）
  * 输出第一行为 `INTENT: ...`，后续为 Markdown bullet list
  * 解析失败时保守地按 data_query 处理（保持旧行为）
"""

from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.llm.provider import get_chat_model

logger = logging.getLogger(__name__)

INTENT_DATA_QUERY = "data_query"
INTENT_DIRECT_ANSWER = "direct_answer"

# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """你是 SG-TIMES 数据分析平台的 Planner。

第一步：判断用户消息的意图，在输出的第一行写：
  INTENT: data_query   —— 用户在询问数据库中的数据（指标数值、趋势、对比、排名、某技术的参数等）
  INTENT: chat         —— 问候、闲聊、感谢、问你是谁/平台能干什么、纯概念解释等不需要查数据库的消息

第二步：仅当 INTENT 为 data_query 时，把问题拆解为 3-5 条简洁的执行步骤：
- 用 Markdown 无序列表，每行一个步骤
- 步骤从动词开始，简洁明确
- 不超过 5 条，每条不超过 30 个字
INTENT 为 chat 时不输出任何步骤，只输出 INTENT 行。

数据库中可用的指标：capex, fixed_opex, variable_opex, emission_factor,
tax_cost, subsidy_cost, efficiency_value, technology_efficiency, heat_rate,
capacity_to_activity_factor, capacity, commodity_demand_value

示例 1（数据问题）：
INTENT: data_query
- 查询 Power 部门 2018-2050 年的 capex 原始数据
- 按年份对 capex 求和聚合
- 用折线图展示趋势

示例 2（闲聊 / 问候）：
INTENT: chat
"""


def _parse_intent(raw: str) -> str:
    """从 LLM 输出首部提取 INTENT；缺失或无法识别时默认 data_query（保守）。"""
    for line in raw.splitlines()[:3]:
        normalized = line.strip().lower()
        if normalized.startswith("intent"):
            return INTENT_DIRECT_ANSWER if "chat" in normalized else INTENT_DATA_QUERY
    return INTENT_DATA_QUERY


def _parse_plan(raw: str) -> list[str]:
    """把 LLM 输出的 Markdown bullet list 转为 list[str]（INTENT 行被自然跳过）。"""
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
    return steps


# -----------------------------------------------------------------------------
# 节点函数
# -----------------------------------------------------------------------------
def planner_node(state: AgentState) -> dict:
    """LangGraph 节点：Planner。

    入参：AgentState（取 messages）
    出参：{ plan, intent, error }（partial state update）
    """
    logger.info("planner_node: start (retry_count=%d)", state.get("retry_count", 0))

    # 取最近一条用户消息作为核心问题
    user_messages = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_messages:
        logger.warning("planner_node: no HumanMessage found in state")
        return {
            "plan": ["无法理解问题，请重新提问"],
            "intent": INTENT_DIRECT_ANSWER,
            "error": "missing user message",
        }

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
        intent = _parse_intent(raw_text)
        plan = _parse_plan(raw_text)
        if intent == INTENT_DATA_QUERY and not plan:
            # 数据问题但没解析出步骤：把全文当一步兜底（旧行为）
            plan = [raw_text.strip()]
        logger.info("planner_node: intent=%s, %d steps", intent, len(plan))
        return {"plan": plan, "intent": intent, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("planner_node: LLM call failed")
        return {"plan": [], "intent": INTENT_DATA_QUERY, "error": f"Planner 失败: {exc!s}"}
