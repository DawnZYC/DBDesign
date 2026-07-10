"""SQLite in-memory database fixture for tests.

Reuses the schema-creation + seeding logic from verify_browse.py, but exposes only minimal
data so the DB-related tool unit tests can all share it.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Must come before importing app.*
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    SmallInteger,
    Table,
    Text,
    UniqueConstraint,
    text,
)

from app import database as dbmod


def setup_test_db() -> None:
    """Create tables + seed test data on the shared engine. Safe to call repeatedly (DROP + CREATE)."""
    md = MetaData()

    # Slimmed-down versions of the 14 business tables (SQLite-compatible: JSONB -> JSON, BigInteger PK -> Integer)
    Table(
        "import_batch",
        md,
        Column("import_batch_id", Integer, primary_key=True, autoincrement=True),
        Column("file_name", Text, nullable=False),
        Column("file_hash", Text),
        Column("imported_by", Text),
        Column("imported_at", Text),
        Column("note", Text),
    )
    Table(
        "raw_excel_row",
        md,
        Column("raw_row_id", Integer, primary_key=True, autoincrement=True),
        Column("import_batch_id", BigInteger, ForeignKey("import_batch.import_batch_id")),
        Column("source_sheet_name", Text, nullable=False),
        Column("excel_row_number", Integer, nullable=False),
        Column("row_type", Text, default="data"),
        Column("raw_cells", JSON, nullable=False),
        Column("normalized_status", Text, default="normalized"),
    )
    Table(
        "sector",
        md,
        Column("sector_id", Integer, primary_key=True, autoincrement=True),
        Column("sector_code", Text, unique=True, nullable=False),
        Column("sector_name", Text, nullable=False),
    )
    Table(
        "geography",
        md,
        Column("geography_id", Integer, primary_key=True, autoincrement=True),
        Column("geography_code", Text, unique=True, nullable=False),
        Column("geography_name", Text),
    )
    Table(
        "commodity",
        md,
        Column("commodity_id", Integer, primary_key=True, autoincrement=True),
        Column("commodity_code", Text, unique=True, nullable=False),
        Column("commodity_set", Text),
        Column("commodity_description", Text),
        Column("unit", Text),
        Column("lim_type", Text),
        Column("cts_lvl", Text),
        Column("peak_ts", Text),
        Column("ctype", Text),
    )
    Table(
        "traceability_record",
        md,
        Column("traceability_id", Integer, primary_key=True, autoincrement=True),
        Column("sector_id", SmallInteger, ForeignKey("sector.sector_id")),
        Column("raw_row_id", BigInteger, ForeignKey("raw_excel_row.raw_row_id")),
        Column("wp_title_raw", Text),
        Column("data_owner_raw", Text),
        Column("data_provider_raw", Text),
        Column("data_user_raw", Text),
        Column("usage_purpose", Text),
        Column("data_source_name", Text),
        Column("data_source_description", Text),
        Column("source_sheet_name", Text),
        Column("source_excel_row", Integer),
    )
    Table(
        "technology_process",
        md,
        Column("technology_id", Integer, primary_key=True, autoincrement=True),
        Column("sector_id", SmallInteger, ForeignKey("sector.sector_id")),
        Column("geography_id", SmallInteger, ForeignKey("geography.geography_id")),
        Column("technology_code", Text, nullable=False),
        Column("technology_description", Text),
        Column("technology_start_year", SmallInteger),
        Column("technology_lifetime_years", SmallInteger),
        Column("grade", Text),
        UniqueConstraint("technology_code", "geography_id"),
    )
    Table(
        "technology_year",
        md,
        Column("technology_year_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_id", BigInteger, ForeignKey("technology_process.technology_id")),
        Column("traceability_id", BigInteger, ForeignKey("traceability_record.traceability_id")),
        Column("raw_row_id", BigInteger, ForeignKey("raw_excel_row.raw_row_id")),
        Column("data_year", SmallInteger, nullable=False),
        UniqueConstraint("technology_id", "data_year"),
    )
    Table(
        "technology_year_ecotea_parameter",
        md,
        Column(
            "technology_year_id",
            BigInteger,
            ForeignKey("technology_year.technology_year_id"),
            primary_key=True,
        ),
        Column("emission_factor", Numeric),
        Column("emission_factor_unit", Text),
        Column("base_currency", Text),
        Column("capex", Numeric),
        Column("capex_unit", Text),
        Column("fixed_opex", Numeric),
        Column("fixed_opex_unit", Text),
        Column("variable_opex", Numeric),
        Column("variable_opex_unit", Text),
        Column("tax_cost", Numeric),
        Column("subsidy_cost", Numeric),
    )
    Table(
        "technology_year_wp_descriptor",
        md,
        Column(
            "technology_year_id",
            BigInteger,
            ForeignKey("technology_year.technology_year_id"),
            primary_key=True,
        ),
        Column("efficiency_value", Numeric),
        Column("efficiency_text", Text),
        Column("efficiency_unit", Text),
        Column("technology_efficiency", Numeric),
        Column("capacity_to_activity_factor", Numeric),
        Column("heat_rate", Numeric),
    )
    Table(
        "technology_year_commodity",
        md,
        Column("technology_year_commodity_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id")),
        Column("commodity_id", SmallInteger, ForeignKey("commodity.commodity_id")),
        Column("commodity_order", SmallInteger, default=1),
        Column("commodity_share_value", Numeric),
        Column("commodity_share_text", Text),
        Column("commodity_demand_value", Numeric),
        Column("commodity_demand_text", Text),
        Column("interpolation_rule_value", Numeric),
        Column("interpolation_rule_text", Text),
    )
    Table(
        "technology_year_constraint",
        md,
        Column("constraint_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id")),
        Column("constraint_type", Text, default="capacity"),
        Column("constraint_value", Numeric),
        Column("bound_type", Text),
        Column("constraint_unit", Text),
    )
    Table(
        "technology_year_constraint_detail",
        md,
        Column("constraint_detail_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id")),
        Column("detail_type", Text, nullable=False),
        Column("detail_value", Numeric),
        Column("detail_unit", Text),
    )
    Table(
        "data_quality_issue",
        md,
        Column("issue_id", Integer, primary_key=True, autoincrement=True),
        Column("raw_row_id", BigInteger, ForeignKey("raw_excel_row.raw_row_id")),
        Column("source_sheet_name", Text),
        Column("excel_row_number", Integer),
        Column("excel_column", Text),
        Column("issue_type", Text, nullable=False),
        Column("original_value", Text),
        Column("issue_message", Text),
    )

    md.drop_all(dbmod.engine)
    md.create_all(dbmod.engine)

    with dbmod.engine.begin() as conn:
        # Dictionaries
        conn.execute(
            text(
                "INSERT INTO sector(sector_code, sector_name) VALUES "
                "('POWER', 'Power'), ('INDUSTRY', 'Industry'), ('PRIMARY', 'Primary')"
            )
        )
        conn.execute(
            text("INSERT INTO geography(geography_code, geography_name) VALUES ('SG', 'Region SG')")
        )
        conn.execute(
            text(
                "INSERT INTO commodity(commodity_code, commodity_set, commodity_description, unit) VALUES "
                "('NGAS01', 'NRG', 'Natural gas for power', 'PJ'), "
                "('COAL01', 'NRG', 'Coal for power', 'PJ'), "
                "('CO2_01', 'ENV', 'Power-sector CO2', 'kt')"
            )
        )

        # raw_excel_row (for raw_row_id trace-back)
        import json as _json

        for i in range(1, 5):
            conn.execute(text("INSERT INTO import_batch(file_name) VALUES ('test.xlsx')"))
            conn.execute(
                text(
                    "INSERT INTO raw_excel_row(import_batch_id, source_sheet_name, "
                    "excel_row_number, raw_cells) "
                    "VALUES (:b, 'Power', :rn, :cells)"
                ).bindparams(b=i, rn=10 + i, cells=_json.dumps({"H": "NGCC01"}))
            )

        # two technology_process rows
        conn.execute(
            text(
                "INSERT INTO technology_process(sector_id, geography_id, technology_code, "
                "technology_description, technology_start_year, technology_lifetime_years) VALUES "
                "(1, 1, 'NGCC01', 'Natural gas combined cycle', 2018, 25), "
                "(1, 1, 'SOLAR01', 'Solar PV', 2018, 25)"
            )
        )

        # technology_year + ecotea_parameter (4 years for NGCC01)
        years = [
            (2018, 1572.78, 56.1, "PJ"),
            (2024, 1500.0, 56.1, "PJ"),
            (2030, 1400.0, 56.1, "PJ"),
            (2040, 1200.0, 56.1, "PJ"),
        ]
        for i, (year, capex, ef, ef_u) in enumerate(years, start=1):
            conn.execute(
                text(
                    "INSERT INTO technology_year(technology_id, data_year, raw_row_id) "
                    "VALUES (1, :y, :rri)"
                ).bindparams(y=year, rri=i)
            )
            conn.execute(
                text(
                    "INSERT INTO technology_year_ecotea_parameter("
                    "technology_year_id, capex, capex_unit, emission_factor, emission_factor_unit) "
                    "VALUES (:tyi, :c, 'GW', :ef, :u)"
                ).bindparams(tyi=i, c=capex, ef=ef, u=ef_u)
            )

        # SOLAR01 one year (different capex, emission_factor=0)
        conn.execute(text("INSERT INTO technology_year(technology_id, data_year) VALUES (2, 2018)"))
        conn.execute(
            text(
                "INSERT INTO technology_year_ecotea_parameter("
                "technology_year_id, capex, capex_unit, emission_factor, emission_factor_unit) "
                "VALUES (5, 2902.6, 'GW', 0.0, 'PJ')"
            )
        )


def teardown_test_db() -> None:
    pass  # in-memory; destroyed when the process ends
