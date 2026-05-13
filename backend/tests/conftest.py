"""Pytest fixtures shared by the backend test suite.

Tests run against an in-memory SQLite database by default so they need no
external services. Integration tests that must hit real PostgreSQL should be
marked with ``@pytest.mark.integration`` and provided their own DSN via the
``DATABASE_URL`` environment variable in CI.
"""

from __future__ import annotations

import os

# IMPORTANT: override DATABASE_URL *before* the application modules import
# config.get_settings(), which is cached with lru_cache.
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("ALLOWED_ORIGINS", "http://localhost:5173")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.sqlite.base import SQLiteTypeCompiler

# PostgreSQL JSONB has no native SQLite representation, but for in-memory
# tests we want the schema to build anyway. Teach the SQLite type compiler
# to render JSONB as TEXT.
def _visit_JSONB(self, type_, **kw):  # noqa: N802
    return "TEXT"


# SQLite only auto-increments columns declared as ``INTEGER PRIMARY KEY``.
# The production schema uses BigInteger / SmallInteger; for tests we render
# them as plain INTEGER so primary keys auto-populate.
def _visit_BIGINT(self, type_, **kw):  # noqa: N802
    return "INTEGER"


def _visit_SMALLINT(self, type_, **kw):  # noqa: N802
    return "INTEGER"


SQLiteTypeCompiler.visit_JSONB = _visit_JSONB
SQLiteTypeCompiler.visit_BIGINT = _visit_BIGINT
SQLiteTypeCompiler.visit_big_integer = _visit_BIGINT
SQLiteTypeCompiler.visit_SMALLINT = _visit_SMALLINT
SQLiteTypeCompiler.visit_small_integer = _visit_SMALLINT

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app import models  # noqa: E402,F401  # populate Base.metadata


@pytest.fixture(scope="session", autouse=True)
def _create_schema() -> None:
    """Build the full schema once per session so DB-backed routes work."""
    Base.metadata.create_all(bind=engine)


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Reusable FastAPI test client."""
    return TestClient(app)


@pytest.fixture()
def db_session():
    """Provide a Session for tests that need direct DB access."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture()
def seeded_sectors(db_session):
    """Populate the sector dictionary so importer/browse tests have data."""
    existing = {s.sector_code for s in db_session.query(models.Sector).all()}
    for code, name in [
        ("POWER", "Power"),
        ("INDUSTRY", "Industry"),
        ("PRIMARY", "Primary"),
        ("TRANSPORT", "Transport"),
        ("WATER", "Water"),
        ("WASTE", "Waste"),
        ("BUILDING", "Building"),
        ("HOUSEHOLD", "Household"),
        ("AGRI", "Agri"),
        ("INFOCOMM", "InfoComm"),
    ]:
        if code not in existing:
            db_session.add(models.Sector(sector_code=code, sector_name=name))
    db_session.commit()
    yield
