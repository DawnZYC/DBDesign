"""健康检查（含数据库 + LLM 抽象层）。"""
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


@router.get("/api/health", response_model=HealthResponse, summary="健康检查")
def health(
    db: Session = Depends(get_db),
    check_llm: bool = Query(
        default=False,
        description="是否真打一次 LLM 连通性测试（会消耗少量 token）",
    ),
) -> HealthResponse:
    """默认只检查 DB；传 ?check_llm=true 才真打一次 LLM API 测试连通性。"""

    # ---- DB ----
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except SQLAlchemyError as exc:  # 不抛 5xx，前端能直观看到状态
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
            error=f"未知 provider '{provider_name}'",
        )
    elif not configured:
        # 不打实际 API，只报 not_configured
        llm_info = LLMHealth(
            provider=provider_name,
            model=settings.llm_model or cfg.default_model,
            configured=False,
        )
    elif not check_llm:
        # 已配置但不主动连通测试（默认）
        llm_info = LLMHealth(
            provider=provider_name,
            model=settings.llm_model or cfg.default_model,
            configured=True,
            ok=True,  # 至少已配置，乐观默认
        )
    else:
        # 显式要求连通测试
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
    summary="列出全部 LLM provider 及当前配置状态",
)
def list_providers() -> dict:
    """前端 settings 页可用：知道哪些 provider 已就绪、当前活跃哪个。"""
    settings = get_settings()
    return {
        "active": (settings.llm_provider or "openai").lower(),
        "providers": list_available_providers(),
    }
