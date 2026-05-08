"""Database connection and session factory."""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

_settings = get_settings()


def _engine_kwargs(url: str) -> dict[str, object]:
    """SQLite memory databases need a shared pool; PostgreSQL uses the standard pool."""
    if ":memory:" in url:
        return {
            "future": True,
            "connect_args": {"check_same_thread": False},
            "poolclass": StaticPool,
        }
    if url.startswith(("sqlite", "sqlite+")):
        return {"future": True}
    return {
        "pool_pre_ping": True,
        "pool_size": 5,
        "max_overflow": 10,
        "future": True,
    }


engine = create_engine(_settings.database_url, **_engine_kwargs(_settings.database_url))

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one Session per request, closed at the end."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
