"""
RouteLike Modeli (Many-to-Many: User ↔ Route)
=============================================
PRD Bölüm 10.2 - ``route_likes`` (standart sosyal etkileşim tablosu).
PRD Bölüm 11 - ROUTES ||--o{ ROUTE_LIKES.
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
    from app.models.route import Route
    from app.models.user import User


class RouteLike(CreatedAtMixin, Base):
    """``route_likes`` — bileşik PK ile M2M (PRD 10.2)."""

    __tablename__ = "route_likes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routes.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user: Mapped["User"] = relationship(back_populates="route_likes")
    route: Mapped["Route"] = relationship(back_populates="likes")

    def __repr__(self) -> str:
        return f"<RouteLike user_id={self.user_id} route_id={self.route_id}>"
