"""Pydantic schemas for API request and response models."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ColumnSuggestionOut(BaseModel):
    """Single-column mapping suggestion for the M5 column-alignment review UI."""

    excel_column: str = Field(..., description="Column letter in the uploaded Excel.")
    excel_header: str = Field(default="", description="Raw header text of the column.")
    target_field: str | None = Field(default=None, description="Matched standard field name.")
    target_column: str | None = Field(
        default=None, description="Canonical column letter of the matched field."
    )
    confidence: float = Field(default=0.0, description="Match confidence in [0, 1].")
    status: str = Field(
        ...,
        description="auto (>=0.9, applied) / review (0.6-0.9, needs human) / unmatched (<0.6).",
    )
    reasoning: str = Field(default="")


class SheetColumnMapping(BaseModel):
    """M5 column-alignment result for one sheet."""

    sheet_name: str
    layout_is_standard: bool = Field(
        ..., description="True when headers match the canonical template (fast path)."
    )
    suggestions: list[ColumnSuggestionOut] = Field(default_factory=list)
    auto_count: int = 0
    review_count: int = Field(default=0, description="Low-confidence columns needing review.")
    unmatched_count: int = 0


class StandardFieldInfo(BaseModel):
    """Standard field metadata for the frontend column-mapping dropdown."""

    field: str
    column: str
    label: str
    description: str


class SheetPreview(BaseModel):
    """Single sheet entry in a file preview."""

    sheet_name: str
    is_known: bool = Field(
        ..., description="Whether the sheet is in the known sector mapping table."
    )
    sector_code: str | None = Field(default=None, description="Mapped sector_code.")
    data_rows: int = Field(..., description="Non-empty data rows from row 10 onward.")
    column_mapping: SheetColumnMapping | None = Field(
        default=None,
        description="M5 column alignment; None for unknown sheets or standard layout.",
    )


class FilePreview(BaseModel):
    """Response for POST /api/imports/preview."""

    file_name: str
    sheets: list[SheetPreview]
    needs_column_review: bool = Field(
        default=False, description="True when any sheet needs column-alignment review."
    )
    standard_fields: list[StandardFieldInfo] = Field(
        default_factory=list, description="All 38 standard fields for the dropdown."
    )


class ImportSheetSummary(BaseModel):
    """Import summary for a single sheet."""

    sheet_name: str
    rows_total: int = Field(..., description="Total data rows in the sheet, excluding headers.")
    rows_imported: int = Field(..., description="Rows imported successfully.")
    rows_skipped: int = Field(default=0, description="Empty or invalid rows skipped.")
    rows_pending: int = Field(default=0, description="Rows pending conflict review.")
    issues: int = Field(default=0, description="New data_quality_issue rows.")
    column_warnings: list[str] = Field(
        default_factory=list,
        description="M5 column-alignment warnings; empty means the fast path was used.",
    )


class ImportResult(BaseModel):
    """Summary for the full import operation."""

    model_config = ConfigDict(from_attributes=True)

    import_batch_id: int
    file_name: str
    imported_at: datetime
    rows_imported: int
    rows_skipped: int
    rows_pending: int = Field(
        default=0, description="Rows pending review, such as sector conflicts."
    )
    issues: int
    sheets: list[ImportSheetSummary]
    duration_ms: int
    column_warnings: list[str] = Field(
        default_factory=list,
        description="Aggregated M5 column-alignment warnings, prefixed with the sheet name.",
    )


class ConflictRow(BaseModel):
    """Single row pending review before grouping by sheet and column A value."""

    raw_row_id: int
    excel_row_number: int


class ConflictGroup(BaseModel):
    """Rows with the same sheet and column A value, grouped for one decision."""

    group_id: str = Field(
        ..., description="Group ID derived from sheet+a_value for client references."
    )
    sheet_name: str
    sheet_sector_code: str | None
    a_column_value: str | None = Field(..., description="Raw value from column A.")
    a_column_sector_code: str | None = Field(
        ..., description="sector_code parsed from column A text, or None when unresolved."
    )
    rows: list[ConflictRow]
    message: str


class ConflictListResponse(BaseModel):
    """Response for GET /api/imports/conflicts."""

    total_pending: int
    groups: list[ConflictGroup]


class ConflictResolution(BaseModel):
    """Single decision submitted by the client."""

    raw_row_id: int
    decision: str = Field(
        ...,
        description="TRUST_SHEET uses the sheet-derived sector; TRUST_A uses the column A-derived sector; SKIP does not import the row.",
    )


class ConflictResolveResponse(BaseModel):
    """Response for POST /api/imports/conflicts/resolve."""

    resolved: int = Field(..., description="Rows processed successfully.")
    failed: int = Field(default=0, description="Rows that failed to process.")
    failure_reasons: list[str] = Field(default_factory=list)


class LLMHealth(BaseModel):
    """Health info for the LLM subsystem (M0)."""

    provider: str
    model: str | None = None
    configured: bool = Field(..., description="Whether the active provider has an API key.")
    ok: bool = Field(default=False, description="Whether the last connectivity test succeeded.")
    latency_ms: int | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = "ok"
    database: str = Field(..., description="Database connection status.")
    llm: LLMHealth | None = Field(default=None, description="LLM abstraction layer status.")


class ProviderInfo(BaseModel):
    """Metadata for one LLM provider (GET /api/llm/providers)."""

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
# Convert (VT -> EcoTEA)
# =============================================================================
class ConvertModelInfo(BaseModel):
    """Public metadata for a registered VT-to-EcoTEA converter."""

    key: str = Field(..., description="Stable identifier passed back to /api/convert.")
    label: str
    sector: str
    description: str | None = None


class ConvertResult(BaseModel):
    """Successful conversion response."""

    download_token: str = Field(..., description="Opaque token used to fetch the converted file.")
    download_name: str
    row_count: int
    sheet_name: str
    model_key: str
    source_file_name: str
    template_file_name: str
    bytes: int = Field(..., description="Size of the produced workbook in bytes.")
    created_at: datetime


# =============================================================================
# Browse
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
    """Single technology list row for /api/technologies."""

    technology_id: int
    technology_code: str
    technology_description: str | None
    sector_code: str
    sector_name: str
    geography_code: str
    technology_start_year: int | None
    technology_lifetime_years: int | None
    grade: str | None
    year_count: int = Field(..., description="Number of technology_year rows for this technology.")
    year_min: int | None
    year_max: int | None


class TechnologyListResponse(BaseModel):
    items: list[TechnologyListItem]
    total: int = Field(..., description="Total rows matching the filters, for pagination.")
    page: int
    page_size: int


class CommodityRowOut(BaseModel):
    commodity_code: str
    commodity_order: int
    share_value: Decimal | None
    share_text: str | None
    demand_value: Decimal | None
    demand_text: str | None
    # From the commodity dictionary table (VEDA Commodities sheet).
    commodity_set: str | None = None
    commodity_description: str | None = None
    unit: str | None = None


class ConstraintDetailOut(BaseModel):
    detail_type: str
    detail_value: Decimal | None
    detail_unit: str | None


class TechnologyYearOut(BaseModel):
    """All parameters for one technology year, including master and satellite data."""

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
    """Technology detail: master row plus all years."""

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


# -----------------------------------------------------------------------------
# Emission-factor manual entry (PUT /api/technologies/{id}/emission-factors)
# -----------------------------------------------------------------------------
class EmissionFactorUpsert(BaseModel):
    """Manually set (or clear) the emission factor for one technology-year."""

    data_year: int = Field(..., ge=1900, le=2200)
    emission_factor: Decimal | None = Field(
        default=None, description="The emission-factor value; send null to clear it."
    )
    emission_factor_unit: str | None = Field(
        default=None, max_length=64, description="e.g. kt-CO2/PJ"
    )


class EmissionFactorOut(BaseModel):
    technology_id: int
    technology_code: str
    technology_year_id: int
    data_year: int
    emission_factor: Decimal | None = None
    emission_factor_unit: str | None = None
    created: bool = Field(
        description="True if a new technology-year and/or parameter row was created."
    )
