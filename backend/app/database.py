"""数据库连接 & 会话工厂。"""
from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

_settings = get_settings()


def _engine_kwargs(url: str) -> dict[str, object]:
    """SQLite memory 必须共享连接池；PG 走标准连接池。"""
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
    """所有 ORM 模型的基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：每个请求一个 Session，结束时自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
