"""Function-calling tool set (M2).

Each tool = Pydantic input + pure-Python implementation + LangChain Tool wrapper.
Call a tool directly with `tool.invoke({...})`; Agent integration goes through LangChain ToolNode.

ALL_TOOLS is the list used to register tools with the Agent, referenced directly by LangGraph.
"""

from app.tools.chart import recommend_chart
from app.tools.emission import lookup_emission_factor
from app.tools.forecast import forecast_trend
from app.tools.sql_runner import run_sql
from app.tools.terminology import lookup_terminology
from app.tools.unit_convert import convert_unit

# Agent registry — order-independent
ALL_TOOLS = [
    lookup_terminology,
    convert_unit,
    run_sql,
    lookup_emission_factor,
    forecast_trend,
    recommend_chart,
]

# Tools the LLM picks via real function-calling in the Tool Agent node (M3+).
# run_sql is excluded (it goes through the structured SQL Agent for injection safety);
# recommend_chart is excluded (it is a rule engine called directly by the Visualizer).
AUX_TOOLS = [
    lookup_terminology,
    convert_unit,
    lookup_emission_factor,
    forecast_trend,
]

__all__ = [
    "ALL_TOOLS",
    "AUX_TOOLS",
    "convert_unit",
    "forecast_trend",
    "lookup_emission_factor",
    "lookup_terminology",
    "recommend_chart",
    "run_sql",
]
