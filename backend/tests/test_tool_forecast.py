"""(5) forecast_trend unit tests (pure computation, no DB)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from app.tools.forecast import forecast_trend  # noqa: E402


def _call(series, horizon=10, method="linear"):
    return forecast_trend.invoke({"series": series, "horizon": horizon, "method": method})


def test_linear_perfect_fit():
    """Perfectly linear data: R² should be close to 1."""
    series = [{"year": 2018 + i, "value": 100 + i * 10} for i in range(5)]
    out = _call(series, horizon=3, method="linear")
    assert out["history_count"] == 5
    assert len(out["forecast"]) == 3
    assert out["r_squared"] > 0.999
    # The next year should be 100 + 5*10 = 150
    assert abs(out["forecast"][0]["value"] - 150) < 0.01
    assert out["forecast"][0]["year"] == 2023


def test_horizon_extends_correctly():
    series = [{"year": 2020 + i, "value": float(i)} for i in range(4)]
    out = _call(series, horizon=5)
    years = [p["year"] for p in out["forecast"]]
    assert years == [2024, 2025, 2026, 2027, 2028]


def test_too_few_points_rejected():
    series = [{"year": 2018, "value": 1.0}, {"year": 2019, "value": 2.0}]
    with pytest.raises((ValueError, Exception)):
        _call(series)


def test_poly2_method():
    """Quadratic curve: poly2 fit R² should be close to 1."""
    # y = (x-2020)^2
    series = [{"year": 2018 + i, "value": (i - 2) ** 2} for i in range(5)]
    out = _call(series, method="poly2", horizon=2)
    assert out["method"] == "poly2"
    assert out["r_squared"] > 0.99


def test_unsorted_input_handled():
    """Out-of-order input should be auto-sorted before fitting."""
    series = [
        {"year": 2022, "value": 200},
        {"year": 2018, "value": 100},
        {"year": 2020, "value": 150},
    ]
    out = _call(series, horizon=2)
    # Should not crash
    assert out["history_count"] == 3
    assert len(out["forecast"]) == 2
