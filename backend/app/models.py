"""SQLAlchemy ORM models aligned with sql/001_init_schema.sql."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


# =============================================================================
# 1. import_batch
# =============================================================================
class ImportBatch(Base):
    __tablename__ = "import_batch"

    import_batch_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_hash: Mapped[str | None] = mapped_column(Text)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    imported_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    raw_rows: Mapped[list[RawExcelRow]] = relationship(
        back_populates="batch", cascade="all, delete-orphan"
    )


# =============================================================================
# 2. raw_excel_row
# =============================================================================
class RawExcelRow(Base):
    __tablename__ = "raw_excel_row"

    raw_row_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("import_batch.import_batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    source_sheet_name: Mapped[str] = mapped_column(Text, nullable=False)
    excel_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_type: Mapped[str] = mapped_column(Text, nullable=False, default="data")
    raw_cells: Mapped[dict] = mapped_column(JSONB, nullable=False)
    normalized_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")

    batch: Mapped[ImportBatch] = relationship(back_populates="raw_rows")


# =============================================================================
# 3. sector
# =============================================================================
class Sector(Base):
    __tablename__ = "sector"

    sector_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    sector_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    sector_name: Mapped[str] = mapped_column(Text, nullable=False)


# =============================================================================
# 4. (REMOVED) data_source, merged into traceability_record
# =============================================================================


# =============================================================================
# 6. geography
# =============================================================================
class Geography(Base):
    __tablename__ = "geography"

    geography_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    geography_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    geography_name: Mapped[str | None] = mapped_column(Text)


# =============================================================================
# 11. commodity, including VEDA Commodities fields
# =============================================================================
class Commodity(Base):
    __tablename__ = "commodity"

    commodity_id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    commodity_code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    commodity_set: Mapped[str | None] = mapped_column(Text)  # NRG / ENV
    commodity_description: Mapped[str | None] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(Text)  # PJ, kt
    lim_type: Mapped[str | None] = mapped_column(Text)  # FX
    cts_lvl: Mapped[str | None] = mapped_column(Text)  # DAYNITE
    peak_ts: Mapped[str | None] = mapped_column(Text)
    ctype: Mapped[str | None] = mapped_column(Text)  # ELC


# =============================================================================
# 5. traceability_record
# =============================================================================
class TraceabilityRecord(Base):
    __tablename__ = "traceability_record"

    traceability_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sector_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sector.sector_id"), nullable=False
    )
    raw_row_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("raw_excel_row.raw_row_id", ondelete="SET NULL")
    )
    wp_title_raw: Mapped[str | None] = mapped_column(Text)
    data_owner_raw: Mapped[str | None] = mapped_column(Text)
    data_provider_raw: Mapped[str | None] = mapped_column(Text)
    data_user_raw: Mapped[str | None] = mapped_column(Text)
    usage_purpose: Mapped[str | None] = mapped_column(Text)
    data_source_name: Mapped[str | None] = mapped_column(Text)
    data_source_description: Mapped[str | None] = mapped_column(Text)
    source_sheet_name: Mapped[str | None] = mapped_column(Text)
    source_excel_row: Mapped[int | None] = mapped_column(Integer)


# =============================================================================
# 7. technology_process
# =============================================================================
class TechnologyProcess(Base):
    __tablename__ = "technology_process"
    __table_args__ = (UniqueConstraint("technology_code", "geography_id"),)

    technology_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sector_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("sector.sector_id"), nullable=False
    )
    geography_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("geography.geography_id"), nullable=False
    )
    technology_code: Mapped[str] = mapped_column(Text, nullable=False)
    technology_description: Mapped[str | None] = mapped_column(Text)
    technology_start_year: Mapped[int | None] = mapped_column(SmallInteger)
    technology_lifetime_years: Mapped[int | None] = mapped_column(SmallInteger)
    grade: Mapped[str | None] = mapped_column(Text)


# =============================================================================
# 8. technology_year (Anchor)
# =============================================================================
class TechnologyYear(Base):
    __tablename__ = "technology_year"
    __table_args__ = (UniqueConstraint("technology_id", "data_year"),)

    technology_year_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    technology_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_process.technology_id", ondelete="CASCADE"),
        nullable=False,
    )
    traceability_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("traceability_record.traceability_id")
    )
    raw_row_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("raw_excel_row.raw_row_id", ondelete="SET NULL")
    )
    data_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)


# =============================================================================
# 9. technology_year_ecotea_parameter (O:Y)
# =============================================================================
class TechnologyYearEcoteaParameter(Base):
    __tablename__ = "technology_year_ecotea_parameter"

    technology_year_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_year.technology_year_id", ondelete="CASCADE"),
        primary_key=True,
    )
    emission_factor: Mapped[Decimal | None] = mapped_column(Numeric)
    emission_factor_unit: Mapped[str | None] = mapped_column(Text)
    base_currency: Mapped[str | None] = mapped_column(Text)
    capex: Mapped[Decimal | None] = mapped_column(Numeric)
    capex_unit: Mapped[str | None] = mapped_column(Text)
    fixed_opex: Mapped[Decimal | None] = mapped_column(Numeric)
    fixed_opex_unit: Mapped[str | None] = mapped_column(Text)
    variable_opex: Mapped[Decimal | None] = mapped_column(Numeric)
    variable_opex_unit: Mapped[str | None] = mapped_column(Text)
    tax_cost: Mapped[Decimal | None] = mapped_column(Numeric)
    subsidy_cost: Mapped[Decimal | None] = mapped_column(Numeric)


# =============================================================================
# 10. technology_year_wp_descriptor (Z, AA, AF, AG)
# =============================================================================
class TechnologyYearWpDescriptor(Base):
    __tablename__ = "technology_year_wp_descriptor"

    technology_year_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_year.technology_year_id", ondelete="CASCADE"),
        primary_key=True,
    )
    efficiency_value: Mapped[Decimal | None] = mapped_column(Numeric)
    efficiency_text: Mapped[str | None] = mapped_column(Text)
    efficiency_unit: Mapped[str | None] = mapped_column(Text)
    technology_efficiency: Mapped[Decimal | None] = mapped_column(Numeric)
    capacity_to_activity_factor: Mapped[Decimal | None] = mapped_column(Numeric)
    heat_rate: Mapped[Decimal | None] = mapped_column(Numeric)


# =============================================================================
# 12. technology_year_commodity (AB:AE)
# =============================================================================
class TechnologyYearCommodity(Base):
    __tablename__ = "technology_year_commodity"
    __table_args__ = (UniqueConstraint("technology_year_id", "commodity_order"),)

    technology_year_commodity_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    technology_year_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_year.technology_year_id", ondelete="CASCADE"),
        nullable=False,
    )
    commodity_id: Mapped[int] = mapped_column(
        SmallInteger, ForeignKey("commodity.commodity_id"), nullable=False
    )
    commodity_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    commodity_share_value: Mapped[Decimal | None] = mapped_column(Numeric)
    commodity_share_text: Mapped[str | None] = mapped_column(Text)
    commodity_demand_value: Mapped[Decimal | None] = mapped_column(Numeric)
    commodity_demand_text: Mapped[str | None] = mapped_column(Text)
    interpolation_rule_value: Mapped[Decimal | None] = mapped_column(Numeric)
    interpolation_rule_text: Mapped[str | None] = mapped_column(Text)


# =============================================================================
# 13. technology_year_constraint (AH:AI)
# =============================================================================
class TechnologyYearConstraint(Base):
    __tablename__ = "technology_year_constraint"

    constraint_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    technology_year_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_year.technology_year_id", ondelete="CASCADE"),
        nullable=False,
    )
    constraint_type: Mapped[str] = mapped_column(Text, nullable=False, default="capacity")
    constraint_value: Mapped[Decimal | None] = mapped_column(Numeric)
    bound_type: Mapped[str | None] = mapped_column(Text)
    constraint_unit: Mapped[str | None] = mapped_column(Text)


# =============================================================================
# 14. technology_year_constraint_detail (AJ:AL)
# =============================================================================
class TechnologyYearConstraintDetail(Base):
    __tablename__ = "technology_year_constraint_detail"

    constraint_detail_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    technology_year_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("technology_year.technology_year_id", ondelete="CASCADE"),
        nullable=False,
    )
    detail_type: Mapped[str] = mapped_column(Text, nullable=False)
    detail_value: Mapped[Decimal | None] = mapped_column(Numeric)
    detail_unit: Mapped[str | None] = mapped_column(Text)


# =============================================================================
# 15. data_quality_issue
# =============================================================================
class DataQualityIssue(Base):
    __tablename__ = "data_quality_issue"

    issue_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    raw_row_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("raw_excel_row.raw_row_id", ondelete="SET NULL")
    )
    source_sheet_name: Mapped[str | None] = mapped_column(Text)
    excel_row_number: Mapped[int | None] = mapped_column(Integer)
    excel_column: Mapped[str | None] = mapped_column(Text)
    issue_type: Mapped[str] = mapped_column(Text, nullable=False)
    original_value: Mapped[str | None] = mapped_column(Text)
    issue_message: Mapped[str | None] = mapped_column(Text)
