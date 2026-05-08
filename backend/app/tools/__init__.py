"""Function-Calling 工具集（M2）。

每个工具 = Pydantic 入参 + 纯 Python 实现 + LangChain Tool 包装。
直接调用工具用 `tool.invoke({...})`；Agent 集成走 LangChain ToolNode。

ALL_TOOLS 是给 Agent 注册用的列表，后续 LangGraph 直接引用。
"""
from app.tools.chart import recommend_chart
from app.tools.emission import lookup_emission_factor
from app.tools.forecast import forecast_trend
from app.tools.sql_runner import run_sql
from app.tools.terminology import lookup_terminology
from app.tools.unit_convert import convert_unit

# Agent 注册表 — 顺序无关
ALL_TOOLS = [
    lookup_terminology,
    convert_unit,
    run_sql,
    lookup_emission_factor,
    forecast_trend,
    recommend_chart,
]

__all__ = [
    "ALL_TOOLS",
    "convert_unit",
    "forecast_trend",
    "lookup_emission_factor",
    "lookup_terminology",
    "recommend_chart",
    "run_sql",
]
