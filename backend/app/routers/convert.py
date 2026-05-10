"""Convert routes: VT model files -> EcoTEA workbook.

The conversion produces a real .xlsx in a server-side cache. The cache is
keyed by an opaque token so the frontend can:
  - download the file (Convert step), and / or
  - hand it off to the importer without re-uploading (handoff endpoints in
    :mod:`app.routers.imports`).
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.converters.engine import convert as run_convert, get_available_models
from app.schemas import ConvertModelInfo, ConvertResult


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/convert", tags=["convert"])

ALLOWED_SUFFIXES = (".xlsx", ".xlsm", ".xls")
MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB

# Bundled EcoTEA template ships with the backend so users do not have to
# re-upload it for every conversion. They may still upload their own.
DEFAULT_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "ecotea_template.xlsx"

# All conversion artefacts live in a per-process tmp dir so they vanish on
# restart but persist across HTTP calls.
_CACHE_ROOT = Path(tempfile.gettempdir()) / "ecotea_convert_cache"
_CACHE_ROOT.mkdir(parents=True, exist_ok=True)


@dataclass
class ConversionArtefact:
    """One entry in the in-memory cache of converted files."""

    token: str
    output_path: Path
    download_name: str
    row_count: int
    sheet_name: str
    model_key: str
    source_file_name: str
    template_file_name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


_cache_lock = Lock()
_artefact_cache: dict[str, ConversionArtefact] = {}


def get_artefact(token: str) -> ConversionArtefact:
    """Return the cached artefact for ``token`` or raise 404."""
    with _cache_lock:
        artefact = _artefact_cache.get(token)
    if artefact is None or not artefact.output_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Converted file not found or has expired.",
        )
    return artefact


def _store_artefact(artefact: ConversionArtefact) -> None:
    with _cache_lock:
        _artefact_cache[artefact.token] = artefact


def _validate_upload(file: UploadFile, file_bytes: bytes, *, label: str) -> None:
    if not file.filename or not file.filename.lower().endswith(ALLOWED_SUFFIXES):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} must be an Excel file ({', '.join(ALLOWED_SUFFIXES)}).",
        )
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{label} is empty.",
        )
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{label} exceeds the {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB limit.",
        )


@router.get(
    "/models",
    response_model=list[ConvertModelInfo],
    summary="List the registered VT model converters.",
)
def list_models() -> list[ConvertModelInfo]:
    try:
        return [ConvertModelInfo(**info) for info in get_available_models()]
    except Exception as exc:  # noqa: BLE001
        # The metadata listing should never raise — but if something does, we
        # log it server-side and surface a readable detail to the UI rather
        # than a bare 500 response.
        logger.exception("Failed to list convert models")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to list converters: {exc!s}",
        ) from exc


@router.post(
    "",
    response_model=ConvertResult,
    status_code=status.HTTP_201_CREATED,
    summary="Convert a VT source file into an EcoTEA workbook.",
)
async def create_conversion(
    model_key: str = Form(..., description="Converter key from /api/convert/models."),
    vt_file: UploadFile = File(..., description="VT source workbook to convert."),
    ecotea_template: UploadFile | None = File(
        default=None,
        description=(
            "Optional EcoTEA template; if omitted the bundled template is used."
        ),
    ),
) -> ConvertResult:
    vt_bytes = await vt_file.read()
    _validate_upload(vt_file, vt_bytes, label="Source file")

    template_path: Path
    template_name: str

    work_dir = _CACHE_ROOT / uuid.uuid4().hex
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        if ecotea_template is not None and ecotea_template.filename:
            tmpl_bytes = await ecotea_template.read()
            _validate_upload(ecotea_template, tmpl_bytes, label="EcoTEA template")
            template_path = work_dir / f"template_{ecotea_template.filename}"
            template_path.write_bytes(tmpl_bytes)
            template_name = ecotea_template.filename
        else:
            if not DEFAULT_TEMPLATE_PATH.exists():
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="No EcoTEA template was supplied and the bundled template is missing.",
                )
            template_path = DEFAULT_TEMPLATE_PATH
            template_name = DEFAULT_TEMPLATE_PATH.name

        vt_path = work_dir / f"source_{vt_file.filename}"
        vt_path.write_bytes(vt_bytes)

        stem = Path(vt_file.filename or "source").stem
        download_name = f"EcoTEA_{stem}_converted.xlsx"
        output_path = work_dir / download_name

        result = run_convert(
            model_name=model_key,
            vt_file_path=str(vt_path),
            template_path=str(template_path),
            output_path=str(output_path),
        )

        if not result.get("success"):
            shutil.rmtree(work_dir, ignore_errors=True)
            errors = result.get("errors") or ["Unknown conversion error."]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="; ".join(errors),
            )

        token = uuid.uuid4().hex
        artefact = ConversionArtefact(
            token=token,
            output_path=output_path,
            download_name=download_name,
            row_count=int(result["row_count"]),
            sheet_name=str(result.get("sheet_name") or "Power"),
            model_key=model_key,
            source_file_name=vt_file.filename or "source.xlsx",
            template_file_name=template_name,
        )
        _store_artefact(artefact)

        return ConvertResult(
            download_token=token,
            download_name=download_name,
            row_count=artefact.row_count,
            sheet_name=artefact.sheet_name,
            model_key=model_key,
            source_file_name=artefact.source_file_name,
            template_file_name=artefact.template_file_name,
            bytes=output_path.stat().st_size,
            created_at=artefact.created_at,
        )

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(work_dir, ignore_errors=True)
        logger.exception("Conversion failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Conversion failed: {exc!s}",
        ) from exc


@router.get(
    "/download/{token}",
    summary="Download a converted EcoTEA workbook.",
)
def download_conversion(token: str):
    from fastapi.responses import FileResponse

    artefact = get_artefact(token)
    return FileResponse(
        path=str(artefact.output_path),
        filename=artefact.download_name,
        media_type=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
    )
