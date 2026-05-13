"""HTTP-level tests for /api/imports routes."""

from __future__ import annotations

from io import BytesIO

import openpyxl
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_workbook(sheets: dict[str, list[list[object]]]) -> bytes:
    """Build an EcoTEA-shaped workbook from {sheet_name: rows}.

    Rows are written starting at row 1; the importer treats row 10 and beyond
    as data rows.
    """
    wb = openpyxl.Workbook()
    # Remove the default sheet.
    default = wb.active
    wb.remove(default)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for r_idx, row in enumerate(rows, start=1):
            for c_idx, value in enumerate(row, start=1):
                ws.cell(row=r_idx, column=c_idx, value=value)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _empty_workbook() -> bytes:
    return _build_workbook({"Power": [["header"]]})


# ---------------------------------------------------------------------------
# /api/imports/preview
# ---------------------------------------------------------------------------
class TestPreviewEndpoint:
    def test_rejects_non_excel(self, client: TestClient):
        response = client.post(
            "/api/imports/preview",
            files={"file": ("foo.txt", b"hello", "text/plain")},
        )
        assert response.status_code == 400

    def test_rejects_empty_file(self, client: TestClient):
        response = client.post(
            "/api/imports/preview",
            files={
                "file": (
                    "empty.xlsx",
                    b"",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 400

    def test_preview_known_sheet(self, client: TestClient):
        rows = [["header"] for _ in range(9)]
        # One actual data row at row 10.
        rows.append(["PROC_CODE"])
        wb_bytes = _build_workbook({"Power": rows, "Unknown Sheet": [["x"]]})

        response = client.post(
            "/api/imports/preview",
            files={
                "file": (
                    "wb.xlsx",
                    wb_bytes,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["file_name"] == "wb.xlsx"
        sheets = {entry["sheet_name"]: entry for entry in body["sheets"]}
        assert sheets["Power"]["is_known"] is True
        assert sheets["Power"]["sector_code"] == "POWER"
        assert sheets["Power"]["data_rows"] == 1
        assert sheets["Unknown Sheet"]["is_known"] is False

    def test_corrupt_excel_returns_400(self, client: TestClient):
        response = client.post(
            "/api/imports/preview",
            files={
                "file": (
                    "wb.xlsx",
                    b"not an xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# /api/imports (create)
# ---------------------------------------------------------------------------
class TestCreateImport:
    def test_rejects_non_excel(self, client: TestClient):
        response = client.post(
            "/api/imports",
            files={"file": ("foo.csv", b"a,b,c", "text/csv")},
        )
        assert response.status_code == 400

    def test_rejects_empty(self, client: TestClient):
        response = client.post(
            "/api/imports",
            files={
                "file": (
                    "x.xlsx",
                    b"",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# /api/imports/conflicts
# ---------------------------------------------------------------------------
class TestConflicts:
    def test_endpoint_returns_shape(self, client: TestClient, seeded_sectors):
        response = client.get("/api/imports/conflicts")
        assert response.status_code == 200
        body = response.json()
        # Response shape is stable regardless of how many other tests have
        # produced conflicts before this one ran.
        assert "total_pending" in body
        assert isinstance(body["groups"], list)
        assert body["total_pending"] == len(
            [row for group in body["groups"] for row in group["rows"]]
        )

    def test_resolve_empty_list_rejected(self, client: TestClient):
        response = client.post("/api/imports/conflicts/resolve", json=[])
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# /api/imports/preview/from-conversion
# ---------------------------------------------------------------------------
class TestPreviewFromConversion:
    def test_unknown_token_404(self, client: TestClient):
        response = client.post(
            "/api/imports/preview/from-conversion?token=does-not-exist",
        )
        assert response.status_code == 404

    def test_import_from_unknown_token_404(self, client: TestClient):
        response = client.post(
            "/api/imports/from-conversion?token=missing",
        )
        assert response.status_code == 404
