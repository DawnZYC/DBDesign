"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import browse, chat, convert, health, imports, rag, raw_rows

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(
    title="SG-TIMES Multi-Agent Analysis Platform",
    description=(
        "EcoTEA WP1 data import tool + LangGraph 4-agent analysis system.\n\n"
        "Natural-language query -> SQL execution -> interpretation -> ECharts "
        "visualization (SSE streaming), plus VT-to-EcoTEA workbook conversion."
    ),
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(convert.router)  # VT -> EcoTEA workbook conversion (from main)
app.include_router(imports.router)
app.include_router(browse.router)
app.include_router(rag.router)  # M1: POST /api/rag/search
app.include_router(chat.router)  # M3: POST /api/chat/stream (SSE)
app.include_router(raw_rows.router)  # M4: GET /api/raw-rows/{id} (chart cell trace)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "EcoTEA WP1 Import API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
