"""③ run_sql 单测（依赖测试 DB）。"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests._db_fixture import setup_test_db  # noqa: E402

setup_test_db()

import pytest  # noqa: E402

from app.tools.sql_runner import (  # noqa: E402
    METRICS,
    QueryParams,
    run_sql,
)


def _call(**kwargs) -> dict:
    return run_sql.invoke(kwargs)


# -----------------------------------------------------------------------------
# Metric 注册表
# -----------------------------------------------------------------------------
def test_metric_registry_complete():
    """注册表应覆盖所有重要指标。"""
    expected = {
        "capex", "fixed_opex", "variable_opex", "emission_factor",
        "tax_cost", "subsidy_cost",
        "efficiency_value", "technology_efficiency",
        "heat_rate", "capacity_to_activity_factor",
        "capacity", "commodity_demand_value",
    }
    assert expected.issubset(set(METRICS.keys()))


# -----------------------------------------------------------------------------
# raw 模式
# -----------------------------------------------------------------------------
def test_capex_raw_returns_rows_with_raw_row_id():
    out = _call(metric="capex", aggregation="raw", sector_codes=["POWER"])
    assert out["row_count"] >= 1
    for row in out["rows"]:
        # 每行必须带 raw_row_id 给 M4 反查（即使是 None 也应该有这个键）
        assert "raw_row_id" in row
        assert "value" in row
        assert "data_year" in row
        assert "technology_code" in row


def test_filter_year_range():
    out = _call(metric="capex", year_min=2030, year_max=2040)
    years = [r["data_year"] for r in out["rows"]]
    assert all(2030 <= y <= 2040 for y in years)


def test_filter_by_technology_code():
    out = _call(metric="capex", technology_codes=["PWRNGACCF01"])
    codes = {r["technology_code"] for r in out["rows"]}
    assert codes == {"PWRNGACCF01"}


def test_filter_by_technology_code_like():
    out = _call(metric="capex", technology_code_like="SOL")
    codes = {r["technology_code"] for r in out["rows"]}
    assert all("SOL" in c for c in codes)


def test_unit_field_returned_for_capex():
    out = _call(metric="capex")
    if out["rows"]:
        assert "unit" in out["rows"][0]
        assert out["metric_unit"] == "GW"


# -----------------------------------------------------------------------------
# 聚合
# -----------------------------------------------------------------------------
def test_aggregation_sum_by_sector():
    out = _call(
        metric="capex", aggregation="sum",
        group_by=["sector"],
    )
    assert out["aggregation"] == "sum"
    # 至少有 1 个 sector group
    assert out["row_count"] >= 1
    for row in out["rows"]:
        assert "sector_code" in row
        assert "value" in row
        # 聚合行不应再带 raw_row_id
        assert "raw_row_id" not in row


def test_aggregation_avg_by_year():
    out = _call(
        metric="capex", aggregation="avg",
        group_by=["year"],
    )
    for row in out["rows"]:
        assert "data_year" in row


def test_count_aggregation():
    out = _call(metric="emission_factor", aggregation="count", group_by=["sector"])
    for row in out["rows"]:
        assert isinstance(row["value"], int)
        assert row["value"] > 0


# -----------------------------------------------------------------------------
# 安全
# -----------------------------------------------------------------------------
def test_unknown_metric_rejected():
    """metric 不在白名单 → Pydantic 验证拒绝。"""
    with pytest.raises(Exception):
        _call(metric="DROP TABLE users; --")


def test_limit_enforced():
    out = _call(metric="capex", limit=2)
    assert out["row_count"] <= 2


def test_limit_max_clamp():
    """超过 MAX_LIMIT 不应 crash，会被 Pydantic 拒绝。"""
    with pytest.raises(Exception):
        _call(metric="capex", limit=99999999)


# -----------------------------------------------------------------------------
# QueryParams normalization
# -----------------------------------------------------------------------------
def test_sector_codes_uppercased():
    p = QueryParams(metric="capex", sector_codes=["power", " industry "])
    assert p.sector_codes == ["POWER", "INDUSTRY"]


def test_empty_filter_lists_normalize_to_none():
    p = QueryParams(metric="capex", sector_codes=["", "  "])
    assert p.sector_codes is None
