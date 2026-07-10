"""Verify browsing endpoint contracts with FastAPI TestClient and SQLite, without PostgreSQL.

This checks only route registration, response fields, and filtering behavior.
Use verify_import.py for real business data behavior; it depends on the full PostgreSQL ORM.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import os

# Use an in-memory SQLite database to avoid real PostgreSQL dependencies.
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Key point: emulate JSONB as JSON on SQLite.
from sqlalchemy.dialects import postgresql
import sqlalchemy.types as sa_types

# Let JSONB fall back to JSON on non-PostgreSQL dialects.
postgresql.JSONB.cache_ok = True

import app.database as dbmod
from app import models
from app.main import app

# Reuse the same engine from app.database. SQLite memory databases do not share
# data across connections unless the same engine is used.
engine = dbmod.engine
TestSession = dbmod.SessionLocal


def _create_tables() -> None:
    """Rebuild tables with generic types because SQLite does not support JSONB / TIMESTAMPTZ."""
    from sqlalchemy import (
        Column,
        Integer,
        String,
        Text,
        Numeric,
        ForeignKey,
        Table,
        MetaData,
        SmallInteger,
        BigInteger,
        DateTime,
        JSON,
        UniqueConstraint,
    )

    md = MetaData()

    Table(
        "import_batch", md,
        Column("import_batch_id", Integer, primary_key=True, autoincrement=True),
        Column("file_name", Text, nullable=False),
        Column("file_hash", Text),
        Column("imported_at", DateTime),
        Column("imported_by", Text),
        Column("note", Text),
    )
    Table(
        "raw_excel_row", md,
        Column("raw_row_id", Integer, primary_key=True, autoincrement=True),
        Column("import_batch_id", BigInteger, ForeignKey("import_batch.import_batch_id")),
        Column("source_sheet_name", Text, nullable=False),
        Column("excel_row_number", Integer, nullable=False),
        Column("row_type", Text, nullable=False, default="data"),
        Column("raw_cells", JSON, nullable=False),
        Column("normalized_status", Text, nullable=False, default="pending"),
    )
    Table(
        "sector", md,
        Column("sector_id", Integer, primary_key=True, autoincrement=True),
        Column("sector_code", Text, unique=True, nullable=False),
        Column("sector_name", Text, nullable=False),
    )
    Table(
        "geography", md,
        Column("geography_id", Integer, primary_key=True, autoincrement=True),
        Column("geography_code", Text, unique=True, nullable=False),
        Column("geography_name", Text),
    )
    Table(
        "commodity", md,
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
        "traceability_record", md,
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
        "technology_process", md,
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
        "technology_year", md,
        Column("technology_year_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_id", BigInteger, ForeignKey("technology_process.technology_id")),
        Column("traceability_id", BigInteger, ForeignKey("traceability_record.traceability_id")),
        Column("raw_row_id", BigInteger, ForeignKey("raw_excel_row.raw_row_id")),
        Column("data_year", SmallInteger, nullable=False),
        UniqueConstraint("technology_id", "data_year"),
    )
    Table(
        "technology_year_ecotea_parameter", md,
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id"), primary_key=True),
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
        "technology_year_wp_descriptor", md,
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id"), primary_key=True),
        Column("efficiency_value", Numeric),
        Column("efficiency_text", Text),
        Column("efficiency_unit", Text),
        Column("technology_efficiency", Numeric),
        Column("capacity_to_activity_factor", Numeric),
        Column("heat_rate", Numeric),
    )
    Table(
        "technology_year_commodity", md,
        Column("technology_year_commodity_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id")),
        Column("commodity_id", SmallInteger, ForeignKey("commodity.commodity_id")),
        Column("commodity_order", SmallInteger, nullable=False, default=1),
        Column("commodity_share_value", Numeric),
        Column("commodity_share_text", Text),
        Column("commodity_demand_value", Numeric),
        Column("commodity_demand_text", Text),
        Column("interpolation_rule_value", Numeric),
        Column("interpolation_rule_text", Text),
    )
    Table(
        "technology_year_constraint", md,
        Column("constraint_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id")),
        Column("constraint_type", Text, nullable=False, default="capacity"),
        Column("constraint_value", Numeric),
        Column("bound_type", Text),
        Column("constraint_unit", Text),
    )
    Table(
        "technology_year_constraint_detail", md,
        Column("constraint_detail_id", Integer, primary_key=True, autoincrement=True),
        Column("technology_year_id", BigInteger, ForeignKey("technology_year.technology_year_id")),
        Column("detail_type", Text, nullable=False),
        Column("detail_value", Numeric),
        Column("detail_unit", Text),
    )
    Table(
        "data_quality_issue", md,
        Column("issue_id", Integer, primary_key=True, autoincrement=True),
        Column("raw_row_id", BigInteger, ForeignKey("raw_excel_row.raw_row_id")),
        Column("source_sheet_name", Text),
        Column("excel_row_number", Integer),
        Column("excel_column", Text),
        Column("issue_type", Text, nullable=False),
        Column("original_value", Text),
        Column("issue_message", Text),
    )

    md.create_all(engine)


def _seed() -> None:
    """Seed test data: one sector, one geography, two technologies, and several years."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("INSERT INTO sector(sector_code, sector_name) VALUES ('POWER', 'Power')"))
        conn.execute(text("INSERT INTO sector(sector_code, sector_name) VALUES ('INDUSTRY', 'Industry')"))
        conn.execute(text("INSERT INTO geography(geography_code, geography_name) VALUES ('SG', 'Singapore')"))
        conn.execute(text(
            "INSERT INTO commodity(commodity_code, commodity_set, commodity_description, unit) "
            "VALUES ('PWRNGA', 'NRG', 'Power Natural Gas', 'PJ')"
        ))

        conn.execute(text(
            "INSERT INTO technology_process(sector_id, geography_id, technology_code, "
            "technology_description, technology_start_year, technology_lifetime_years, grade) "
            "VALUES (1, 1, 'PWRNGACCF01', 'Natural gas combined cycle', 2018, 25, NULL)"
        ))
        conn.execute(text(
            "INSERT INTO technology_process(sector_id, geography_id, technology_code, "
            "technology_description, technology_start_year, technology_lifetime_years, grade) "
            "VALUES (2, 1, 'IRFELECAE00', 'Refinery Compressed Air System', 2018, 15, NULL)"
        ))

        # Add two years for PWRNGACCF01.
        conn.execute(text(
            "INSERT INTO technology_year(technology_id, data_year) VALUES (1, 2018)"
        ))
        conn.execute(text(
            "INSERT INTO technology_year(technology_id, data_year) VALUES (1, 2024)"
        ))
        conn.execute(text(
            "INSERT INTO technology_year_ecotea_parameter(technology_year_id, capex, capex_unit) "
            "VALUES (1, 1572.78, 'GW')"
        ))
        conn.execute(text(
            "INSERT INTO technology_year_wp_descriptor(technology_year_id, efficiency_value, efficiency_text) "
            "VALUES (1, 0.497, '0.497')"
        ))
        conn.execute(text(
            "INSERT INTO technology_year_commodity(technology_year_id, commodity_id, "
            "commodity_order, commodity_share_value, commodity_share_text) "
            "VALUES (1, 1, 1, 1.0, '1')"
        ))


