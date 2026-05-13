"""
SQLAlchemy 2.x Declarative Base
================================
Tüm ORM modellerinin türeyeceği taban sınıf. ``MetaData`` üzerinde
tutarlı bir naming convention tanımlanır (Alembic autogenerate temizliği için).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# Alembic autogenerate'in tutarlı isimlendirme üretebilmesi için
# (PostgreSQL pratik standardı):
NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Tüm modellerin ortak ata sınıfı."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
