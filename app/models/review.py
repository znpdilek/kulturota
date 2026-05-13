"""
Review Modeli
=============
PRD Bölüm 10.2 - ``reviews`` tablosu.
PRD Bölüm 11.1 - ``reviews.place_id → places(mekan_id)`` ON DELETE CASCADE.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.place import Place
    from app.models.user import User


class Review(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``reviews`` — kullanıcı yorum + puan (PRD 10.2)."""

    __tablename__ = "reviews"

    # PRD 11.1: ON DELETE CASCADE
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

    # --- İçerik --------------------------------------------------------------
    rating: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    visited_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Sosyal sayaçlar ----------------------------------------------------
    helpful_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # --- AI moderasyon (PRD 9.x, 14.3) --------------------------------------
    language: Mapped[str | None] = mapped_column(String(8), nullable=True)
    toxicity_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    __table_args__ = (
        # PRD 10.2: rating smallint 1-5
        CheckConstraint("rating BETWEEN 1 AND 5", name="rating_range"),
        # Adım 8 (Sosyal MVP): bir kullanıcı bir mekana yalnızca 1 yorum.
        # Yarış koşullarına karşı DB seviyesinde son savunma hattı; servis
        # katmanı da aynı kuralı önceden kontrol eder.
        UniqueConstraint("place_id", "user_id", name="uq_reviews_place_user"),
    )

    # --- İlişkiler ----------------------------------------------------------
    place: Mapped["Place"] = relationship(back_populates="reviews")
    user: Mapped["User"] = relationship(back_populates="reviews")

    def __repr__(self) -> str:
        return f"<Review id={self.id} place_id={self.place_id} rating={self.rating}>"
