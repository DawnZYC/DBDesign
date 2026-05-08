"""③ run_sql — Pydantic 参数化的 SQL 执行工具。

设计要点：
  * 输入是 Pydantic 模型 QueryParams，**不接收原始 SQL 字符串**，杜绝注入
  * 字段白名单（metric / aggregation / group_by 等都是 Literal 枚举）
  * 用 SQLAlchemy 2.0 select() 表达式 + bindparam，绝不字符串拼接
  * 结果一定带 raw_row_id（除非 aggregation != raw），M4 图表反查源单元格的依赖
  * 结果默认 limit 1000，硬上限 10000

支持的 metric:
  - capex / fixed_opex / variable_opex / emission_factor / tax_cost / subsidy_cost
    （来自 technology_year_ecotea_parameter）
  - efficiency_value / technology_efficiency / heat_rate / capacity_to_activity_factor
    （来自 technology_year_wp_descriptor）
  - capacity（来自 technology_year_constraint）
  - commodity_demand_value（来自 technology_year_commodity）
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
# Metric 注册表 — 把 metric 名映射到 (model_class, 数值列, 单位列|None)
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
    unit_col: Column | None  # 该 metric 是否有 *_unit 字段


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
# Pydantic 入参
# -----------------------------------------------------------------------------
class QueryParams(BaseModel):
    """SQL Agent 的结构化输出。Agent 不写 SQL，只填这个对象。"""

    metric: MetricName = Field(..., description="目标指标")
    aggregation: Aggregation = Field(default="raw")

    # 过滤
    sector_codes: list[str] | None = Field(
        default=None, description="按 sector_code 过滤，如 ['POWER', 'INDUSTRY']"
    )
    geography_codes: list[str] | None = Field(default=None, description="如 ['SG']")
    technology_codes: list[str] | None = Field(
        default=None, description="精确技术代码，如 ['PWRNGACCF01']"
    )
    technology_code_like: str | None = Field(
        default=None, description="技术代码模糊匹配（ILIKE %X%），如 'PWRSOL'"
    )
    commodity_codes: list[str] | None = Field(default=None)
    year_min: int | None = None
    year_max: int | None = None

    # 分组（仅当 aggregation != 'raw' 时生效）
    group_by: list[GroupBy] = Field(default_factory=list)

    # 限制
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
    metric_unit: str | None = Field(
        default=None, description="结果中最常见的单位（多种时取众数）"
    )
    row_count: int
    truncated: bool = Field(default=False, description="是否触达 limit 被截断")
    sql_summary: str = Field(
        default="", description="人类可读的查询摘要（debug / trace 用）"
    )


# -----------------------------------------------------------------------------
# 编译：QueryParams → SQLAlchemy select()
# -----------------------------------------------------------------------------
def _build_query(params: QueryParams) -> tuple[Select, list[str]]:
    """构造 select() 与结果列名列表。"""
    info = METRICS[params.metric]
    metric_table = info.model
    value_col = info.value_col

    # 基础 join：satellite ← technology_year ← technology_process ← sector / geography
    ty = models.TechnologyYear
    tp = models.TechnologyProcess
    sector = models.Sector
    geo = models.Geography

    # 选列（每行身份 + metric 值）
    select_cols: list[Any] = []
    col_names: list[str] = []

    if params.aggregation == "raw":
        # 原始行：必带 raw_row_id 用于反查
        select_cols.extend([
            ty.data_year.label("data_year"),
            tp.technology_code.label("technology_code"),
            sector.sector_code.label("sector_code"),
            sector.sector_name.label("sector_name"),
            geo.geography_code.label("geography_code"),
            ty.raw_row_id.label("raw_row_id"),
            value_col.label("value"),
        ])
        col_names = ["data_year", "technology_code", "sector_code",
                     "sector_name", "geography_code", "raw_row_id", "value"]
        if info.unit_col is not None:
            select_cols.append(info.unit_col.label("unit"))
            col_names.append("unit")
    else:
        # 聚合
        agg_func = {
            "sum": func.sum, "avg": func.avg, "min": func.min,
            "max": func.max, "count": func.count,
        }[params.aggregation]
        select_cols.append(agg_func(value_col).label("value"))
        col_names.append("value")
        # 加上分组列
        gb_cols = _resolve_group_by(params.group_by, sector, geo, tp, ty)
        for gb_name, gb_col in gb_cols:
            select_cols.insert(0, gb_col.label(gb_name))
            col_names.insert(0, gb_name)

    stmt: Select = select(*select_cols)

    # JOIN 链路：先 metric 表 → technology_year → technology_process → sector & geography
    stmt = stmt.select_from(metric_table)

    # commodity metric 比较特殊：tech_year_id 反查
    stmt = stmt.join(ty, metric_table.technology_year_id == ty.technology_year_id)
    stmt = stmt.join(tp, ty.technology_id == tp.technology_id)
    stmt = stmt.join(sector, tp.sector_id == sector.sector_id)
    stmt = stmt.join(geo, tp.geography_id == geo.geography_id)

    # 如果 metric 是 commodity_demand_value，还要 join commodity 表（可选，用于过滤）
    if params.metric == "commodity_demand_value" and params.commodity_codes:
        stmt = stmt.join(
            models.Commodity, models.Commodity.commodity_id == _CM.commodity_id
        )

    # ---- WHERE ----
    where: list[Any] = [value_col.is_not(None)]  # 永远过滤掉 NULL 指标
    if params.sector_codes:
        where.append(sector.sector_code.in_(params.sector_codes))
    if params.geography_codes:
        where.append(geo.geography_code.in_(params.geography_codes))
    if params.technology_codes:
        where.append(tp.technology_code.in_(params.technology_codes))
    if params.technology_code_like:
        where.append(tp.technology_code.ilike(f"%{params.technology_code_like}%"))
    if params.commodity_codes and params.metric == "commodity_demand_value":
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
        # 排序也按这些列
        stmt = stmt.order_by(*[c for _, c in gb_cols])
    else:
        stmt = stmt.order_by(ty.data_year, tp.technology_code)

    # ---- LIMIT ----
    stmt = stmt.limit(min(params.limit, MAX_LIMIT))
    return stmt, col_names


def _resolve_group_by(
    gb: list[GroupBy], sector, geo, tp, ty
) -> list[tuple[str, Any]]:
    mapping = {
        "sector": ("sector_code", sector.sector_code),
        "geography": ("geography_code", geo.geography_code),
        "technology": ("technology_code", tp.technology_code),
        "year": ("data_year", ty.data_year),
        "commodity": ("commodity_code", models.Commodity.commodity_code),
    }
    return [mapping[g] for g in gb]


# -----------------------------------------------------------------------------
# 执行
# -----------------------------------------------------------------------------
def _execute(db: Session, params: QueryParams) -> QueryResult:
    stmt, _ = _build_query(params)
    rows = db.execute(stmt).mappings().all()
    rows_list = [dict(r) for r in rows]

    # 单位推断（取众数）
    unit: str | None = None
    if rows_list and "unit" in rows_list[0]:
        units = [r.get("unit") for r in rows_list if r.get("unit")]
        if units:
            unit = max(set(units), key=units.count)

    truncated = len(rows_list) >= min(params.limit, MAX_LIMIT)

    # SQL 摘要（人类可读）
    summary_parts = [f"metric={params.metric}", f"agg={params.aggregation}"]
    if params.sector_codes: summary_parts.append(f"sectors={params.sector_codes}")
    if params.geography_codes: summary_parts.append(f"geo={params.geography_codes}")
    if params.technology_codes: summary_parts.append(f"techs={params.technology_codes}")
    if params.technology_code_like: summary_parts.append(f"tech~{params.technology_code_like}")
    if params.year_min or params.year_max:
        summary_parts.append(f"years={params.year_min or '*'}..{params.year_max or '*'}")
    if params.group_by: summary_parts.append(f"group_by={params.group_by}")

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
# 工具入口（LangChain @tool）
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
