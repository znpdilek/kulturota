"""
Place Modeli (Gold Set — Canonical Entity)
==========================================
PRD Bölüm 10.1 - ``places`` tablosu (Canonical).
PRD Bölüm 11 - PLACES bir çok tabloyla 1:N ilişkide.

Önemli detaylar:
    * ``koordinat`` = ``geography(Point, 4326)``  → GeoAlchemy2.
    * ``bbox``      = ``geography(Polygon, 4326)`` → opsiyonel, site sınırları.
    * GIST + GIN indeksleri (PRD 10.1).
    * Soft-delete: ``is_published`` (PRD 11.1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from geoalchemy2 import Geography
from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.favorite import Favorite
    from app.models.merge_decision_log import MergeDecisionLog
    from app.models.opening_hours import OpeningHours
    from app.models.photo import Photo
    from app.models.place_tag import PlaceTag
    from app.models.review import Review
    from app.models.route_stop import RouteStop


class Place(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """``places`` — Gold Set canonical entity (PRD 10.1)."""

    __tablename__ = "places"

    # PRD 10.1 mekan_id alanı; ortak ``id`` alanına eşlenir
    # (kod tarafında ``place.id`` ile erişilir, DB tarafında ``id`` kolonudur).
    # Kolon adını "mekan_id" yapmıyoruz; tutarlılık için tüm modellerde "id".

    # --- SEO ----------------------------------------------------------------
    slug: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)

    # --- Çok-dilli isim (PRD 10.1: jsonb) -----------------------------------
    isim: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # --- Kategori (taksonomi) -----------------------------------------------
    kategori: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )

    # --- Geometri (PRD 10.1: PostGIS zorunlu) -------------------------------
    koordinat: Mapped[Any] = mapped_column(
        Geography(geometry_type="POINT", srid=4326, spatial_index=False),
        nullable=False,
    )
    bbox: Mapped[Any | None] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326, spatial_index=False),
        nullable=True,
    )

    # --- Ziyaret bilgisi (PRD 10.1) -----------------------------------------
    # acilis_kapanis, muzekart_gecerli (bool D2 statik), giris_ucretleri
    ziyaret_bilgisi: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Algoritmik etiketler -----------------------------------------------
    etiketler: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )

    # --- Tarihsel + UNESCO --------------------------------------------------
    tarihi_yapim_yili: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unesco: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # --- Görsel + Açıklama --------------------------------------------------
    kapak_foto_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    aciklama: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    aciklama_source: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # wikipedia / llm-gemini-flash-2.0 / manual

    # --- Lisans / Atıf bloğu ------------------------------------------------
    kaynak_atif: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)

    # --- Kalite Skoru (DQ) --------------------------------------------------
    kalite_skoru: Mapped[float | None] = mapped_column(Numeric(3, 2), nullable=True)

    # --- Lineage + Yayın ----------------------------------------------------
    merged_from: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # --- İndeksler (PRD 10.1) -----------------------------------------------
    __table_args__ = (
        Index("ix_places_koordinat_gist", "koordinat", postgresql_using="gist"),
        Index("ix_places_bbox_gist", "bbox", postgresql_using="gist"),
        Index("ix_places_etiketler_gin", "etiketler", postgresql_using="gin"),
        Index("ix_places_kategori_gin", "kategori", postgresql_using="gin"),
        Index(
            "ix_places_isim_gin",
            "isim",
            postgresql_using="gin",
            postgresql_ops={"isim": "jsonb_path_ops"},
        ),
        Index("ix_places_updated_at_desc", text("updated_at DESC")),
    )

    # --- İlişkiler (PRD Bölüm 11) -------------------------------------------
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="place",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="place",
        cascade="all, delete-orphan",  # PRD 11.1: ON DELETE CASCADE
        passive_deletes=True,
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="place",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    opening_hours: Mapped[list["OpeningHours"]] = relationship(
        back_populates="place",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    place_tags: Mapped[list["PlaceTag"]] = relationship(
        back_populates="place",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # PRD 11.1: route_stops.place_id → places ON DELETE RESTRICT
    route_stops: Mapped[list["RouteStop"]] = relationship(
        back_populates="place",
        passive_deletes=True,
    )
    # PRD 11: PLACES ||--o{ MERGE_DECISION_LOG : decided_for
    merge_decisions: Mapped[list["MergeDecisionLog"]] = relationship(
        back_populates="place",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Place id={self.id} slug={self.slug!r}>"
