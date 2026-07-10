"""Health check (database + LLM abstraction layer)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.llm import (
    PROVIDER_REGISTRY,
    list_available_providers,
    test_connectivity,
)
from app.schemas import HealthResponse, LLMHealth

logger = logging.getLogger(__name__)
router = APIRouter(tags=["meta"])


@router.get("/api/health", response_model=HealthResponse, summary="Health check")
def health(
    db: Session = Depends(get_db),
    check_llm: bool = Query(
        default=False,
        description="Whether to actually run an LLM connectivity test (consumes a few tokens)",
    ),
) -> HealthResponse:
    """By default only checks the DB; pass ?check_llm=true to actually hit the LLM API."""

    # ---- DB ----
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except SQLAlchemyError as exc:  # don't raise 5xx, so the frontend can see the status directly
        db_status = f"error: {exc!s}"

    # ---- LLM ----
    settings = get_settings()
    provider_name = (settings.llm_provider or "openai").lower()
    cfg = PROVIDER_REGISTRY.get(provider_name)
    configured = bool(cfg) and bool(getattr(settings, cfg.api_key_field, None)) if cfg else False
    llm_info: LLMHealth | None

    if cfg is None:
        llm_info = LLMHealth(
            provider=provider_name,
            configured=False,
            error=f"Unknown provider '{provider_name}'",
        )
    elif not configured:
        # Don't hit the real API; just report not_configured
        llm_info = LLMHealth(
            provider=provider_name,
            model=settings.llm_model or cfg.default_model,
            configured=False,
        )
    elif not check_llm:
        # Configured but no active connectivity test (default)
        llm_info = LLMHealth(
            provider=provider_name,
            model=settings.llm_model or cfg.default_model,
            configured=True,
            ok=True,  # at least configured; optimistic default
        )
    else:
        # Connectivity test explicitly requested
        result = test_connectivity()
        llm_info = LLMHealth(
            provider=result.get("provider", provider_name),
            model=result.get("model"),
            configured=True,
            ok=result.get("ok", False),
            latency_ms=result.get("latency_ms"),
            error=result.get("error"),
        )

    return HealthResponse(status="ok", database=db_status, llm=llm_info)


@router.get(
    "/api/llm/providers",
    summary="List all LLM providers and their current config status",
)
def list_providers() -> dict:
    """For the frontend settings page: know which providers are ready and which is active."""
    settings = get_settings()
    return {
        "active": (settings.llm_provider or "openai").lower(),
        "providers": list_available_providers(),
    }
