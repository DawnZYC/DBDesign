"""(3) run_sql — Pydantic-parameterized SQL execution tool.

Design points:
  * Input is the Pydantic model QueryParams; it **never accepts raw SQL strings**, ruling out injection.
  * Field whitelist (metric / aggregation / group_by etc. are all Literal enums).
  * Uses SQLAlchemy 2.0 select() expressions + bindparam, never string concatenation.
  * Results always include raw_row_id (unless aggregation != raw); the M4 chart cell-trace depends on it.
  * Results default to limit 1000, hard cap 10000.

Supported metrics:
  - capex / fixed_opex / variable_opex / emission_factor / tax_cost / subsidy_cost
    (from technology_year_ecotea_parameter)
  - efficiency_value / technology_efficiency / heat_rate / capacity_to_activity_factor
    (from technology_year_wp_descriptor)
  - capacity (from technology_year_constraint)
  - commodity_demand_value (from technology_year_commodity)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, Select, and_, func, select
from sqlalchemy.orm import Session

from app import models
from app.database import SessionLocal
from app.tools._base import with_observability

# -----------------------------------------------------------------------------
# Metric registry — map a metric name to (model_class, value column, unit column|None)
# -----------------------------------------------------------------------------
_E = models.TechnologyYearEcoteaParameter
_W = models.TechnologyYearWpDescriptor
_C = models.TechnologyYearConstraint
_CM = models.TechnologyYearCommodity

MetricName = Literal[
    "capex",
    "fixed_opex",
    "variable_opex",
    "emission_factor",
    "tax_cost",
    "subsidy_cost",
    "efficiency_value",
    "technology_efficiency",
    "heat_rate",
    "capacity_to_activity_factor",
    "capacity",
    "commodity_demand_value",
]


@dataclass(frozen=True)
class _MetricInfo:
    model: Any
    value_col: Column
    unit_col: Column | None  # whether this metric has a *_unit field


METRICS: dict[str, _MetricInfo] = {
    "capex": _MetricInfo(_E, _E.capex, _E.capex_unit),
    "fixed_opex": _MetricInfo(_E, _E.fixed_opex, _E.fixed_opex_unit),
    "variable_opex": _MetricInfo(_E, _E.variable_opex, _E.variable_opex_unit),
    "emission_factor": _MetricInfo(_E, _E.emission_factor, _E.emission_factor_unit),
    "tax_cost": _MetricInfo(_E, _E.tax_cost, None),
    "subsidy_cost": _MetricInfo(_E, _E.subsidy_cost, None),
    "efficiency_value": _MetricInfo(_W, _W.efficiency_value, _W.efficiency_unit),
    "technology_efficiency": _MetricInfo(_W, _W.technology_efficiency, None),
    "heat_rate": _MetricInfo(_W, _W.heat_rate, None),
    "capacity_to_activity_factor": _MetricInfo(_W, _W.capacity_to_activity_factor, None),
    "capacity": _MetricInfo(_C, _C.constraint_value, _C.constraint_unit),
    "commodity_demand_value": _MetricInfo(_CM, _CM.commodity_demand_value, None),
}

GroupBy = Literal["sector", "geography", "technology", "year", "commodity"]
Aggregation = Literal["raw", "sum", "avg", "min", "max", "count"]

MAX_LIMIT = 10_000
DEFAULT_LIMIT = 1_000


# -----------------------------------------------------------------------------
# Pydantic input
# -----------------------------------------------------------------------------
class QueryParams(BaseModel):
    """The SQL Agent's structured output. The Agent writes no SQL; it only fills this object."""

    metric: MetricName = Field(..., description="Target metric")
    aggregation: Aggregation = Field(default="raw")

    # Filters
    sector_codes: list[str] | None = Field(
        default=None, description="Filter by sector_code, e.g. ['POWER', 'INDUSTRY']"
    )
    geography_codes: list[str] | None = Field(default=None, description="e.g. ['SG']")
    technology_codes: list[str] | None = Field(
        default=None, description="Exact technology codes, e.g. ['NGCC01']"
    )
    technology_code_like: str | None = Field(
        default=None, description="Fuzzy match on technology code (ILIKE %X%), e.g. 'SOLAR'"
    )
    commodity_codes: list[str] | None = Field(default=None)
    year_min: int | None = None
    year_max: int | None = None

    # Grouping (only effective when aggregation != 'raw')
    group_by: list[GroupBy] = Field(default_factory=list)

    # Limit
    limit: int = Field(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)

    @field_validator("sector_codes", "geography_codes", "technology_codes", "commodity_codes")
    @classmethod
    def _strip_empty(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        cleaned = [s.strip().upper() if s else "" for s in v]
        cleaned = [s for s in cleaned if s]
        return cleaned or None


class QueryResult(BaseModel):
    rows: list[dict[str, Any]]
    metric: MetricName
    aggregation: Aggregation
    metric_unit: str | None = Field(default=None, description="Most common unit in the result (mode when several)")
    row_count: int
    truncated: bool = Field(default=False, description="Whether the limit was hit and rows were truncated")
    sql_summary: str = Field(default="", description="Human-readable query summary (for debug / trace)")


# -----------------------------------------------------------------------------
# Compile: QueryParams -> SQLAlchemy select()
# -----------------------------------------------------------------------------
def _build_query(params: QueryParams) -> tuple[Select, list[str]]:
    """Build the select() and the list of result column names."""
    info = METRICS[params.metric]
    metric_table = info.model
    value_col = info.value_col

    # Base join: satellite <- technology_year <- technology_process <- sector / geography
    ty = models.TechnologyYear
    tp = models.TechnologyProcess
    sector = models.Sector
    geo = models.Geography

    # Selected columns (per-row identity + metric value)
    select_cols: list[Any] = []
    col_names: list[str] = []

    if params.aggregation == "raw":
        # Raw rows: always carry raw_row_id for tracing
        select_cols.extend(
            [
                ty.data_year.label("data_year"),
                tp.technology_code.label("technology_code"),
                sector.sector_code.label("sector_code"),
                sector.sector_name.label("sector_name"),
                geo.geography_code.label("geography_code"),
                ty.raw_row_id.label("raw_row_id"),
                value_col.label("value"),
            ]
        )
        col_names = [
            "data_year",
            "technology_code",
            "sector_code",
            "sector_name",
            "geography_code",
            "raw_row_id",
            "value",
        ]
        if info.unit_col is not None:
            select_cols.append(info.unit_col.label("unit"))
            col_names.append("unit")
    else:
        # Aggregation
        agg_func = {
            "sum": func.sum,
            "avg": func.avg,
            "min": func.min,
            "max": func.max,
            "count": func.count,
        }[params.aggregation]
        select_cols.append(agg_func(value_col).label("value"))
        col_names.append("value")
        # Add the grouping columns
        gb_cols = _resolve_group_by(params.group_by, sector, geo, tp, ty)
        for gb_name, gb_col in gb_cols:
            select_cols.insert(0, gb_col.label(gb_name))
            col_names.insert(0, gb_name)

    stmt: Select = select(*select_cols)

    # JOIN chain: metric table -> technology_year -> technology_process -> sector & geography
    stmt = stmt.select_from(metric_table)

    # The commodity metric is special: trace via tech_year_id
    stmt = stmt.join(ty, metric_table.technology_year_id == ty.technology_year_id)
    stmt = stmt.join(tp, ty.technology_id == tp.technology_id)
    stmt = stmt.join(sector, tp.sector_id == sector.sector_id)
    stmt = stmt.join(geo, tp.geography_id == geo.geography_id)

    # Join the commodity tables whenever a commodity GROUPING or commodity FILTER is requested.
    # For the commodity_demand_value metric the metric table already IS technology_year_commodity;
    # for any other metric we must bring it in via technology_year first, otherwise the query would
    # reference Commodity without a join (an invalid query / accidental cross join).
    needs_commodity = ("commodity" in params.group_by) or bool(params.commodity_codes)
    if needs_commodity:
        if metric_table is not _CM:
            stmt = stmt.join(_CM, _CM.technology_year_id == ty.technology_year_id)
        stmt = stmt.join(models.Commodity, models.Commodity.commodity_id == _CM.commodity_id)

    # ---- WHERE ----
    where: list[Any] = [value_col.is_not(None)]  # always filter out NULL metric values
    if params.sector_codes:
        where.append(sector.sector_code.in_(params.sector_codes))
    if params.geography_codes:
        where.append(geo.geography_code.in_(params.geography_codes))
    if params.technology_codes:
        where.append(tp.technology_code.in_(params.technology_codes))
    if params.technology_code_like:
        where.append(tp.technology_code.ilike(f"%{params.technology_code_like}%"))
    if params.commodity_codes:
        where.append(models.Commodity.commodity_code.in_(params.commodity_codes))
    if params.year_min is not None:
        where.append(ty.data_year >= params.year_min)
    if params.year_max is not None:
        where.append(ty.data_year <= params.year_max)
    stmt = stmt.where(and_(*where))

    # ---- GROUP BY ----
    if params.aggregation != "raw":
        gb_cols = _resolve_group_by(params.group_by, sector, geo, tp, ty)
        stmt = stmt.group_by(*[c for _, c in gb_cols])
        # Order by the same columns
        stmt = stmt.order_by(*[c for _, c in gb_cols])
    else:
        stmt = stmt.order_by(ty.data_year, tp.technology_code)

    # ---- LIMIT ----
    stmt = stmt.limit(min(params.limit, MAX_LIMIT))
    return stmt, col_names


def _resolve_group_by(gb: list[GroupBy], sector, geo, tp, ty) -> list[tuple[str, Any]]:
    mapping = {
        "sector": ("sector_code", sector.sector_code),
        "geography": ("geography_code", geo.geography_code),
        "technology": ("technology_code", tp.technology_code),
        "year": ("data_year", ty.data_year),
        "commodity": ("commodity_code", models.Commodity.commodity_code),
    }
    return [mapping[g] for g in gb]


# -----------------------------------------------------------------------------
# Execution
# -----------------------------------------------------------------------------
def _execute(db: Session, params: QueryParams) -> QueryResult:
    effective_limit = min(params.limit, MAX_LIMIT)
    # Fetch 1 extra row to detect truncation, avoiding a false positive when count == limit exactly
    stmt, _ = _build_query(params)
    stmt = stmt.limit(effective_limit + 1)
    rows = db.execute(stmt).mappings().all()
    rows_list = [dict(r) for r in rows]

    truncated = len(rows_list) > effective_limit
    if truncated:
        rows_list = rows_list[:effective_limit]  # drop the extra row we fetched

    # Unit inference (mode)
    unit: str | None = None
    if rows_list and "unit" in rows_list[0]:
        units = [r.get("unit") for r in rows_list if r.get("unit")]
        if units:
            unit = max(set(units), key=units.count)

    # SQL summary (human-readable)
    summary_parts = [f"metric={params.metric}", f"agg={params.aggregation}"]
    if params.sector_codes:
        summary_parts.append(f"sectors={params.sector_codes}")
    if params.geography_codes:
        summary_parts.append(f"geo={params.geography_codes}")
    if params.technology_codes:
        summary_parts.append(f"techs={params.technology_codes}")
    if params.technology_code_like:
        summary_parts.append(f"tech~{params.technology_code_like}")
    if params.year_min or params.year_max:
        summary_parts.append(f"years={params.year_min or '*'}..{params.year_max or '*'}")
    if params.group_by:
        summary_parts.append(f"group_by={params.group_by}")

    return QueryResult(
        rows=rows_list,
        metric=params.metric,
        aggregation=params.aggregation,
        metric_unit=unit,
        row_count=len(rows_list),
        truncated=truncated,
        sql_summary="; ".join(summary_parts),
    )


# -----------------------------------------------------------------------------
# Tool entry point (LangChain @tool)
# -----------------------------------------------------------------------------
@tool("run_sql", args_schema=QueryParams)
@with_observability("run_sql")
def run_sql(**kwargs: Any) -> dict:
    """Execute a parameterized, safe SQL query against the EcoTEA WP1 schema.

    Input is a structured QueryParams (no raw SQL strings). The query is compiled
    via SQLAlchemy with bound parameters, joining the appropriate satellite table
    based on the requested metric. Results always include raw_row_id when
    aggregation='raw' so the frontend can trace back to the source Excel cell.
    """
    params = QueryParams(**kwargs)
    db = SessionLocal()
    try:
        result = _execute(db, params)
        return result.model_dump()
    finally:
        db.close()
