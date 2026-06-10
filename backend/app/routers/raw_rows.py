"""raw_rows 路由（M4）— GET /api/raw-rows/{raw_row_id}。

用途：图表点击事件的源单元格反查。
  前端 ECharts dataset 把 raw_row_id 编进隐藏维度，用户点击数据点时
  取出该 id，调本端点拿回原始 Excel 行信息（sheet / 行号 / 原始单元格 JSON）。

响应包含：
  - raw_row_id / source_sheet_name / excel_row_number / raw_cells (JSONB)
  - import_batch.file_name / imported_at / note（情景标签）
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
# 响应 schema
# -----------------------------------------------------------------------------
class ImportBatchBrief(BaseModel):
    """import_batch 的简要信息（避免把整张 batch 表都透传）。"""

    import_batch_id: int
    file_name: str
    imported_at: datetime
    note: str | None


class RawRowDetail(BaseModel):
    """单条原始 Excel 行的完整信息。"""

    raw_row_id: int
    source_sheet_name: str
    excel_row_number: int
    raw_cells: dict  # JSONB 原文，保持 dict 格式
    import_batch: ImportBatchBrief


# -----------------------------------------------------------------------------
# 端点
# -----------------------------------------------------------------------------
@router.get(
    "/raw-rows/{raw_row_id}",
    response_model=RawRowDetail,
    summary="反查源 Excel 单元格（图表点击用）",
)
def get_raw_row(
    raw_row_id: int,
    db: Session = Depends(get_db),
) -> RawRowDetail:
    """根据 raw_row_id 返回原始 Excel 行信息。

    前端图表点击时携带 raw_row_id，调用本端点展示：
      - 来源 sheet 名 + Excel 行号
      - raw_cells JSONB（原始单元格内容，key=列字母，value=原始值）
      - 所属 import_batch（文件名 + 导入时间 + 情景注记）
    """
    row = db.query(models.RawExcelRow).filter(models.RawExcelRow.raw_row_id == raw_row_id).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"raw_row_id={raw_row_id} 不存在",
        )

    batch = row.batch
    if batch is None:
        # 关联 batch 已被删除（理论上外键 CASCADE 不会发生，防御性检查）
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"raw_row_id={raw_row_id} 对应的 import_batch 不存在",
        )

    logger.info(
        "raw_row fetch: id=%d sheet=%s row=%d batch_id=%d",
        raw_row_id,
        row.source_sheet_name,
        row.excel_row_number,
        batch.import_batch_id,
    )

    return RawRowDetail(
        raw_row_id=row.raw_row_id,
        source_sheet_name=row.source_sheet_name,
        excel_row_number=row.excel_row_number,
        raw_cells=row.raw_cells or {},
        import_batch=ImportBatchBrief(
            import_batch_id=batch.import_batch_id,
            file_name=batch.file_name,
            imported_at=batch.imported_at,
            note=batch.note,
        ),
    )
