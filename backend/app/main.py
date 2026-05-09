"""FastAPI application entry point."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import browse, health, imports

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(
    title="EcoTEA WP1 Import API",
    description="Import EcoTEA Excel data into a PostgreSQL schema with 15 tables.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(imports.router)
app.include_router(browse.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "EcoTEA WP1 Import API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
