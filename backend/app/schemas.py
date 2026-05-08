"""Pydantic schemas — API 请求/响应模型。"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class SheetPreview(BaseModel):
    """文件预览中的单个 sheet 信息。"""

    sheet_name: str
    is_known: bool = Field(..., description="是否在已知行业映射表里（10 个 sheet）")
    sector_code: str | None = Field(default=None, description="对应的 sector_code")
    data_rows: int = Field(..., description="非空数据行数（行 10 起）")


class FilePreview(BaseModel):
    """POST /api/imports/preview 的响应。"""

    file_name: str
    sheets: list[SheetPreview]


class ImportSheetSummary(BaseModel):
    """单个 sheet 的导入摘要。"""

    sheet_name: str
    rows_total: int = Field(..., description="该 sheet 数据行总数（不含表头）")
    rows_imported: int = Field(..., description="成功导入的行数")
    rows_skipped: int = Field(default=0, description="跳过的空行 / 无效行")
    rows_pending: int = Field(default=0, description="发现冲突待复核的行数")
    issues: int = Field(default=0, description="data_quality_issue 新增数")


class ImportResult(BaseModel):
    """整个导入操作的结果摘要。"""

    model_config = ConfigDict(from_attributes=True)

    import_batch_id: int
    file_name: str
    imported_at: datetime
    rows_imported: int
    rows_skipped: int
    rows_pending: int = Field(default=0, description="待复核行数（有 sector 冲突等）")
    issues: int
    sheets: list[ImportSheetSummary]
    duration_ms: int


class ConflictRow(BaseModel):
    """一条待复核的行（按 sheet + A 列值分组前的原始记录）。"""

    raw_row_id: int
    excel_row_number: int


class ConflictGroup(BaseModel):
    """同 sheet、同 A 列值的若干行打包成一组，让用户一次决定。"""

    group_id: str = Field(..., description="组 ID，由 sheet+a_value 派生，用于客户端引用")
    sheet_name: str
    sheet_sector_code: str | None
    a_column_value: str | None = Field(..., description="A 列原始值")
    a_column_sector_code: str | None = Field(
        ..., description="A 列文本解析出的 sector_code（无法解析则为 None）"
    )
    rows: list[ConflictRow]
    message: str


class ConflictListResponse(BaseModel):
    """GET /api/imports/conflicts 响应。"""

    total_pending: int
    groups: list[ConflictGroup]


class ConflictResolution(BaseModel):
    """客户端提交的单条决定。"""

    raw_row_id: int
    decision: str = Field(
        ...,
        description="TRUST_SHEET（用 sheet 推出的 sector）/ TRUST_A（用 A 列推出的 sector）/ SKIP（不导入）",
    )


class ConflictResolveResponse(BaseModel):
    """POST /api/imports/conflicts/resolve 响应。"""

    resolved: int = Field(..., description="处理成功的行数")
    failed: int = Field(default=0, description="处理失败的行数")
    failure_reasons: list[str] = Field(default_factory=list)


class LLMHealth(BaseModel):
    """LLM 子系统的健康检查信息。"""

    provider: str
    model: str | None = None
    configured: bool = Field(..., description="当前 provider 是否已配置 API key")
    ok: bool = Field(default=False, description="最近一次连通性测试是否成功")
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str = "ok"
    database: str = Field(..., description="数据库连接状态")
    llm: LLMHealth | None = Field(default=None, description="LLM 抽象层状态")


class ProviderInfo(BaseModel):
    """单个 provider 的元信息（用于 GET /api/llm/providers）。"""

    name: str
    display_name: str
    adapter: str
    default_model: str
    base_url: str | None
    docs_url: str | None
    configured: bool
    is_active: bool


class ProvidersResponse(BaseModel):
    active: str
    providers: list[ProviderInfo]


# =============================================================================
# 浏览相关
# =============================================================================
class SectorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sector_id: int
    sector_code: str
    sector_name: str


class GeographyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    geography_id: int
    geography_code: str
    geography_name: str | None = None


class TechnologyListItem(BaseModel):
    """技术列表的一行（用于 /api/technologies）。"""

    technology_id: int
    technology_code: str
    technology_description: str | None
    sector_code: str
    sector_name: str
    geography_code: str
    technology_start_year: int | None
    technology_lifetime_years: int | None
    grade: str | None
    year_count: int = Field(..., description="该技术下 technology_year 的数量")
    year_min: int | None
    year_max: int | None


class TechnologyListResponse(BaseModel):
    items: list[TechnologyListItem]
    total: int = Field(..., description="符合过滤条件的总数（分页用）")
    page: int
    page_size: int


class CommodityRowOut(BaseModel):
    commodity_code: str
    commodity_order: int
    share_value: Decimal | None
    share_text: str | None
    demand_value: Decimal | None
    demand_text: str | None
    # 来自 commodity 字典表（VEDA Commodities sheet）
    commodity_set: str | None = None
    commodity_description: str | None = None
    unit: str | None = None


class ConstraintDetailOut(BaseModel):
    detail_type: str
    detail_value: Decimal | None
    detail_unit: str | None


class TechnologyYearOut(BaseModel):
    """单个技术年份的全部参数（master + 5 satellites）。"""

    technology_year_id: int
    data_year: int
    raw_row_id: int | None

    # ecotea_parameter
    emission_factor: Decimal | None = None
    emission_factor_unit: str | None = None
    base_currency: str | None = None
    capex: Decimal | None = None
    capex_unit: str | None = None
    fixed_opex: Decimal | None = None
    fixed_opex_unit: str | None = None
    variable_opex: Decimal | None = None
    variable_opex_unit: str | None = None
    tax_cost: Decimal | None = None
    subsidy_cost: Decimal | None = None

    # wp_descriptor
    efficiency_value: Decimal | None = None
    efficiency_text: str | None = None
    efficiency_unit: str | None = None
    technology_efficiency: Decimal | None = None
    capacity_to_activity_factor: Decimal | None = None
    heat_rate: Decimal | None = None

    # constraint
    capacity_value: Decimal | None = None
    capacity_bound_type: str | None = None

    # detail (multi)
    constraint_details: list[ConstraintDetailOut] = Field(default_factory=list)

    # commodity (multi)
    commodities: list[CommodityRowOut] = Field(default_factory=list)


class TechnologyDetail(BaseModel):
    """技术详情：master + 所有年份。"""

    technology_id: int
    technology_code: str
    technology_description: str | None
    sector_code: str
    sector_name: str
    geography_code: str
    technology_start_year: int | None
    technology_lifetime_years: int | None
    grade: str | None
    years: list[TechnologyYearOut] = Field(default_factory=list)
