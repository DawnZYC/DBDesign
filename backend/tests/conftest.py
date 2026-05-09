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

from app.main import app


@pytest.fixture(scope="session")
def client() -> TestClient:
    """Reusable FastAPI test client."""
    return TestClient(app)
