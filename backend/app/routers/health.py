"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["meta"])


@router.get("/api/health", response_model=HealthResponse, summary="Health check")
def health(db: Session = Depends(get_db)) -> HealthResponse:
    try:
        db.execute(text("SELECT 1"))
        db_status = "ok"
    except SQLAlchemyError as exc:  # Do not raise 5xx so the frontend can display the state.
        db_status = f"error: {exc!s}"
    return HealthResponse(status="ok", database=db_status)