def _override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


def main() -> None:
    _create_tables()
    _seed()

    # Replace global engine / SessionLocal with the test versions.
    dbmod.engine = engine
    dbmod.SessionLocal = TestSession
    app.dependency_overrides[dbmod.get_db] = _override_get_db

    client = TestClient(app)

    print("== /api/sectors ==")
    r = client.get("/api/sectors")
    print(f"  status={r.status_code}  body={r.json()}")
    assert r.status_code == 200
    assert any(s["sector_code"] == "POWER" for s in r.json())

    print("\n== /api/geographies ==")
    r = client.get("/api/geographies")
    print(f"  status={r.status_code}  body={r.json()}")
    assert r.status_code == 200

    print("\n== /api/technologies ==")
    r = client.get("/api/technologies")
    body = r.json()
    print(f"  status={r.status_code}  total={body['total']}  items={len(body['items'])}")
    assert r.status_code == 200
    assert body["total"] == 2

    print("\n== /api/technologies?sector_id=1 ==")
    r = client.get("/api/technologies?sector_id=1")
    body = r.json()
    print(f"  status={r.status_code}  total={body['total']}")
    assert body["total"] == 1
    assert body["items"][0]["technology_code"] == "PWRNGACCF01"
    assert body["items"][0]["year_count"] == 2
    assert body["items"][0]["year_min"] == 2018
    assert body["items"][0]["year_max"] == 2024

    print("\n== /api/technologies?q=natural ==")
    r = client.get("/api/technologies?q=natural")
    body = r.json()
    print(f"  status={r.status_code}  total={body['total']}")
    assert body["total"] == 1

    print("\n== /api/technologies/1 (detail) ==")
    r = client.get("/api/technologies/1")
    body = r.json()
    print(
        f"  status={r.status_code}  code={body['technology_code']}  "
        f"years={len(body['years'])}"
    )
    assert r.status_code == 200
    assert body["technology_code"] == "PWRNGACCF01"
    assert len(body["years"]) == 2
    y0 = body["years"][0]
    print(
        f"  year[0]: {y0['data_year']} capex={y0['capex']} "
        f"efficiency_text={y0['efficiency_text']} commodities={y0['commodities']}"
    )
    assert y0["data_year"] == 2018
    assert float(y0["capex"]) == 1572.78
    assert y0["efficiency_text"] == "0.497"
    assert len(y0["commodities"]) == 1
    c0 = y0["commodities"][0]
    assert c0["commodity_code"] == "PWRNGA"
    # Verify extended dictionary fields are included in the response.
    assert c0["commodity_set"] == "NRG", f"expected NRG, got {c0['commodity_set']}"
    assert c0["commodity_description"] == "Power Natural Gas"
    assert c0["unit"] == "PJ"

    print("\n== /api/technologies/999 (404) ==")
    r = client.get("/api/technologies/999")
    print(f"  status={r.status_code}  body={r.json()}")
    assert r.status_code == 404

    print("\nAll browse API contract tests passed ✓")


if __name__ == "__main__":
    main()
