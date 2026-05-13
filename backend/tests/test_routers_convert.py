"""HTTP-level tests for /api/convert routes."""

from __future__ import annotations

from io import BytesIO
from unittest.mock import patch

import openpyxl
import pytest
from fastapi.testclient import TestClient

from app.converters.base_model import PowerRecord
from app.routers import convert as convert_router


# ---------------------------------------------------------------------------
# /api/convert/models
# ---------------------------------------------------------------------------
class TestListModels:
    def test_returns_registered_models(self, client: TestClient):
        response = client.get("/api/convert/models")
        assert response.status_code == 200
        body = response.json()
        keys = {item["key"] for item in body}
        assert "VT_SG_PWR" in keys
        assert "VT_SG_PRI" in keys

    def test_each_entry_has_required_fields(self, client: TestClient):
        response = client.get("/api/convert/models")
        assert response.status_code == 200
        for item in response.json():
            for k in ("key", "label", "sector", "description"):
                assert k in item

    def test_handles_internal_error_gracefully(self, client: TestClient):
        with patch.object(
            convert_router,
            "get_available_models",
            side_effect=RuntimeError("boom"),
        ):
            response = client.get("/api/convert/models")
        assert response.status_code == 500
        assert "boom" in response.json()["detail"]


# ---------------------------------------------------------------------------
# /api/convert (upload)
# ---------------------------------------------------------------------------
def _make_workbook_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws["A1"] = "stub"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCreateConversion:
    def test_rejects_non_excel_filename(self, client: TestClient):
        response = client.post(
            "/api/convert",
            data={"model_key": "VT_SG_PWR"},
            files={"vt_file": ("source.txt", b"not excel", "text/plain")},
        )
        assert response.status_code == 400

    def test_rejects_empty_file(self, client: TestClient):
        response = client.post(
            "/api/convert",
            data={"model_key": "VT_SG_PWR"},
            files={
                "vt_file": (
                    "source.xlsx",
                    b"",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 400

    def test_propagates_unknown_model_as_400(self, client: TestClient):
        response = client.post(
            "/api/convert",
            data={"model_key": "NOPE"},
            files={
                "vt_file": (
                    "source.xlsx",
                    _make_workbook_bytes(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        # The engine reports the unknown model, which surfaces as 400.
        assert response.status_code == 400

    def test_success_with_stubbed_engine(self, client: TestClient, tmp_path):
        # Patch the engine.convert function so we don't need real VT data.
        out_file = tmp_path / "EcoTEA_source_converted.xlsx"
        out_file.write_bytes(b"FAKE_XLSX")

        def fake_convert(*, model_name, vt_file_path, template_path, output_path):
            # Pretend we wrote something at output_path.
            with open(output_path, "wb") as fh:
                fh.write(b"FAKE_XLSX")
            return {
                "success": True,
                "row_count": 5,
                "sheet_name": "Power",
                "errors": [],
            }

        with patch.object(convert_router, "run_convert", side_effect=fake_convert):
            response = client.post(
                "/api/convert",
                data={"model_key": "VT_SG_PWR"},
                files={
                    "vt_file": (
                        "source.xlsx",
                        _make_workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
            )

        assert response.status_code == 201
        body = response.json()
        assert body["row_count"] == 5
        assert body["sheet_name"] == "Power"
        assert body["download_token"]


# ---------------------------------------------------------------------------
# /api/convert/download/{token}
# ---------------------------------------------------------------------------
class TestDownload:
    def test_unknown_token_returns_404(self, client: TestClient):
        response = client.get("/api/convert/download/does-not-exist")
        assert response.status_code == 404
