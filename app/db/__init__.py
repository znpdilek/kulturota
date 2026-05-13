"""
Veritabanı katmanı
==================
SQLAlchemy ``Base`` deklarasyonu, ortak mixin'ler ve session factory'leri.
"""

from app.db.base_class import Base
from app.db.session import SessionLocal, engine

__all__ = ["Base", "SessionLocal", "engine"]
