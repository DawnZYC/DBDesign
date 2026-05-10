"""Import routes."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.routers.convert import get_artefact as get_conversion_artefact
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
    """Common upload validation for suffix, empty content, and size limit."""
    if not file.filename or not file.filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {ALLOWED_SUFFIXES} files are supported",
        )
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty")
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB limit",
        )


@router.post(
    "/preview",
    response_model=FilePreview,
    status_code=status.HTTP_200_OK,
    summary="Preview Excel sheet list without writing to the database",
)
async def preview_import(
    file: UploadFile = File(..., description=".xlsx file to preview"),
) -> FilePreview:
    """Read sheet names, row counts, and known mapping status for sheet selection."""
    file_bytes = await file.read()
    _validate_upload(file, file_bytes)

    try:
        return preview_excel(file_bytes=file_bytes, file_name=file.filename or "upload.xlsx")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Preview failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read Excel: {exc!s}",
        ) from exc


@router.post(
    "",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and import an EcoTEA Excel file with an optional sheet allowlist",
)
async def create_import(
    file: UploadFile = File(..., description=".xlsx file to import"),
    imported_by: str | None = Form(default=None, description="Importer name, optional"),
    note: str | None = Form(default=None, description="Import note, optional"),
    sheets: str | None = Form(
        default=None,
        description="Comma-separated sheet names to import. Empty imports all known sheets.",
    ),
    db: Session = Depends(get_db),
) -> ImportResult:
    """Receive an Excel file, write it to the database synchronously, and return a summary.

    Example sheets value: `Power,Industry` or `Power, Industry`; spaces are ignored.
    """
    file_bytes = await file.read()
    _validate_upload(file, file_bytes)

    selected_sheets: list[str] | None = None
    if sheets:
        selected_sheets = [s.strip() for s in sheets.split(",") if s.strip()]

    try:
        result = import_excel(
            db,
            file_bytes=file_bytes,
            file_name=file.filename or "upload.xlsx",
            imported_by=imported_by,
            note=note,
            selected_sheets=selected_sheets,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Import failed (database error)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed: {exc!s}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Import failed (unknown error)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {exc!s}",
        ) from exc

    return result


@router.post(
    "/preview/from-conversion",
    response_model=FilePreview,
    summary="Preview a previously converted EcoTEA workbook by token (no re-upload).",
)
def preview_from_conversion(
    token: str = Query(..., description="Token returned by POST /api/convert."),
) -> FilePreview:
    artefact = get_conversion_artefact(token)
    file_bytes = artefact.output_path.read_bytes()
    try:
        return preview_excel(file_bytes=file_bytes, file_name=artefact.download_name)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Preview from conversion failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read the converted workbook: {exc!s}",
        ) from exc


@router.post(
    "/from-conversion",
    response_model=ImportResult,
    status_code=status.HTTP_201_CREATED,
    summary="Import a previously converted EcoTEA workbook by token (no re-upload).",
)
def import_from_conversion(
    token: str = Query(..., description="Token returned by POST /api/convert."),
    imported_by: str | None = Form(default=None),
    note: str | None = Form(default=None),
    sheets: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> ImportResult:
    artefact = get_conversion_artefact(token)
    file_bytes = artefact.output_path.read_bytes()

    selected_sheets: list[str] | None = None
    if sheets:
        selected_sheets = [s.strip() for s in sheets.split(",") if s.strip()]

    try:
        return import_excel(
            db,
            file_bytes=file_bytes,
            file_name=artefact.download_name,
            imported_by=imported_by,
            note=note,
            selected_sheets=selected_sheets,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Import from conversion failed (database error)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed: {exc!s}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.exception("Import from conversion failed (unknown error)")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import failed: {exc!s}",
        ) from exc


@router.get(
    "/conflicts",
    response_model=ConflictListResponse,
    summary="List sector conflicts pending review, grouped by sheet and column A value",
)
def get_conflicts(db: Session = Depends(get_db)) -> ConflictListResponse:
    return list_pending_conflicts(db)


@router.post(
    "/conflicts/resolve",
    response_model=ConflictResolveResponse,
    summary="Submit conflict review decisions in bulk",
)
def post_resolve_conflicts(
    resolutions: list[ConflictResolution] = Body(
        ...,
        description="Decision list. Each item is {raw_row_id, decision: 'TRUST_SHEET'|'TRUST_A'|'SKIP'}",
    ),
    db: Session = Depends(get_db),
) -> ConflictResolveResponse:
    if not resolutions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="resolutions list is empty",
        )
    try:
        return resolve_pending_conflicts(db, resolutions=resolutions)
    except SQLAlchemyError as exc:
        db.rollback()
        logger.exception("Database error while reviewing conflicts")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database write failed: {exc!s}",
        ) from exc
