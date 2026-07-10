"""SQL Agent node — turn the execution plan into structured QueryParams and run the run_sql tool.

Responsibilities:
  1. Read AgentState.plan (the Planner's step list).
  2. Use llm.with_structured_output(QueryParams) to strongly constrain the LLM output
     - no raw SQL strings; only Pydantic fields may be filled
     - the field whitelist is enforced by QueryParams' own Literal / validators
  3. Run the run_sql tool and write the result into AgentState.sql_result.
  4. On failure, write error and let graph.py's conditional edge decide on retry.

Safety guarantees (inherited from the M2 run_sql tool):
  * Input is limited to QueryParams fields; the LLM cannot inject arbitrary SQL.
  * All filter values go through SQLAlchemy bindparam, no string concatenation.
  * Result rows are hard-capped at 10000.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.state import AgentState
from app.llm.provider import get_chat_model
from app.tools.sql_runner import QueryParams, run_sql

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Prompt
# -----------------------------------------------------------------------------
_SYSTEM = """You are the SQL Agent of the EcoTEA data analysis platform.
Your task: given the execution plan, produce one QueryParams object
(structured output) for a safe database query.

Valid metrics (the `metric` field):
  capex, fixed_opex, variable_opex, emission_factor, tax_cost, subsidy_cost,
  efficiency_value, technology_efficiency, heat_rate, capacity_to_activity_factor,
  capacity, commodity_demand_value

Aggregations: raw (default, rows include raw_row_id), sum, avg, min, max, count

group_by dimensions: sector, geography, technology, year, commodity

Filters:
  - sector_codes: list of sector codes, e.g. ["POWER", "INDUSTRY"]
  - geography_codes: list of geography codes, e.g. ["SG"]
  - technology_codes: exact technology codes
  - technology_code_like: fuzzy match (ILIKE %X%), e.g. "SOLAR"
  - year_min / year_max: integer year range
  - limit: max rows (default 1000, hard cap 10000)

Rules:
1. aggregation='raw' keeps raw_row_id for chart cell-tracing (prefer raw)
2. for aggregated statistics pick sum/avg/count etc. and set group_by
3. never invent a metric outside the whitelist
4. when codes/names are uncertain, use technology_code_like
"""


def _plan_to_prompt(plan: list[str], question: str) -> str:
    """Combine the plan and the original question into the SQL Agent prompt."""
    plan_text = "\n".join(f"  {i + 1}. {step}" for i, step in enumerate(plan))
    return (
        f"User question: {question}\n\n"
        f"Execution plan:\n{plan_text}\n\n"
        "Fill in QueryParams to perform the key data query of this plan. "
        "If the plan implies several queries, produce only the most essential one."
    )


# -----------------------------------------------------------------------------
# Node function
# -----------------------------------------------------------------------------
def sql_agent_node(state: AgentState) -> dict:
    """LangGraph node: SQL Agent.

    In:  AgentState (reads messages + plan)
    Out: { sql_params, sql_result, error } (partial state update)
    """
    logger.info("sql_agent_node: start")

    plan = state.get("plan") or []
    if not plan:
        return {
            "sql_params": None,
            "sql_result": None,
            "error": "Plan is empty; cannot derive SQL parameters",
        }

    # Take the original user question (to build the prompt) plus the last few turns:
    # the user may have replied with only "capex", while sector / year filters are in the context.
    from langchain_core.messages import HumanMessage as HMsg

    from app.agents.context import with_context

    user_msgs = [m for m in state["messages"] if isinstance(m, HMsg)]
    question = str(user_msgs[-1].content) if user_msgs else "(unknown)"
    question = with_context(question, state["messages"])

    # ---- Step 1: LLM structured output -> QueryParams ----
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
            params.metric,
            params.aggregation,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("sql_agent_node: structured output failed")
        return {
            "sql_params": None,
            "sql_result": None,
            "error": f"SQL Agent structured output failed: {exc!s}",
        }

    # ---- Step 2: run the run_sql tool ----
    try:
        result_dict: dict[str, Any] = run_sql.invoke(params.model_dump())
        logger.info(
            "sql_agent_node: run_sql ok row_count=%s truncated=%s",
            result_dict.get("row_count"),
            result_dict.get("truncated"),
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
            "error": f"SQL execution failed: {exc!s}",
        }
