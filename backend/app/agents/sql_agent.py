"""SQL Agent 节点 — 把执行计划转换为结构化 QueryParams，调用 run_sql 工具执行。

职责：
  1. 读取 AgentState.plan（Planner 的步骤列表）
  2. 用 llm.with_structured_output(QueryParams) 强约束 LLM 输出
     - 禁止裸字符串 SQL，只允许填写 Pydantic 字段
     - 字段白名单由 QueryParams 本身的 Literal / validator 保证
  3. 调用 run_sql 工具执行，把结果写入 AgentState.sql_result
  4. 失败时写入 error，交由 graph.py 的条件边决定是否重试

安全性保证（继承自 M2 run_sql 工具）：
  * 输入只能是 QueryParams 字段，LLM 无法注入任意 SQL
  * 所有过滤值走 SQLAlchemy bindparam，无字符串拼接
  * 结果行数硬上限 10000
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from app.agents.state import AgentState
from app.llm.provider import get_chat_model
from app.tools.sql_runner import QueryParams, run_sql

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """你是 SG-TIMES 数据分析平台的 SQL Agent。
你的任务：根据执行计划，生成一个 QueryParams 对象（结构化输出），用于安全地查询数据库。

可用指标（metric 字段的合法值）：
  capex, fixed_opex, variable_opex, emission_factor, tax_cost, subsidy_cost,
  efficiency_value, technology_efficiency, heat_rate, capacity_to_activity_factor,
  capacity, commodity_demand_value

聚合方式（aggregation）：raw（默认，带 raw_row_id）, sum, avg, min, max, count

分组维度（group_by 列表中的合法值）：sector, geography, technology, year, commodity

过滤字段：
  - sector_codes: 部门代码列表，如 ["POWER", "INDUSTRY"]
  - geography_codes: 地理代码列表，如 ["SG"]
  - technology_codes: 精确技术代码列表
  - technology_code_like: 技术代码模糊匹配（ILIKE %X%），如 "PWRSOL"
  - year_min / year_max: 年份范围（整数）
  - limit: 最大返回行数（默认 1000，上限 10000）

规则：
1. aggregation='raw' 时结果含 raw_row_id，用于图表反查源单元格（优先选 raw）
2. 若计划要求聚合统计，aggregation 选 sum/avg/count 等，并填 group_by
3. 不要选超出白名单的 metric 名称
4. 代码/名称不确定时，用 technology_code_like 做模糊匹配
"""


def _plan_to_prompt(plan: list[str], question: str) -> str:
    """把计划和原始问题组合成给 SQL Agent 的 prompt。"""
    plan_text = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(plan))
    return (
        f"用户原始问题：{question}\n\n"
        f"执行计划：\n{plan_text}\n\n"
        "请根据以上计划，填写 QueryParams 来完成第一步数据查询。"
        "若计划有多个查询步骤，只生成最关键的那一次查询。"
    )


# -----------------------------------------------------------------------------
# 节点函数
# -----------------------------------------------------------------------------
def sql_agent_node(state: AgentState) -> dict:
    """LangGraph 节点：SQL Agent。

    入参：AgentState（取 messages + plan）
    出参：{ sql_params, sql_result, error }（partial state update）
    """
    logger.info("sql_agent_node: start")

    plan = state.get("plan") or []
    if not plan:
        return {
            "sql_params": None,
            "sql_result": None,
            "error": "plan 为空，无法生成 SQL 参数",
        }

    # 取原始用户问题（用于构造提示）
    from langchain_core.messages import HumanMessage as HMsg
    user_msgs = [m for m in state["messages"] if isinstance(m, HMsg)]
    question = str(user_msgs[-1].content) if user_msgs else "(unknown)"

    # ---- Step 1: LLM 结构化输出 → QueryParams ----
    llm = get_chat_model()
    structured_llm = llm.with_structured_output(QueryParams)

    messages = [
        SystemMessage(content=_SYSTEM),
        HumanMessage(content=_plan_to_prompt(plan, question)),
    ]

    try:
        params: QueryParams = structured_llm.invoke(messages)
        logger.info(
            "sql_agent_node: structured output ok metric=%s agg=%s",
            params.metric, params.aggregation,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("sql_agent_node: structured output failed")
        return {
            "sql_params": None,
            "sql_result": None,
            "error": f"SQL Agent 结构化输出失败: {exc!s}",
        }

    # ---- Step 2: 调用 run_sql 工具执行 ----
    try:
        result_dict: dict[str, Any] = run_sql.invoke(params.model_dump())
        logger.info(
            "sql_agent_node: run_sql ok row_count=%s truncated=%s",
            result_dict.get("row_count"), result_dict.get("truncated"),
        )
        return {
            "sql_params": params.model_dump(),
            "sql_result": result_dict,
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("sql_agent_node: run_sql execution failed")
        return {
            "sql_params": params.model_dump(),
            "sql_result": None,
            "error": f"SQL 执行失败: {exc!s}",
        }
