"""Manual emission-factor entry.

Emission factors normally arrive via Excel import. This router lets a user set or
correct one by hand for a given (technology, year):

  PUT /api/technologies/{technology_id}/emission-factors

It get-or-creates the ``technology_year`` anchor (traceability/raw_row are nullable, so a
purely manual row is valid) and the ``technology_year_ecotea_parameter`` satellite, then
writes ``emission_factor`` / ``emission_factor_unit``. Sending a null value clears the EF.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import EmissionFactorOut, EmissionFactorUpsert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["emission-factors"])


@router.put(
    "/technologies/{technology_id}/emission-factors",
    response_model=EmissionFactorOut,
)
def upsert_emission_factor(
    technology_id: int,
    payload: EmissionFactorUpsert,
    db: Annotated[Session, Depends(get_db)],
) -> EmissionFactorOut:
    """Set (or clear) the emission factor for one technology-year. Creates rows as needed."""
    tech = db.get(models.TechnologyProcess, technology_id)
    if tech is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Technology {technology_id} not found.",
        )

    unit = (payload.emission_factor_unit or "").strip() or None
    created = False

    try:
        ty = db.scalar(
            select(models.TechnologyYear).where(
                models.TechnologyYear.technology_id == technology_id,
                models.TechnologyYear.data_year == payload.data_year,
            )
        )
        if ty is None:
            ty = models.TechnologyYear(
                technology_id=technology_id,
                data_year=payload.data_year,
            )
            db.add(ty)
            db.flush()  # assign technology_year_id
            created = True

        param = db.get(models.TechnologyYearEcoteaParameter, ty.technology_year_id)
        if param is None:
            param = models.TechnologyYearEcoteaParameter(technology_year_id=ty.technology_year_id)
            db.add(param)
            created = True

        param.emission_factor = payload.emission_factor
        param.emission_factor_unit = unit

        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "Failed to upsert emission factor for technology %s year %s",
            technology_id,
            payload.data_year,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save the emission factor.",
        ) from None

    return EmissionFactorOut(
        technology_id=technology_id,
        technology_code=tech.technology_code,
        technology_year_id=ty.technology_year_id,
        data_year=payload.data_year,
        emission_factor=payload.emission_factor,
        emission_factor_unit=unit,
        created=created,
    )
