"""Smoke tests for the /api/health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_200(client: TestClient) -> None:
    """The endpoint should always return 200, even when the database is down."""
    response = client.get("/api/health")
    assert response.status_code == 200


def test_health_payload_shape(client: TestClient) -> None:
    """The response must expose ``status`` and ``database`` fields."""
    payload = client.get("/api/health").json()
    assert payload["status"] == "ok"
    assert "database" in payload


def test_root_returns_metadata(client: TestClient) -> None:
    """The root route should expose service identity and docs links."""
    payload = client.get("/").json()
    assert payload["service"] == "EcoTEA WP1 Import API"
    assert payload["docs"] == "/docs"
