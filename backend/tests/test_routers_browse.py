"""HTTP-level tests for /api browse routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import models


# ---------------------------------------------------------------------------
# Seeding helper
# ---------------------------------------------------------------------------
@pytest.fixture()
def seeded_data(db_session, seeded_sectors):
    """Populate enough data to exercise the browse endpoints."""
    # SmallInteger PKs don't autoincrement on SQLite — assign explicitly.
    existing_geo = db_session.query(models.Geography).filter_by(geography_code="SG").one_or_none()
    if existing_geo is None:
        next_geo_id = (db_session.query(models.Geography).count() or 0) + 1
        geo = models.Geography(
            geography_id=next_geo_id,
            geography_code="SG",
            geography_name="Singapore",
        )
        db_session.add(geo)
        db_session.flush()
    else:
        geo = existing_geo

    sector = db_session.query(models.Sector).filter_by(sector_code="POWER").one()

    # Re-use existing test tech if present.
    tech = (
        db_session.query(models.TechnologyProcess)
        .filter_by(technology_code="TEST_TECH")
        .one_or_none()
    )
    if tech is None:
        tech = models.TechnologyProcess(
            sector_id=sector.sector_id,
            geography_id=geo.geography_id,
            technology_code="TEST_TECH",
            technology_description="Test technology",
            technology_start_year=2018,
            technology_lifetime_years=30,
            grade="N/A",
        )
        db_session.add(tech)
        db_session.flush()

    year = (
        db_session.query(models.TechnologyYear)
        .filter_by(technology_id=tech.technology_id, data_year=2020)
        .one_or_none()
    )
    if year is None:
        year = models.TechnologyYear(
            technology_id=tech.technology_id,
            data_year=2020,
        )
        db_session.add(year)
        db_session.flush()

    db_session.commit()
    yield {"sector": sector, "geography": geo, "tech": tech, "year": year}


# ---------------------------------------------------------------------------
# Dictionary endpoints
# ---------------------------------------------------------------------------
class TestSectorList:
    def test_returns_sectors(self, client: TestClient, seeded_sectors):
        response = client.get("/api/sectors")
        assert response.status_code == 200
        codes = {entry["sector_code"] for entry in response.json()}
        assert "POWER" in codes


class TestGeographyList:
    def test_returns_geographies(self, client: TestClient, seeded_data):
        response = client.get("/api/geographies")
        assert response.status_code == 200
        codes = {entry["geography_code"] for entry in response.json()}
        assert "SG" in codes


# ---------------------------------------------------------------------------
# /api/technologies (list)
# ---------------------------------------------------------------------------
class TestTechnologyList:
    def test_returns_seeded_tech(self, client: TestClient, seeded_data):
        response = client.get("/api/technologies")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] >= 1
        codes = {item["technology_code"] for item in body["items"]}
        assert "TEST_TECH" in codes

    def test_filter_by_sector(self, client: TestClient, seeded_data):
        sector_id = seeded_data["sector"].sector_id
        response = client.get(f"/api/technologies?sector_id={sector_id}")
        assert response.status_code == 200
        for item in response.json()["items"]:
            assert item["sector_code"] == "POWER"

    def test_fuzzy_search(self, client: TestClient, seeded_data):
        response = client.get("/api/technologies?q=test")
        assert response.status_code == 200
        codes = {item["technology_code"] for item in response.json()["items"]}
        assert "TEST_TECH" in codes

    def test_pagination(self, client: TestClient, seeded_data):
        response = client.get("/api/technologies?page=1&page_size=1")
        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 1
        assert body["page_size"] == 1
        assert len(body["items"]) <= 1

    def test_invalid_page_size_rejected(self, client: TestClient):
        response = client.get("/api/technologies?page_size=99999")
        assert response.status_code == 422

    def test_filter_by_unknown_geography_returns_empty(self, client: TestClient, seeded_data):
        # 9999 must be within SMALLINT range (max 32767) but unlikely to exist.
        response = client.get("/api/technologies?geography_id=9999")
        assert response.status_code == 200
        assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# /api/technologies/{id}
# ---------------------------------------------------------------------------
class TestTechnologyDetail:
    def test_existing(self, client: TestClient, seeded_data):
        tech_id = seeded_data["tech"].technology_id
        response = client.get(f"/api/technologies/{tech_id}")
        assert response.status_code == 200
        body = response.json()
        assert body["technology_code"] == "TEST_TECH"
        assert body["sector_code"] == "POWER"
        assert body["geography_code"] == "SG"
        assert any(y["data_year"] == 2020 for y in body["years"])

    def test_missing_returns_404(self, client: TestClient, seeded_data):
        # technology_id is BigInteger in PG so big numbers are fine here.
        response = client.get("/api/technologies/9999999")
        assert response.status_code == 404
