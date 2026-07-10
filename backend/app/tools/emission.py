"""(4) lookup_emission_factor — look up a technology's emission factor for a given year.

When the exact year is missing, fall back to the nearest year (that has an emission_factor).
"""

from __future__ import annotations

from langchain_core.tools import tool
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import models
from app.database import SessionLocal
from app.tools._base import with_observability


class EmissionFactorInput(BaseModel):
    technology_code: str = Field(..., description="Technology code (e.g. NGCC01)")
    year: int = Field(..., description="Target year")
    geography_code: str = Field(default="SG")


class EmissionFactorHit(BaseModel):
    technology_code: str
    matched_year: int
    requested_year: int
    is_exact_year: bool
    emission_factor: float | None
    emission_factor_unit: str | None
    raw_row_id: int | None = Field(default=None, description="Source Excel row ID (for M4 trace-back)")


class EmissionFactorResponse(BaseModel):
    found: bool
    hit: EmissionFactorHit | None = None
    message: str | None = None


@tool("lookup_emission_factor", args_schema=EmissionFactorInput)
@with_observability("lookup_emission_factor")
def lookup_emission_factor(technology_code: str, year: int, geography_code: str = "SG") -> dict:
    """Look up the emission factor for a given technology code and year.

    Returns the exact year if available; otherwise falls back to the
    nearest year (preferring earlier) that has a non-null emission factor.
    """
    db = SessionLocal()
    try:
        # Get the technology_id
        tech = db.scalar(
            select(models.TechnologyProcess)
            .join(
                models.Geography,
                models.Geography.geography_id == models.TechnologyProcess.geography_id,
            )
            .where(
                models.TechnologyProcess.technology_code == technology_code,
                models.Geography.geography_code == geography_code,
            )
        )
        if tech is None:
            return EmissionFactorResponse(
                found=False,
                message=f"Technology '{technology_code}' does not exist for geography={geography_code}.",
            ).model_dump()

        # Collect all years and their emission_factor for this technology
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

        candidates = [r for r in rows if r.emission_factor is not None]
        if not candidates:
            return EmissionFactorResponse(
                found=False,
                message=f"Technology '{technology_code}' has no emission_factor records.",
            ).model_dump()

        # Find the exact year
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

        # No exact match: find the nearest (smallest absolute diff, ties prefer earlier)
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
            message=f"No record for year {year}; fell back to the nearest year {best.data_year}.",
        ).model_dump()
    finally:
        db.close()
