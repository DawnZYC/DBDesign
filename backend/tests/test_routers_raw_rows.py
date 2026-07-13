"""raw_rows trace-back endpoint tests (GET /api/raw-rows/{id})."""

from __future__ import annotations

from app import models


def _make_raw_row(db_session, raw_cells: dict) -> models.RawExcelRow:
    batch = models.ImportBatch(file_name="wp1.xlsx", note="scenario A")
    db_session.add(batch)
    db_session.flush()
    row = models.RawExcelRow(
        import_batch_id=batch.import_batch_id,
        source_sheet_name="Power",
        excel_row_number=12,
        raw_cells=raw_cells,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_get_raw_row_not_found(client):
    resp = client.get("/api/raw-rows/999999")
    assert resp.status_code == 404


def test_get_raw_row_returns_cells_and_batch(client, db_session):
    row = _make_raw_row(db_session, {"H": "PWR-COAL-01", "R": "1500"})

    resp = client.get(f"/api/raw-rows/{row.raw_row_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["source_sheet_name"] == "Power"
    assert body["excel_row_number"] == 12
    assert body["raw_cells"] == {"H": "PWR-COAL-01", "R": "1500"}
    assert body["import_batch"]["file_name"] == "wp1.xlsx"
    assert body["import_batch"]["note"] == "scenario A"


def test_get_raw_row_strips_m5_meta_keys(client, db_session):
    row = _make_raw_row(
        db_session,
        {"H": "PWR-SOLAR-01", "__column_remap__": {"S": "R"}, "__anything__": 1},
    )

    resp = client.get(f"/api/raw-rows/{row.raw_row_id}")
    body = resp.json()
    assert body["raw_cells"] == {"H": "PWR-SOLAR-01"}
