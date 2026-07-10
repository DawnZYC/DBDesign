"""(6) recommend_chart — recommend an ECharts spec from data shape and intent.

Pure rule engine, no LLM. The Visualizer Agent calls this tool to get a skeleton, then fills in the dataset.
"""

from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.tools._base import with_observability

ChartType = Literal["line", "bar", "stacked_bar", "grouped_bar", "pie", "sankey"]


class DataShape(BaseModel):
    """Describes the shape of the query result, inferred by the SQL Agent after it gets the rows."""

    n_rows: int
    has_time_axis: bool = Field(
        default=False, description="Whether there is a year/time axis (dimension 'data_year' etc.)"
    )
    n_categories: int = Field(
        default=0, description="Number of non-time categories (e.g. count of sectors / commodities)"
    )
    n_metrics: int = Field(default=1, description="Number of value columns")
    is_aggregated: bool = Field(
        default=False, description="Whether it is an aggregated result (no raw_row_id)"
    )
    metric_unit: str | None = None


class RecommendChartInput(BaseModel):
    data_shape: DataShape
    intent: str | None = Field(
        default=None,
        description="Natural-language intent, e.g. 'compare', 'trend', 'share', 'flow'",
    )


class ChartRecommendation(BaseModel):
    chart_type: ChartType
    rationale: str
    echarts_skeleton: dict[str, Any] = Field(
        ..., description="ECharts option skeleton (no dataset; the frontend fills it)"
    )
    suggested_dimensions: list[str] = Field(
        ..., description="Which columns to use as x-axis / grouping dimensions"
    )


# -----------------------------------------------------------------------------
# Rule engine
# -----------------------------------------------------------------------------
def _decide_chart_type(shape: DataShape, intent_text: str) -> ChartType:
    """Rule priority: intent keywords > data shape.

    NOTE: only the line/bar family is returned. The Visualizer assembles dataset+encode for
    those; pie and sankey need a different data layout it doesn't build yet, so recommending
    them would render a broken chart. Until pie/sankey assembly exists, a "share" question maps
    to a bar chart rather than a misrendered pie. (pie/sankey kept in ChartType for the future.)
    """
    intent_text = (intent_text or "").lower()

    # Prefer time series
    if shape.has_time_axis:
        if shape.n_categories > 1 and any(kw in intent_text for kw in ("stack", "composition")):
            return "stacked_bar"
        return "line"

    # Non-time: compare by category
    if shape.n_categories >= 1 and shape.n_metrics == 1:
        return "bar"
    if shape.n_categories >= 1 and shape.n_metrics > 1:
        return "grouped_bar"

    # Fallback
    return "bar"


def _skeleton_for(chart_type: ChartType, unit: str | None) -> dict[str, Any]:
    """Build the ECharts option skeleton (no data; the frontend binds the dataset)."""
    unit_label = f" ({unit})" if unit else ""
    base: dict[str, Any] = {
        "tooltip": {"trigger": "axis"},
        "grid": {"left": "3%", "right": "5%", "bottom": "8%", "containLabel": True},
        "legend": {"top": 0},
    }
    if chart_type == "line":
        return {
            **base,
            "xAxis": {"type": "category"},
            "yAxis": {"type": "value", "name": unit_label.strip() or "Value"},
            "series": [],  # filled by the caller
        }
    if chart_type in ("bar", "grouped_bar", "stacked_bar"):
        opt = {
            **base,
            "xAxis": {"type": "category"},
            "yAxis": {"type": "value", "name": unit_label.strip() or "Value"},
            "series": [],
        }
        if chart_type == "stacked_bar":
            opt["_stack_hint"] = "true"  # the caller uses this to decide series.stack
        return opt
    if chart_type == "pie":
        return {
            **base,
            "tooltip": {"trigger": "item"},
            "series": [{"type": "pie", "radius": "60%", "data": []}],
        }
    if chart_type == "sankey":
        return {
            "tooltip": {"trigger": "item"},
            "series": [{"type": "sankey", "data": [], "links": []}],
        }
    raise ValueError(f"Unknown chart_type {chart_type}")


def _suggest_dimensions(shape: DataShape, chart_type: ChartType) -> list[str]:
    """Pick x / group columns. The actual column names are filled in by the caller from the SQL result; this only gives the logic."""
    dims = []
    if shape.has_time_axis:
        dims.append("data_year")
    if shape.n_categories >= 1:
        dims.append("category")  # placeholder: sector / commodity etc.
    return dims or ["category"]


@tool("recommend_chart", args_schema=RecommendChartInput)
@with_observability("recommend_chart")
def recommend_chart(
    data_shape: DataShape,
    intent: str | None = None,
) -> dict:
    """Recommend an ECharts visualization spec based on data shape and intent.

    Returns a chart_type (line/bar/sankey/...), an ECharts option skeleton
    (without dataset; the frontend binds rows), and which columns should be
    used as x/group dimensions.
    """
    # After LangChain's invoke -> args_schema.model_validate -> model_dump, a nested
    # Pydantic model comes back as a dict; defensively coerce the type here.
    if isinstance(data_shape, dict):
        data_shape = DataShape(**data_shape)

    chart_type = _decide_chart_type(data_shape, intent or "")
    skeleton = _skeleton_for(chart_type, data_shape.metric_unit)
    dims = _suggest_dimensions(data_shape, chart_type)

    rationale_parts = [f"chart_type={chart_type}"]
    if data_shape.has_time_axis:
        rationale_parts.append("has_time_axis=True -> time series")
    if data_shape.n_categories > 1:
        rationale_parts.append(f"categories={data_shape.n_categories}")
    if data_shape.n_metrics > 1:
        rationale_parts.append(f"metrics={data_shape.n_metrics}")
    if intent:
        rationale_parts.append(f"intent='{intent}'")

    return ChartRecommendation(
        chart_type=chart_type,
        rationale="; ".join(rationale_parts),
        echarts_skeleton=skeleton,
        suggested_dimensions=dims,
    ).model_dump()
