"""
Veritabanı Tipi Yardımcıları
============================
Tekrarlanan SQLAlchemy tip tanımları için ortak factory'ler.
"""

from __future__ import annotations

import enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=enum.Enum)


def pg_enum(enum_cls: type[E], *, name: str) -> SAEnum:
    """
    PostgreSQL ENUM tipini Python enum sınıfının **değerleriyle** (``.value``)
    oluşturur.

    Neden?
    ------
    SQLAlchemy'nin ``Enum`` tipi varsayılan olarak Python enum üyesinin
    *isim*lerini (``PENDING``, ``USER``) DB tarafında ENUM değeri olarak yazar.
    Bizim enum'larımız ise ``str``-değerli (``"pending"``, ``"user"``).
    Bu uyumsuzluk ``server_default=Enum.MEMBER.value`` kullanıldığında
    ``invalid input value for enum`` hatasına yol açar.

    Bu fabrika ``values_callable`` ile DB ENUM değerlerini ``.value``
    üzerinden üreterek tutarlılık sağlar.
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda members: [m.value for m in members],
        native_enum=True,
        create_constraint=False,
        validate_strings=True,
    )
