"""
Follow Modeli (Many-to-Many: User ↔ User — Self Referential)
============================================================
PRD Bölüm 10.2 ``follows`` tablosu, bileşik PK (PRD 11.1).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin

if TYPE_CHECKING:
    from app.models.user import User


class Follow(CreatedAtMixin, Base):
    """``follows`` — self-referential M2M (PRD 11.1)."""

    __tablename__ = "follows"

    follower_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    followee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    __table_args__ = (
        # Kendi kendini takip etme engellenir
        CheckConstraint("follower_id <> followee_id", name="no_self_follow"),
    )

    follower: Mapped["User"] = relationship(
        back_populates="following",
        foreign_keys=[follower_id],
    )
    followee: Mapped["User"] = relationship(
        back_populates="followers",
        foreign_keys=[followee_id],
    )

    def __repr__(self) -> str:
        return f"<Follow {self.follower_id} -> {self.followee_id}>"
