"""Visualizer node — build a complete ECharts spec from the SQL result and the NL intent.

Responsibilities:
  1. Read AgentState.sql_result + the original user question (to infer intent).
  2. Call the recommend_chart tool (rule engine) to get a chart skeleton.
  3. Fill the actual data rows into the ECharts dataset / series to produce a ready-to-render spec.
  4. Write the result into AgentState.chart_spec.

Full ECharts spec format (the frontend calls setOption directly):
  {
    "tooltip": {...},
    "legend": {...},
    "xAxis": {...},
    "yAxis": {...},
    "dataset": { "dimensions": [...], "source": [[...], ...] },
    "series": [{...}, ...],
    "_meta": { "chart_type": "line", "metric": "capex", "unit": "M$" }
  }

Data trimming:
  * The ECharts dataset only carries the first MAX_CHART_ROWS rows (avoids frontend render lag).
  * When exceeded, _meta.truncated is set so the frontend can warn the user.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.agents.state import AgentState
from app.tools.chart import DataShape, RecommendChartInput, recommend_chart

logger = logging.getLogger(__name__)

MAX_CHART_ROWS = 500  # Max rows in the frontend ECharts dataset


# -----------------------------------------------------------------------------
# Internal helpers
# -----------------------------------------------------------------------------
def _infer_data_shape(sql_result: dict[str, Any]) -> DataShape:
    """Infer a DataShape from the QueryResult dict (used by recommend_chart)."""
    rows: list[dict] = sql_result.get("rows", [])
    row_count = sql_result.get("row_count", 0)
    aggregation = sql_result.get("aggregation", "raw")

    # Determine whether there is a time axis
    has_time = any("data_year" in r or "year" in r for r in rows[:5])

    # Determine the number of categories (non-time dimension)
    category_keys = {"sector_code", "technology_code", "geography_code", "commodity_code"}
    n_categories = 0
    if rows:
        present = category_keys.intersection(rows[0].keys())
        if present:
            sample_col = next(iter(present))
            n_categories = len({r.get(sample_col) for r in rows if r.get(sample_col)})

    return DataShape(
        n_rows=row_count,
        has_time_axis=has_time,
        n_categories=max(n_categories, 0),
        n_metrics=1,
        is_aggregated=(aggregation != "raw"),
        metric_unit=sql_result.get("metric_unit"),
    )


def _extract_intent(state: AgentState) -> str:
    """Extract intent keywords from the user message to help recommend_chart decide."""
    user_msgs = [m for m in state["messages"] if isinstance(m, HumanMessage)]
    if not user_msgs:
        return ""
    return str(user_msgs[-1].content)[:200]


def _build_echarts_spec(
    sql_result: dict[str, Any],
    skeleton: dict[str, Any],
    chart_type: str,
    suggested_dimensions: list[str],
) -> dict[str, Any]:
    """Combine the skeleton + SQL rows into a complete ECharts option.

    Strategy:
    - Bind data via ECharts dataset + encode, so the frontend needn't do row/column transforms.
    - The first dimension is fixed as the x axis (time or category); the rest are series.
    - raw_row_id is kept as a hidden dimension (for the chart click-to-trace feature).
    """
    rows: list[dict] = sql_result.get("rows", [])
    sample_rows = rows[:MAX_CHART_ROWS]
    truncated = len(rows) > MAX_CHART_ROWS

    if not sample_rows:
        return {**skeleton, "_meta": {"chart_type": chart_type, "no_data": True}}

    # Decide the dimension order
    all_keys = list(sample_rows[0].keys())

    # x-axis priority: data_year > suggested_dimensions > first non-value/raw_row_id column
    x_candidates = ["data_year"] + suggested_dimensions
    x_col = next((c for c in x_candidates if c in all_keys), None)

    # Category column (used for legend/series grouping)
    category_keys_priority = ["sector_code", "technology_code", "geography_code", "commodity_code"]
    cat_col = next((c for c in category_keys_priority if c in all_keys), None)

    # Value column
    value_col = "value"

    # Build dataset dimensions (raw_row_id goes last, for tracing)
    dimensions: list[str] = []
    if x_col:
        dimensions.append(x_col)
    if cat_col and cat_col != x_col:
        dimensions.append(cat_col)
    if value_col in all_keys:
        dimensions.append(value_col)
    # Append the hidden dimension (raw_row_id for frontend click-to-trace)
    if "raw_row_id" in all_keys and "raw_row_id" not in dimensions:
        dimensions.append("raw_row_id")

    # Add any missing columns (keep the data complete)
    for k in all_keys:
        if k not in dimensions:
            dimensions.append(k)

    # Build the dataset source (**pure data rows**, no header).
    # Note: when dimensions are given explicitly, ECharts does not treat source[0] as a header,
    # so we must NOT push dimensions into source as the first row (it would render as a "first data point").
    source: list[list[Any]] = []
    for row in sample_rows:
        source.append([row.get(d) for d in dimensions])

    # Build the dataset list + series (grouped by cat_col, or a single series).
    # For multi-series, each category needs its own filter dataset, otherwise ECharts would
    # draw N identical lines from the same data — use dataset.transform=filter to slice client-side.
    datasets: list[dict[str, Any]] = [
        {"dimensions": dimensions, "source": source}  # index=0: raw full data
    ]
    series: list[dict[str, Any]] = []

    if cat_col and cat_col in dimensions:
        # Multi-series: one filter dataset + one series referencing it per category value
        categories = list(
            dict.fromkeys(r.get(cat_col) for r in sample_rows if r.get(cat_col) is not None)
        )
        for cat in categories:
            # Append a transform dataset: filter the rows of this category from raw dataset(0)
            datasets.append(
                {
                    "transform": {
                        "type": "filter",
                        "config": {"dimension": cat_col, "value": cat},
                    },
                }
            )
            serie: dict[str, Any] = {
                "type": chart_type if chart_type in ("line", "bar") else "line",
                "name": str(cat),
                "datasetIndex": len(datasets) - 1,  # points to the filter dataset just appended
                "encode": {"x": x_col or dimensions[0], "y": value_col},
            }
            if skeleton.get("_stack_hint"):
                serie["stack"] = "total"
            series.append(serie)
    else:
        # Single series
        series.append(
            {
                "type": chart_type if chart_type in ("line", "bar", "pie") else "line",
                "name": sql_result.get("metric", "value"),
                "datasetIndex": 0,
                "encode": {
                    "x": x_col or (dimensions[0] if dimensions else "x"),
                    "y": value_col,
                },
            }
        )

    # Drop _stack_hint from the skeleton (the frontend doesn't need it)
    spec = {k: v for k, v in skeleton.items() if k != "_stack_hint"}
    # ECharts supports dataset as a list (required when using transforms)
    spec["dataset"] = datasets if len(datasets) > 1 else datasets[0]
    spec["series"] = series
    spec["_meta"] = {
        "chart_type": chart_type,
        "metric": sql_result.get("metric"),
        "unit": sql_result.get("metric_unit"),
        "row_count": len(rows),  # total SQL rows (including truncated part)
        "chart_row_count": len(sample_rows),  # rows actually rendered in the chart
        "truncated": truncated,
    }
    return spec


# -----------------------------------------------------------------------------
# Node function
# -----------------------------------------------------------------------------
def visualizer_node(state: AgentState) -> dict:
    """LangGraph node: Visualizer.

    In:  AgentState (reads sql_result + messages)
    Out: { chart_spec, error } (partial state update)
    """
    logger.info("visualizer_node: start")

    sql_result = state.get("sql_result")
    if not sql_result or not sql_result.get("rows"):
        logger.info("visualizer_node: no data rows, skipping chart generation")
        return {"chart_spec": None, "error": None}

    intent = _extract_intent(state)
    data_shape = _infer_data_shape(sql_result)

    # ---- Call the recommend_chart rule engine ----
    try:
        rec_input = RecommendChartInput(data_shape=data_shape, intent=intent or None)
        rec_result: dict[str, Any] = recommend_chart.invoke(rec_input.model_dump())
        chart_type: str = rec_result["chart_type"]
        skeleton: dict[str, Any] = rec_result["echarts_skeleton"]
        suggested_dims: list[str] = rec_result.get("suggested_dimensions", [])
        logger.info("visualizer_node: chart_type=%s", chart_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("visualizer_node: recommend_chart failed")
        return {"chart_spec": None, "error": f"Chart recommendation failed: {exc!s}"}

    # ---- Assemble the complete ECharts spec ----
    try:
        spec = _build_echarts_spec(sql_result, skeleton, chart_type, suggested_dims)
        # dataset may now be a list (multiple transforms) or a dict (single dataset); take index=0 source length
        ds = spec.get("dataset", {})
        raw_ds = ds[0] if isinstance(ds, list) else ds
        ds_rows = len(raw_ds.get("source", [])) if isinstance(raw_ds, dict) else 0
        logger.info(
            "visualizer_node: spec built, series_count=%d dataset_rows=%d",
            len(spec.get("series", [])),
            ds_rows,
        )
        return {"chart_spec": spec, "error": None}
    except Exception as exc:  # noqa: BLE001
        logger.exception("visualizer_node: spec assembly failed")
        return {"chart_spec": None, "error": f"Chart generation failed: {exc!s}"}
