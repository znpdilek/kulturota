"""
Veritabanı Session Yönetimi
===========================
Senkron SQLAlchemy ``Engine`` ve ``SessionLocal`` factory tanımları.
FastAPI bağımlılığı (Depends) bu modüldeki ``get_db`` üzerinden çalışacak.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends için DB session sağlayıcı."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
