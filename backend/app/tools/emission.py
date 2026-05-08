"""④ lookup_emission_factor — 查询某技术在某年的排放因子。

精确年份没有时回退到最近一年（带 emission_factor 的）。
"""
from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.tools._base import with_observability


class EmissionFactorInput(BaseModel):
    technology_code: str = Field(..., description="技术代码（如 PWRNGACCF01）")
    year: int = Field(..., description="目标年份")
    geography_code: str = Field(default="SG")


class EmissionFactorHit(BaseModel):
    technology_code: str
    matched_year: int
    requested_year: int
    is_exact_year: bool
    emission_factor: float | None
    emission_factor_unit: str | None
    raw_row_id: int | None = Field(default=None, description="原始 Excel 行 ID（M4 反查用）")


class EmissionFactorResponse(BaseModel):
    found: bool
    hit: EmissionFactorHit | None = None
    message: str | None = None


@tool("lookup_emission_factor", args_schema=EmissionFactorInput)
@with_observability("lookup_emission_factor")
def lookup_emission_factor(
    technology_code: str, year: int, geography_code: str = "SG"
) -> dict:
    """Look up the emission factor for a given technology code and year.

    Returns the exact year if available; otherwise falls back to the
    nearest year (preferring earlier) that has a non-null emission factor.
    """
    db = SessionLocal()
    try:
        # 拿到 technology_id
        tech = db.scalar(
            select(models.TechnologyProcess)
            .join(models.Geography,
                  models.Geography.geography_id == models.TechnologyProcess.geography_id)
            .where(
                models.TechnologyProcess.technology_code == technology_code,
                models.Geography.geography_code == geography_code,
            )
        )
        if tech is None:
            return EmissionFactorResponse(
                found=False,
                message=f"技术 '{technology_code}' 在 geography={geography_code} 不存在。",
            ).model_dump()

        # 收集该技术下所有年份及其 emission_factor
        rows = db.execute(
            select(
                models.TechnologyYear.data_year,
                models.TechnologyYear.raw_row_id,
                models.TechnologyYearEcoteaParameter.emission_factor,
                models.TechnologyYearEcoteaParameter.emission_factor_unit,
            )
            .join(
                models.TechnologyYearEcoteaParameter,
                models.TechnologyYearEcoteaParameter.technology_year_id
                == models.TechnologyYear.technology_year_id,
                isouter=True,
            )
            .where(models.TechnologyYear.technology_id == tech.technology_id)
            .order_by(models.TechnologyYear.data_year)
        ).all()

        candidates = [
            r for r in rows if r.emission_factor is not None
        ]
        if not candidates:
            return EmissionFactorResponse(
                found=False,
                message=f"技术 '{technology_code}' 没有任何 emission_factor 记录。",
            ).model_dump()

        # 找精确年
        exact = next((r for r in candidates if r.data_year == year), None)
        if exact:
            return EmissionFactorResponse(
                found=True,
                hit=EmissionFactorHit(
                    technology_code=technology_code,
                    matched_year=int(exact.data_year),
                    requested_year=year,
                    is_exact_year=True,
                    emission_factor=float(exact.emission_factor),
                    emission_factor_unit=exact.emission_factor_unit,
                    raw_row_id=exact.raw_row_id,
                ),
            ).model_dump()

        # 没精确，找最近（绝对值差最小，相同时取较早）
        best = min(candidates, key=lambda r: (abs(int(r.data_year) - year), int(r.data_year)))
        return EmissionFactorResponse(
            found=True,
            hit=EmissionFactorHit(
                technology_code=technology_code,
                matched_year=int(best.data_year),
                requested_year=year,
                is_exact_year=False,
                emission_factor=float(best.emission_factor),
                emission_factor_unit=best.emission_factor_unit,
                raw_row_id=best.raw_row_id,
            ),
            message=f"年份 {year} 无记录；回退到最近的 {best.data_year}。",
        ).model_dump()
    finally:
        db.close()
