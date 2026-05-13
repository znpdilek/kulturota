"""
Photo Modeli
============
PRD Bölüm 10.2 - ``photos`` tablosu.
PRD Bölüm 11 - PLACES ||--o{ PHOTOS, USERS ||--o{ PHOTOS, ROUTES nullable bağ.

Soft-delete: ``is_approved`` (PRD 11.1).
EXIF GPS temizliği (PRD 17.3) ETL/uygulama katmanı sorumluluğundadır.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.place import Place
    from app.models.route import Route
    from app.models.user import User


class Photo(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``photos`` — kullanıcı fotoğrafları (PRD 10.2)."""

    __tablename__ = "photos"

    # --- İlişkili tablolar --------------------------------------------------
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # PRD 10.2: route_id nullable
    route_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # --- Dosya / Görsel detayları -------------------------------------------
    url: Mapped[str] = mapped_column(Text, nullable=False)
    thumb_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- EXIF (GPS temizlenmiş, PRD 17.3) -----------------------------------
    exif: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # --- Lisans (PRD 20.4: varsayılan CC BY-NC 4.0) -------------------------
    license: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        server_default="CC BY-NC 4.0",
    )

    # --- Moderasyon / Dedup -------------------------------------------------
    is_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    nsfw_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    phash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # --- İlişkiler ----------------------------------------------------------
    place: Mapped["Place"] = relationship(back_populates="photos")
    user: Mapped["User"] = relationship(back_populates="photos")
    route: Mapped["Route | None"] = relationship()

    def __repr__(self) -> str:
        return f"<Photo id={self.id} place_id={self.place_id}>"
