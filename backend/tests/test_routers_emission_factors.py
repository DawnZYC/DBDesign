"""Manual emission-factor upsert endpoint tests (PUT /api/technologies/{id}/emission-factors)."""

from __future__ import annotations

from app import models


def _make_technology(db_session, code: str = "PWR-COAL-EF") -> models.TechnologyProcess:
    sector = db_session.query(models.Sector).filter_by(sector_code="POWER").one()
    geo = db_session.query(models.Geography).filter_by(geography_code="SG").first()
    if geo is None:
        geo = models.Geography(geography_code="SG", geography_name="Singapore")
        db_session.add(geo)
        db_session.flush()
    tech = models.TechnologyProcess(
        sector_id=sector.sector_id,
        geography_id=geo.geography_id,
        technology_code=code,
    )
    db_session.add(tech)
    db_session.commit()
    return tech


def test_upsert_unknown_technology_404(client):
    resp = client.put(
        "/api/technologies/999999/emission-factors",
        json={"data_year": 2030, "emission_factor": 0.5},
    )
    assert resp.status_code == 404


def test_upsert_creates_year_and_parameter(client, db_session, seeded_sectors):
    tech = _make_technology(db_session, "PWR-COAL-EF1")

    resp = client.put(
        f"/api/technologies/{tech.technology_id}/emission-factors",
        json={"data_year": 2030, "emission_factor": 0.85, "emission_factor_unit": " kt/PJ "},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["technology_code"] == "PWR-COAL-EF1"
    assert body["data_year"] == 2030
    assert float(body["emission_factor"]) == 0.85
    assert body["emission_factor_unit"] == "kt/PJ"  # whitespace stripped

    param = db_session.get(models.TechnologyYearEcoteaParameter, body["technology_year_id"])
    assert float(param.emission_factor) == 0.85


def test_upsert_existing_year_updates_in_place(client, db_session, seeded_sectors):
    tech = _make_technology(db_session, "PWR-COAL-EF2")
    url = f"/api/technologies/{tech.technology_id}/emission-factors"

    first = client.put(url, json={"data_year": 2035, "emission_factor": 0.5})
    assert first.json()["created"] is True

    second = client.put(url, json={"data_year": 2035, "emission_factor": 0.6})
    body = second.json()
    assert body["created"] is False
    assert float(body["emission_factor"]) == 0.6
    # Same anchor row is reused
    assert body["technology_year_id"] == first.json()["technology_year_id"]


def test_upsert_null_value_clears_the_factor(client, db_session, seeded_sectors):
    tech = _make_technology(db_session, "PWR-COAL-EF3")
    url = f"/api/technologies/{tech.technology_id}/emission-factors"

    client.put(url, json={"data_year": 2040, "emission_factor": 1.2, "emission_factor_unit": "kt"})
    resp = client.put(url, json={"data_year": 2040, "emission_factor": None})
    assert resp.status_code == 200
    body = resp.json()
    assert body["emission_factor"] is None
    assert body["emission_factor_unit"] is None

    param = db_session.get(models.TechnologyYearEcoteaParameter, body["technology_year_id"])
    db_session.refresh(param)
    assert param.emission_factor is None
