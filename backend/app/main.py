"""FastAPI 应用入口。"""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import browse, chat, health, imports, rag, raw_rows

settings = get_settings()

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

app = FastAPI(
    title="SG-TIMES Multi-Agent 智能分析平台",
    description=(
        "EcoTEA WP1 数据导入工具 + LangGraph 4-Agent 智能分析系统。\n\n"
        "主要能力：自然语言查询 → SQL 执行 → 数据解读 → ECharts 可视化（SSE 流式）"
    ),
    version="0.2.0",
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
app.include_router(rag.router)
app.include_router(chat.router)      # M3: POST /api/chat/stream (SSE)
app.include_router(raw_rows.router)  # M4: GET /api/raw-rows/{id} (图表反查源单元格)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "EcoTEA WP1 Import API",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }
