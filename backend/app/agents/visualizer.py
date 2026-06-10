"""Visualizer 节点 — 根据 SQL 结果和自然语言意图生成完整 ECharts spec。

职责：
  1. 读取 AgentState.sql_result + 用户原始问题（推断意图）
  2. 调用 recommend_chart 工具（规则引擎）拿图表骨架
  3. 把实际数据行填入 ECharts dataset / series，生成可直接渲染的完整 spec
  4. 结果写入 AgentState.chart_spec

ECharts spec 完整格式（前端直接 setOption）：
  {
    "tooltip": {...},
    "legend": {...},
    "xAxis": {...},
    "yAxis": {...},
    "dataset": { "dimensions": [...], "source": [[...], ...] },
    "series": [{...}, ...],
    "_meta": { "chart_type": "line", "metric": "capex", "unit": "M$" }
  }

数据裁剪：
  * ECharts dataset 只传前 MAX_CHART_ROWS 行（避免前端渲染卡顿）
  * 超出时在 _meta.truncated 标记，让前端提示用户
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage

from app.agents.state import AgentState
from app.tools.chart import DataShape, RecommendChartInput, recommend_chart

logger = logging.getLogger(__name__)

MAX_CHART_ROWS = 500   # 前端 ECharts dataset 最大行数


# -----------------------------------------------------------------------------
# 内部辅助
# -----------------------------------------------------------------------------
def _infer_data_shape(sql_result: dict[str, Any]) -> DataShape:
    """从 QueryResult dict 推断 DataShape（供 recommend_chart 使用）。"""
    rows: list[dict] = sql_result.get("rows", [])
    row_count = sql_result.get("row_count", 0)
    aggregation = sql_result.get("aggregation", "raw")

    # 判断是否有时间轴
    has_time = any("data_year" in r or "year" in r for r in rows[:5])

    # 判断分类数（非时间 dimension）
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
    """从用户消息中提取意图关键词，传给 recommend_chart 辅助决策。"""
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
    """把骨架 + SQL 行数据组合成完整 ECharts option。

    策略：
    - 用 ECharts dataset + encode 方式绑定数据，前端不需要自己处理行列转换
    - dimensions 第一列固定为 x 轴（时间或分类），其余为 series
    - raw_row_id 作为隐藏维度保留（前端图表点击事件反查用）
    """
    rows: list[dict] = sql_result.get("rows", [])
    sample_rows = rows[:MAX_CHART_ROWS]
    truncated = len(rows) > MAX_CHART_ROWS

    if not sample_rows:
        return {**skeleton, "_meta": {"chart_type": chart_type, "no_data": True}}

    # 决定 dimensions 顺序
    all_keys = list(sample_rows[0].keys())

    # x 轴优先顺序：data_year > suggested_dimensions > 第一个非 value/raw_row_id 列
    x_candidates = ["data_year"] + suggested_dimensions
    x_col = next((c for c in x_candidates if c in all_keys), None)

    # 分类列（用于 legend/series 分组）
    category_keys_priority = [
        "sector_code", "technology_code", "geography_code", "commodity_code"
    ]
    cat_col = next((c for c in category_keys_priority if c in all_keys), None)

    # 数值列
    value_col = "value"

    # 构造 dataset dimensions（raw_row_id 放最后，用于反查）
    dimensions: list[str] = []
    if x_col:
        dimensions.append(x_col)
    if cat_col and cat_col != x_col:
        dimensions.append(cat_col)
    if value_col in all_keys:
        dimensions.append(value_col)
    # 附加隐藏维度（raw_row_id 供前端点击反查）
    if "raw_row_id" in all_keys and "raw_row_id" not in dimensions:
        dimensions.append("raw_row_id")

    # 补上遗漏列（保证数据完整）
    for k in all_keys:
        if k not in dimensions:
            dimensions.append(k)

    # 构造 dataset source（**纯数据行**，不含 header）
    # 注意：当显式提供 dimensions 时，ECharts 不会把 source[0] 当成表头，
    # 所以这里千万不能把 dimensions 再塞进 source 当首行（会被画成"第一个数据点"）。
    source: list[list[Any]] = []
    for row in sample_rows:
        source.append([row.get(d) for d in dimensions])

    # 构造 dataset 列表 + series（按 cat_col 分组，或单 series）
    # 多 series 时，每个 category 需要自己的 filter dataset，否则 ECharts 会
    # 用同一份数据画 N 条相同的线 —— 用 dataset.transform=filter 在客户端切片。
    datasets: list[dict[str, Any]] = [
        {"dimensions": dimensions, "source": source}   # index=0：原始全量数据
    ]
    series: list[dict[str, Any]] = []

    if cat_col and cat_col in dimensions:
        # 多 series：每个分类值生成一个 filter dataset + 一条 series 引用它
        categories = list(dict.fromkeys(
            r.get(cat_col) for r in sample_rows if r.get(cat_col) is not None
        ))
        for cat in categories:
            # 追加一个 transform dataset：从原始 dataset(0) 过滤出该 category 的行
            datasets.append({
                "transform": {
                    "type": "filter",
                    "config": {"dimension": cat_col, "value": cat},
                },
            })
            serie: dict[str, Any] = {
                "type": chart_type if chart_type in ("line", "bar") else "line",
                "name": str(cat),
                "datasetIndex": len(datasets) - 1,   # 指向刚追加的 filter dataset
                "encode": {"x": x_col or dimensions[0], "y": value_col},
            }
            if skeleton.get("_stack_hint"):
                serie["stack"] = "total"
            series.append(serie)
    else:
        # 单 series
        series.append({
            "type": chart_type if chart_type in ("line", "bar", "pie") else "line",
            "name": sql_result.get("metric", "value"),
            "datasetIndex": 0,
            "encode": {
                "x": x_col or (dimensions[0] if dimensions else "x"),
                "y": value_col,
            },
        })

    # 移除骨架中的 _stack_hint（前端不需要）
    spec = {k: v for k, v in skeleton.items() if k != "_stack_hint"}
    # ECharts 支持 dataset 为 list（带 transform 时必须这样写）
    spec["dataset"] = datasets if len(datasets) > 1 else datasets[0]
    spec["series"] = series
    spec["_meta"] = {
        "chart_type": chart_type,
        "metric": sql_result.get("metric"),
        "unit": sql_result.get("metric_unit"),
        "row_count": len(rows),           # SQL 总行数（含被截断部分）
        "chart_row_count": len(sample_rows),  # 图表实际渲染行数
        "truncated": truncated,
    }
    return spec


# -----------------------------------------------------------------------------
# 节点函数
# -----------------------------------------------------------------------------
def visualizer_node(state: AgentState) -> dict:
    """LangGraph 节点：Visualizer。

    入参：AgentState（取 sql_result + messages）
    出参：{ chart_spec, error }（partial state update）
    """
    logger.info("visualizer_node: start")

    sql_result = state.get("sql_result")
    if not sql_result or not sql_result.get("rows"):
        logger.info("visualizer_node: no data rows, skipping chart generation")
        return {"chart_spec": None, "error": None}

    intent = _extract_intent(state)
    data_shape = _infer_data_shape(sql_result)

    # ---- 调用 recommend_chart 规则引擎 ----
    try:
        rec_input = RecommendChartInput(data_shape=data_shape, intent=intent or None)
        rec_result: dict[str, Any] = recommend_chart.invoke(rec_input.model_dump())
        chart_type: str = rec_result["chart_type"]
        skeleton: dict[str, Any] = rec_result["echarts_skeleton"]
        suggested_dims: list[str] = rec_result.get("suggested_dimensions", [])
        logger.info("visualizer_node: chart_type=%s", chart_type)
    except Exception as exc:  # noqa: BLE001
        logger.exception("visualizer_node: recommend_chart failed")
        return {"chart_spec": None, "error": f"图表推荐失败: {exc!s}"}

    # ---- 组装完整 ECharts spec ----
    try:
        spec = _build_echarts_spec(sql_result, skeleton, chart_type, suggested_dims)
        # dataset 现在可能是 list（多 transform）或 dict（单 dataset），统一取 index=0 的 source 长度
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
        return {"chart_spec": None, "error": f"图表生成失败: {exc!s}"}
