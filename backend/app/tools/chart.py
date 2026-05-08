"""⑥ recommend_chart — 根据数据形状和意图推荐 ECharts spec。

纯规则引擎，无 LLM。Visualizer Agent 调用本工具拿一个骨架，再填充 dataset。
"""
from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.tools._base import with_observability

ChartType = Literal["line", "bar", "stacked_bar", "grouped_bar", "pie", "sankey"]


class DataShape(BaseModel):
    """描述查询结果的形状，由 SQL Agent 在拿到 rows 后推断出来传进来。"""

    n_rows: int
    has_time_axis: bool = Field(
        default=False, description="是否有按年/时间的轴（dimension 'data_year' 等）"
    )
    n_categories: int = Field(default=0, description="非时间分类数（譬如 sector / commodity 数量）")
    n_metrics: int = Field(default=1, description="数值列数量")
    is_aggregated: bool = Field(default=False, description="是否为聚合结果（无 raw_row_id）")
    metric_unit: str | None = None


class RecommendChartInput(BaseModel):
    data_shape: DataShape
    intent: str | None = Field(
        default=None, description="自然语言意图，如「对比」「趋势」「占比」「流向」"
    )


class ChartRecommendation(BaseModel):
    chart_type: ChartType
    rationale: str
    echarts_skeleton: dict[str, Any] = Field(
        ..., description="ECharts option 骨架（不含 dataset，前端填）"
    )
    suggested_dimensions: list[str] = Field(
        ..., description="建议哪些列作为 x 轴 / 分组维度"
    )


# -----------------------------------------------------------------------------
# 规则引擎
# -----------------------------------------------------------------------------
def _decide_chart_type(shape: DataShape, intent_text: str) -> ChartType:
    """规则优先级：意图关键词 > 数据形状。"""
    intent_text = (intent_text or "").lower()

    if any(kw in intent_text for kw in ("flow", "流向", "桑基", "sankey")):
        return "sankey"
    if any(kw in intent_text for kw in ("占比", "share", "饼", "pie")):
        return "pie"

    # 时间序列优先
    if shape.has_time_axis:
        if shape.n_categories > 1 and any(
            kw in intent_text for kw in ("堆叠", "stack", "组成")
        ):
            return "stacked_bar"
        return "line"

    # 非时间：按分类对比
    if shape.n_categories >= 1 and shape.n_metrics == 1:
        return "bar"
    if shape.n_categories >= 1 and shape.n_metrics > 1:
        return "grouped_bar"

    # 兜底
    return "bar"


def _skeleton_for(chart_type: ChartType, unit: str | None) -> dict[str, Any]:
    """构造 ECharts option 骨架（不含数据，前端绑 dataset）。"""
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
            "yAxis": {"type": "value", "name": unit_label.strip() or "值"},
            "series": [],  # 由调用方填
        }
    if chart_type in ("bar", "grouped_bar", "stacked_bar"):
        opt = {
            **base,
            "xAxis": {"type": "category"},
            "yAxis": {"type": "value", "name": unit_label.strip() or "值"},
            "series": [],
        }
        if chart_type == "stacked_bar":
            opt["_stack_hint"] = "true"  # 调用方据此决定 series.stack
        return opt
    if chart_type == "pie":
        return {
            **base,
            "tooltip": {"trigger": "item"},
            "series": [
                {"type": "pie", "radius": "60%", "data": []}
            ],
        }
    if chart_type == "sankey":
        return {
            "tooltip": {"trigger": "item"},
            "series": [
                {"type": "sankey", "data": [], "links": []}
            ],
        }
    raise ValueError(f"Unknown chart_type {chart_type}")


def _suggest_dimensions(shape: DataShape, chart_type: ChartType) -> list[str]:
    """挑选 x / group 列。具体列名由调用方根据 SQL 结果填实，这里只给逻辑。"""
    dims = []
    if shape.has_time_axis:
        dims.append("data_year")
    if shape.n_categories >= 1:
        dims.append("category")  # 占位：sector / commodity 等
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
    chart_type = _decide_chart_type(data_shape, intent or "")
    skeleton = _skeleton_for(chart_type, data_shape.metric_unit)
    dims = _suggest_dimensions(data_shape, chart_type)

    rationale_parts = [f"chart_type={chart_type}"]
    if data_shape.has_time_axis:
        rationale_parts.append("has_time_axis=True → 时间序列")
    if data_shape.n_categories > 1:
        rationale_parts.append(f"分类={data_shape.n_categories}")
    if data_shape.n_metrics > 1:
        rationale_parts.append(f"指标={data_shape.n_metrics}")
    if intent:
        rationale_parts.append(f"intent='{intent}'")

    return ChartRecommendation(
        chart_type=chart_type,
        rationale="; ".join(rationale_parts),
        echarts_skeleton=skeleton,
        suggested_dimensions=dims,
    ).model_dump()
