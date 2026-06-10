"""导入相关路由。"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents.schema_mapper import SchemaMappingRejected
from app.database import get_db
from app.schemas import (
    ConflictListResponse,
    ConflictResolution,
    ConflictResolveResponse,
    FilePreview,
    ImportResult,
)
from app.services.excel_importer import (
    import_excel,
    list_pending_conflicts,
    preview_excel,
    resolve_pending_conflicts,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/imports", tags=["imports"])

ALLOWED_SUFFIXES = (".xlsx", ".xlsm")
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


def _validate_upload(file: UploadFile, file_bytes: bytes) -> None:
    """通用文件校验：扩展名、是否为空、大小上限。"""
    if not file.filename or not file.filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"仅支持 {ALLOWED_SUFFIXES} 类型的文件",
        )
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="文件为空"
        )
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件超过 {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB 上限",
        )


@router.post(
    "/preview",
    response_model=FilePreview,
    status_code=status.HTTP_200_OK,
    summary="预览 Excel 的 sheet 列表（不入库）",
)
async def preview_import(
    file: UploadFile = File(..., description="要预览的 .xlsx 文件"),
    use_llm_mapping: bool = Form(
        default=False,
        description="M5 列对齐是否用 LLM 后端（默认确定性，快且零成本）",
    ),
) -> FilePreview:
    """读取上传文件的 sheet 名称、行数、是否在已知映射表内，并给出 M5 列对齐建议。

    前端用返回的 column_mapping 让用户在列布局变化时做对齐复核。
    """
    file_bytes = await file.read()
    _validate_upload(file, file_bytes)

    try:
        return preview_excel(
            file_bytes=file_bytes,
            file_name=file.filename or "upload.xlsx",
            use_llm_mapping=use_llm_mapping,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("预览失败")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"读取 Excel 失败：{exc!s}",
        ) from exc


@router.post(
    "",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="上传并导入 EcoTEA Excel 文件（可选择 sheet 白名单）",
)
async def create_import(
    file: UploadFile = File(..., description="要导入的 .xlsx 文件"),
    imported_by: str | None = Form(default=None, description="导入操作人（可选）"),
    note: str | None = Form(default=None, description="本次导入备注（可选）"),
    sheets: str | None = Form(
        default=None,
        description="只导入这些 sheet，逗号分隔。为空时导入全部已知 sheet。",
    ),
    column_overrides: str | None = Form(
        default=None,
        description=(
            "M5 列对齐复核结果，JSON 字符串：{sheet: {陌生列: 标准列}}。"
            "给了就按它搬运，不再自动调 Schema-Mapping Agent。"
        ),
    ),
    auto_map_columns: bool = Form(
        default=True,
        description="无 override 且表头非标准时，是否自动调 Schema-Mapping Agent",
    ),
    use_llm_mapping: bool = Form(
        default=False, description="Schema-Mapping Agent 是否用 LLM 后端"
    ),
    db: Session = Depends(get_db),
) -> ImportResult:
    """接收 Excel 文件，同步写入数据库并返回汇总结果。

    sheets 字段示例：`Power,Industry` 或 `Power, Industry`（空格无所谓）。
    column_overrides 示例：`{"Power": {"F": "R", "G": "T"}}`。
    """
    file_bytes = await file.read()
    _validate_upload(file, file_bytes)

    selected_sheets: list[str] | None = None
    if sheets:
        selected_sheets = [s.strip() for s in sheets.split(",") if s.strip()]

    overrides: dict[str, dict[str, str]] | None = None
    if column_overrides:
        try:
            parsed = json.loads(column_overrides)
            if not isinstance(parsed, dict):
                raise ValueError("column_overrides 必须是 JSON 对象")
            overrides = {
                str(sheet): {str(k): str(v) for k, v in mapping.items()}
                for sheet, mapping in parsed.items()
                if isinstance(mapping, dict)
            }
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"column_overrides 解析失败：{exc!s}",
            ) from exc

    try:
        result = import_excel(
            db,
            file_bytes=file_bytes,
            file_name=file.filename or "upload.xlsx",
            imported_by=imported_by,
            note=note,
            selected_sheets=selected_sheets,
            column_overrides=overrides,
            auto_map_columns=auto_map_columns,
            use_llm_mapping=use_llm_mapping,
        )
    except SchemaMappingRejected as exc:
        db.rollback()
        logger.warning("导入被列对齐质量门槛拒绝：%s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("导入失败 (DB 异常)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据库写入失败：{exc!s}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("导入失败 (未知异常)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入失败：{exc!s}",
        ) from exc

    return result


@router.get(
    "/conflicts",
    response_model=ConflictListResponse,
    summary="列出所有待复核的 sector 冲突（按 sheet + A 列值分组）",
)
def get_conflicts(db: Session = Depends(get_db)) -> ConflictListResponse:
    return list_pending_conflicts(db)


@router.post(
    "/conflicts/resolve",
    response_model=ConflictResolveResponse,
    summary="批量提交冲突复核结果",
)
def post_resolve_conflicts(
    resolutions: list[ConflictResolution] = Body(
        ...,
        description="决定列表，每条 {raw_row_id, decision: 'TRUST_SHEET'|'TRUST_A'|'SKIP'}",
    ),
    db: Session = Depends(get_db),
) -> ConflictResolveResponse:
    if not resolutions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resolutions 列表为空",
        )
    try:
        return resolve_pending_conflicts(db, resolutions=resolutions)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("复核冲突时数据库异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"数据库写入失败：{exc!s}",
        ) from exc
