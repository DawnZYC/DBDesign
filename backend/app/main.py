"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    browse,
    chat,
    convert,
    emission_factors,
    health,
    imports,
    rag,
    raw_rows,
)

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(
    title="Strata — Multi-Agent Energy Model Analytics",
    description=(
        "Strata: a LangGraph multi-agent analysis system over the EcoTEA WP1 energy-model "
        "dataset.\n\n"
        "Natural-language query -> SQL execution -> interpretation -> ECharts "
        "visualization (SSE streaming), plus VT-to-EcoTEA workbook conversion."
    ),
    version="0.3.0",
)

# A wildcard origin cannot be combined with credentials (browsers reject it per the
# CORS spec), so disable credentials when origins are "*".
_cors_origins = settings.cors_origins
_allow_credentials = "*" not in _cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Security response headers on the backend itself, so a client hitting the API
# directly (not just through the nginx proxy) still gets them. Clears ZAP
# baseline alerts 10021 (X-Content-Type-Options) and the CORP instance of 90004
# on the OpenAPI API scan. `setdefault` avoids clobbering headers a route sets.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Referrer-Policy": "no-referrer",
}


@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    return response

app.include_router(health.router)
app.include_router(convert.router)  # VT -> EcoTEA workbook conversion (from main)
app.include_router(imports.router)
app.include_router(browse.router)
app.include_router(rag.router)  # M1: POST /api/rag/search
app.include_router(chat.router)  # M3: POST /api/chat/stream (SSE)
app.include_router(raw_rows.router)  # M4: GET /api/raw-rows/{id} (chart cell trace)
app.include_router(emission_factors.router)  # PUT /api/technologies/{id}/emission-factors


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "EcoTEA WP1 Import API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
