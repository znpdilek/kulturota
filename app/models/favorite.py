"""
Favorite Modeli (Many-to-Many: User ↔ Place)
============================================
PRD Bölüm 10.2 ``favorites`` tablosu, bileşik PK (PRD 11.1).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.models.place import Place
    from app.models.user import User


class Favorite(CreatedAtMixin, Base):
    """``favorites`` — M2M (user_id, place_id) bileşik PK (PRD 11.1)."""

    __tablename__ = "favorites"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user: Mapped["User"] = relationship(back_populates="favorites")
    place: Mapped["Place"] = relationship(back_populates="favorites")

    def __repr__(self) -> str:
        return f"<Favorite user_id={self.user_id} place_id={self.place_id}>"
