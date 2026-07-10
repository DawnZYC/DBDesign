"""raw_rows router (M4) — GET /api/raw-rows/{raw_row_id}.

Purpose: source-cell trace-back for chart click events.
  The frontend ECharts dataset encodes raw_row_id as a hidden dimension; when the user
  clicks a data point, it takes that id and calls this endpoint to retrieve the original
  Excel row info (sheet / row number / original cell JSON).

The response contains:
  - raw_row_id / source_sheet_name / excel_row_number / raw_cells (JSONB)
  - import_batch.file_name / imported_at / note (scenario label)
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import models
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["raw-rows"])


# -----------------------------------------------------------------------------
# Response schema
# -----------------------------------------------------------------------------
class ImportBatchBrief(BaseModel):
    """Brief import_batch info (avoid passing through the entire batch table)."""

    import_batch_id: int
    file_name: str
    imported_at: datetime
    note: str | None


class RawRowDetail(BaseModel):
    """Full info for a single raw Excel row."""

    raw_row_id: int
    source_sheet_name: str
    excel_row_number: int
    raw_cells: dict  # JSONB original, kept as a dict
    import_batch: ImportBatchBrief


# -----------------------------------------------------------------------------
# Endpoint
# -----------------------------------------------------------------------------
@router.get(
    "/raw-rows/{raw_row_id}",
    response_model=RawRowDetail,
    summary="Trace back to the source Excel cell (for chart clicks)",
)
def get_raw_row(
    raw_row_id: int,
    db: Session = Depends(get_db),
) -> RawRowDetail:
    """Return the original Excel row info for a given raw_row_id.

    On a chart click, the frontend passes raw_row_id and calls this endpoint to show:
      - source sheet name + Excel row number
      - raw_cells JSONB (original cell content, key=column letter, value=original value)
      - the owning import_batch (file name + import time + scenario note)
    """
    row = db.query(models.RawExcelRow).filter(models.RawExcelRow.raw_row_id == raw_row_id).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"raw_row_id={raw_row_id} does not exist",
        )

    batch = row.batch
    if batch is None:
        # The associated batch was deleted (shouldn't happen with the FK CASCADE; defensive check)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"the import_batch for raw_row_id={raw_row_id} does not exist",
        )

    logger.info(
        "raw_row fetch: id=%d sheet=%s row=%d batch_id=%d",
        raw_row_id,
        row.source_sheet_name,
        row.excel_row_number,
        batch.import_batch_id,
    )

    # Strip M5 meta keys (e.g. "__column_remap__") so the trace shows only real Excel cells.
    raw_cells = {k: v for k, v in (row.raw_cells or {}).items() if not str(k).startswith("__")}

    return RawRowDetail(
        raw_row_id=row.raw_row_id,
        source_sheet_name=row.source_sheet_name,
        excel_row_number=row.excel_row_number,
        raw_cells=raw_cells,
        import_batch=ImportBatchBrief(
            import_batch_id=batch.import_batch_id,
            file_name=batch.file_name,
            imported_at=batch.imported_at,
            note=batch.note,
        ),
    )
