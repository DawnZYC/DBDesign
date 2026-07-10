"""(5) forecast_trend — simple time-series extrapolation.

Strategy:
  - linear (default): numpy.polyfit deg=1
  - poly2           : deg=2 quadratic fit
  - fewer than 3 data points -> reject
  - output the next N years (horizon), one (year, value) pair per year, with R²
"""

from __future__ import annotations

from typing import Literal

import numpy as np
from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from app.tools._base import with_observability


class SeriesPoint(BaseModel):
    year: int
    value: float


class ForecastInput(BaseModel):
    series: list[SeriesPoint] = Field(..., description="Historical time series (by year)")
    horizon: int = Field(default=10, ge=1, le=80, description="How many years to forecast")
    method: Literal["linear", "poly2"] = "linear"

    @field_validator("series")
    @classmethod
    def _at_least_three_points(cls, v: list[SeriesPoint]) -> list[SeriesPoint]:
        if len(v) < 3:
            raise ValueError("At least 3 historical data points are required to extrapolate")
        return v


class ForecastPoint(BaseModel):
    year: int
    value: float


class ForecastResult(BaseModel):
    method: str
    history_count: int
    forecast: list[ForecastPoint]
    r_squared: float = Field(..., description="Goodness of fit (closer to 1 is better)")
    coefficients: list[float] = Field(..., description="Polynomial coefficients (highest to lowest degree)")


@tool("forecast_trend", args_schema=ForecastInput)
@with_observability("forecast_trend")
def forecast_trend(
    series: list[SeriesPoint],
    horizon: int = 10,
    method: Literal["linear", "poly2"] = "linear",
) -> dict:
    """Project a yearly time series into the future using polyfit.

    Use 'linear' (deg=1) by default; 'poly2' (deg=2) for clearly curving series.
    Returns forecasted (year, value) pairs plus R² to indicate fit quality.
    """
    # 1) Convert to numpy & sort
    pts = sorted([(p.year, p.value) for p in series], key=lambda x: x[0])
    xs = np.array([p[0] for p in pts], dtype=float)
    ys = np.array([p[1] for p in pts], dtype=float)

    # 2) Fit
    deg = 1 if method == "linear" else 2
    coeffs = np.polyfit(xs, ys, deg=deg)

    # R²
    y_hat = np.polyval(coeffs, xs)
    ss_res = float(np.sum((ys - y_hat) ** 2))
    ss_tot = float(np.sum((ys - ys.mean()) ** 2))
    r2 = 0.0 if ss_tot == 0 else 1 - ss_res / ss_tot

    # 3) Extrapolate
    last_year = int(xs[-1])
    future_years = np.arange(last_year + 1, last_year + 1 + horizon, dtype=float)
    future_vals = np.polyval(coeffs, future_years)

    return ForecastResult(
        method=method,
        history_count=len(pts),
        forecast=[
            ForecastPoint(year=int(y), value=float(v))
            for y, v in zip(future_years, future_vals, strict=False)
        ],
        r_squared=float(r2),
        coefficients=[float(c) for c in coeffs],
    ).model_dump()
