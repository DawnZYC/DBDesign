"""⑥ recommend_chart 单测（纯规则，无 DB）。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.tools.chart import recommend_chart  # noqa: E402


def _call(shape: dict, intent: str | None = None) -> dict:
    return recommend_chart.invoke({"data_shape": shape, "intent": intent})


def test_time_series_yields_line():
    out = _call({
        "n_rows": 50, "has_time_axis": True,
        "n_categories": 1, "n_metrics": 1, "is_aggregated": False,
        "metric_unit": "PJ",
    })
    assert out["chart_type"] == "line"
    assert "data_year" in out["suggested_dimensions"]


def test_categorical_single_metric_yields_bar():
    out = _call({
        "n_rows": 10, "has_time_axis": False,
        "n_categories": 5, "n_metrics": 1, "is_aggregated": True,
        "metric_unit": None,
    })
    assert out["chart_type"] == "bar"


def test_categorical_multi_metric_yields_grouped_bar():
    out = _call({
        "n_rows": 10, "has_time_axis": False,
        "n_categories": 5, "n_metrics": 3, "is_aggregated": True,
    })
    assert out["chart_type"] == "grouped_bar"


def test_intent_share_yields_pie():
    out = _call(
        {"n_rows": 5, "has_time_axis": False, "n_categories": 5, "n_metrics": 1},
        intent="占比分析",
    )
    assert out["chart_type"] == "pie"


def test_intent_flow_yields_sankey():
    out = _call(
        {"n_rows": 20, "has_time_axis": False, "n_categories": 10, "n_metrics": 1},
        intent="energy flow diagram",
    )
    assert out["chart_type"] == "sankey"


def test_stacked_bar_when_intent_says_so():
    out = _call(
        {
            "n_rows": 50, "has_time_axis": True,
            "n_categories": 4, "n_metrics": 1,
        },
        intent="按部门堆叠",
    )
    assert out["chart_type"] == "stacked_bar"


def test_skeleton_has_required_fields():
    out = _call({
        "n_rows": 10, "has_time_axis": True,
        "n_categories": 1, "n_metrics": 1, "metric_unit": "PJ",
    })
    skel = out["echarts_skeleton"]
    # 折线图骨架应该有 xAxis/yAxis
    assert "xAxis" in skel
    assert "yAxis" in skel
    # 单位应入轴名
    assert "PJ" in skel["yAxis"]["name"]
