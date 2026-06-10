"""Read-only data browsing routes."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models
from app.database import get_db
from app.schemas import (
    CommodityRowOut,
    ConstraintDetailOut,
    GeographyOut,
    SectorOut,
    TechnologyDetail,
    TechnologyListItem,
    TechnologyListResponse,
    TechnologyYearOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["browse"])

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


# -----------------------------------------------------------------------------
# Dictionary lookups for frontend filter dropdowns.
# -----------------------------------------------------------------------------
@router.get("/sectors", response_model=list[SectorOut], summary="List all sectors")
def list_sectors(db: Session = Depends(get_db)) -> list[SectorOut]:
    rows = db.scalars(select(models.Sector).order_by(models.Sector.sector_id)).all()
    return [SectorOut.model_validate(r) for r in rows]


@router.get("/geographies", response_model=list[GeographyOut], summary="List all geographies")
def list_geographies(db: Session = Depends(get_db)) -> list[GeographyOut]:
    rows = db.scalars(select(models.Geography).order_by(models.Geography.geography_id)).all()
    return [GeographyOut.model_validate(r) for r in rows]


# -----------------------------------------------------------------------------
# Technology list.
# -----------------------------------------------------------------------------
@router.get(
    "/technologies",
    response_model=TechnologyListResponse,
    summary="List technologies by filters, including year range for each technology",
)
def list_technologies(
    db: Session = Depends(get_db),
    sector_id: Annotated[int | None, Query(description="Filter by sector_id")] = None,
    geography_id: Annotated[int | None, Query(description="Filter by geography_id")] = None,
    q: Annotated[
        str | None,
        Query(description="Fuzzy search by technology_code or description"),
    ] = None,
    page: Annotated[int, Query(ge=1, description="Page number, 1-based")] = 1,
    page_size: Annotated[
        int, Query(ge=1, le=MAX_PAGE_SIZE, description="Page size")
    ] = DEFAULT_PAGE_SIZE,
) -> TechnologyListResponse:
    """Technology list with summary statistics: year count, earliest year, latest year."""

    tp = models.TechnologyProcess
    s = models.Sector
    g = models.Geography
    ty = models.TechnologyYear

    base = (
        select(
            tp.technology_id,
            tp.technology_code,
            tp.technology_description,
            tp.technology_start_year,
            tp.technology_lifetime_years,
            tp.grade,
            s.sector_code,
            s.sector_name,
            g.geography_code,
            func.count(ty.technology_year_id).label("year_count"),
            func.min(ty.data_year).label("year_min"),
            func.max(ty.data_year).label("year_max"),
        )
        .join(s, s.sector_id == tp.sector_id)
        .join(g, g.geography_id == tp.geography_id)
        .join(ty, ty.technology_id == tp.technology_id, isouter=True)
        .group_by(
            tp.technology_id,
            tp.technology_code,
            tp.technology_description,
            tp.technology_start_year,
            tp.technology_lifetime_years,
            tp.grade,
            s.sector_code,
            s.sector_name,
            g.geography_code,
        )
    )

    if sector_id is not None:
        base = base.where(tp.sector_id == sector_id)
    if geography_id is not None:
        base = base.where(tp.geography_id == geography_id)
    if q:
        like = f"%{q.strip()}%"
        base = base.where(
            (tp.technology_code.ilike(like)) | (tp.technology_description.ilike(like))
        )

    # Count rows by wrapping the grouped query in a subquery.
    count_stmt = select(func.count()).select_from(base.subquery())
    total = int(db.scalar(count_stmt) or 0)

    # Apply pagination.
    rows = db.execute(
        base.order_by(tp.technology_code).offset((page - 1) * page_size).limit(page_size)
    ).all()

    items = [
        TechnologyListItem(
            technology_id=r.technology_id,
            technology_code=r.technology_code,
            technology_description=r.technology_description,
            sector_code=r.sector_code,
            sector_name=r.sector_name,
            geography_code=r.geography_code,
            technology_start_year=r.technology_start_year,
            technology_lifetime_years=r.technology_lifetime_years,
            grade=r.grade,
            year_count=int(r.year_count or 0),
            year_min=int(r.year_min) if r.year_min is not None else None,
            year_max=int(r.year_max) if r.year_max is not None else None,
        )
        for r in rows
    ]
    return TechnologyListResponse(items=items, total=total, page=page, page_size=page_size)


# -----------------------------------------------------------------------------
# Technology detail: master row plus all years and satellite rows.
# -----------------------------------------------------------------------------
@router.get(
    "/technologies/{technology_id}",
    response_model=TechnologyDetail,
    summary="All years and parameters for one technology",
)
def get_technology(technology_id: int, db: Session = Depends(get_db)) -> TechnologyDetail:
    tp = db.get(models.TechnologyProcess, technology_id)
    if tp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"technology_id={technology_id} does not exist",
        )

    sector = db.get(models.Sector, tp.sector_id)
    geography = db.get(models.Geography, tp.geography_id)

    # Fetch all years in one query.
    year_rows = db.scalars(
        select(models.TechnologyYear)
        .where(models.TechnologyYear.technology_id == technology_id)
        .order_by(models.TechnologyYear.data_year)
    ).all()
    if not year_rows:
        return _empty_detail(tp, sector, geography)

    year_ids = [y.technology_year_id for y in year_rows]

    ecotea_map = _fetch_by_year_id(
        db,
        models.TechnologyYearEcoteaParameter,
        models.TechnologyYearEcoteaParameter.technology_year_id,
        year_ids,
    )
    descriptor_map = _fetch_by_year_id(
        db,
        models.TechnologyYearWpDescriptor,
        models.TechnologyYearWpDescriptor.technology_year_id,
        year_ids,
    )
    constraint_map = _fetch_constraints(db, year_ids)
    detail_map = _fetch_constraint_details(db, year_ids)
    commodity_map = _fetch_commodities(db, year_ids)

    years_out: list[TechnologyYearOut] = []
    for y in year_rows:
        eco = ecotea_map.get(y.technology_year_id)
        desc = descriptor_map.get(y.technology_year_id)
        cap = constraint_map.get(y.technology_year_id)

        years_out.append(
            TechnologyYearOut(
                technology_year_id=y.technology_year_id,
                data_year=y.data_year,
                raw_row_id=y.raw_row_id,
                emission_factor=eco.emission_factor if eco else None,
                emission_factor_unit=eco.emission_factor_unit if eco else None,
                base_currency=eco.base_currency if eco else None,
                capex=eco.capex if eco else None,
                capex_unit=eco.capex_unit if eco else None,
                fixed_opex=eco.fixed_opex if eco else None,
                fixed_opex_unit=eco.fixed_opex_unit if eco else None,
                variable_opex=eco.variable_opex if eco else None,
                variable_opex_unit=eco.variable_opex_unit if eco else None,
                tax_cost=eco.tax_cost if eco else None,
                subsidy_cost=eco.subsidy_cost if eco else None,
                efficiency_value=desc.efficiency_value if desc else None,
                efficiency_text=desc.efficiency_text if desc else None,
                efficiency_unit=desc.efficiency_unit if desc else None,
                technology_efficiency=desc.technology_efficiency if desc else None,
                capacity_to_activity_factor=desc.capacity_to_activity_factor if desc else None,
                heat_rate=desc.heat_rate if desc else None,
                capacity_value=cap.constraint_value if cap else None,
                capacity_bound_type=cap.bound_type if cap else None,
                constraint_details=detail_map.get(y.technology_year_id, []),
                commodities=commodity_map.get(y.technology_year_id, []),
            )
        )

    return TechnologyDetail(
        technology_id=tp.technology_id,
        technology_code=tp.technology_code,
        technology_description=tp.technology_description,
        sector_code=sector.sector_code if sector else "",
        sector_name=sector.sector_name if sector else "",
        geography_code=geography.geography_code if geography else "",
        technology_start_year=tp.technology_start_year,
        technology_lifetime_years=tp.technology_lifetime_years,
        grade=tp.grade,
        years=years_out,
    )


# -----------------------------------------------------------------------------
# Internal helpers.
# -----------------------------------------------------------------------------
def _empty_detail(
    tp: models.TechnologyProcess,
    sector: models.Sector | None,
    geography: models.Geography | None,
) -> TechnologyDetail:
    return TechnologyDetail(
        technology_id=tp.technology_id,
        technology_code=tp.technology_code,
        technology_description=tp.technology_description,
        sector_code=sector.sector_code if sector else "",
        sector_name=sector.sector_name if sector else "",
        geography_code=geography.geography_code if geography else "",
        technology_start_year=tp.technology_start_year,
        technology_lifetime_years=tp.technology_lifetime_years,
        grade=tp.grade,
        years=[],
    )


def _fetch_by_year_id(
    db: Session,
    model_cls,
    fk_column,
    year_ids: list[int],
) -> dict[int, object]:
    """Index satellite rows by technology_year_id, with at most one row per ID."""
    rows = db.scalars(select(model_cls).where(fk_column.in_(year_ids))).all()
    return {r.technology_year_id: r for r in rows}


def _fetch_constraints(
    db: Session, year_ids: list[int]
) -> dict[int, models.TechnologyYearConstraint]:
    rows = db.scalars(
        select(models.TechnologyYearConstraint).where(
            models.TechnologyYearConstraint.technology_year_id.in_(year_ids)
        )
    ).all()
    out: dict[int, models.TechnologyYearConstraint] = {}
    for r in rows:
        out.setdefault(r.technology_year_id, r)  # Use the first row.
    return out


def _fetch_constraint_details(
    db: Session, year_ids: list[int]
) -> dict[int, list[ConstraintDetailOut]]:
    rows = db.scalars(
        select(models.TechnologyYearConstraintDetail).where(
            models.TechnologyYearConstraintDetail.technology_year_id.in_(year_ids)
        )
    ).all()
    out: dict[int, list[ConstraintDetailOut]] = defaultdict(list)
    for r in rows:
        out[r.technology_year_id].append(
            ConstraintDetailOut(
                detail_type=r.detail_type,
                detail_value=r.detail_value,
                detail_unit=r.detail_unit,
            )
        )
    return out


def _fetch_commodities(db: Session, year_ids: list[int]) -> dict[int, list[CommodityRowOut]]:
    rows = (
        db.execute(
            select(models.TechnologyYearCommodity, models.Commodity)
            .join(
                models.Commodity,
                models.Commodity.commodity_id == models.TechnologyYearCommodity.commodity_id,
            )
            .where(models.TechnologyYearCommodity.technology_year_id.in_(year_ids))
            .order_by(
                models.TechnologyYearCommodity.technology_year_id,
                models.TechnologyYearCommodity.commodity_order,
            )
        )
    ).all()
    out: dict[int, list[CommodityRowOut]] = defaultdict(list)
    for tyc, commodity in rows:
        out[tyc.technology_year_id].append(
            CommodityRowOut(
                commodity_code=commodity.commodity_code,
                commodity_order=tyc.commodity_order,
                share_value=tyc.commodity_share_value,
                share_text=tyc.commodity_share_text,
                demand_value=tyc.commodity_demand_value,
                demand_text=tyc.commodity_demand_text,
                commodity_set=commodity.commodity_set,
                commodity_description=commodity.commodity_description,
                unit=commodity.unit,
            )
        )
    return out
