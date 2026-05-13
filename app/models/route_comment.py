"""
RouteComment Modeli
===================
PRD Bölüm 10.2 - ``route_comments`` (standart sosyal etkileşim tablosu).
PRD Bölüm 11 - ROUTES ||--o{ ROUTE_COMMENTS.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.route import Route
    from app.models.user import User


class RouteComment(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``route_comments`` (PRD 10.2)."""

    __tablename__ = "route_comments"

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_flagged: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    route: Mapped["Route"] = relationship(back_populates="comments")
    user: Mapped["User"] = relationship(back_populates="route_comments")

    def __repr__(self) -> str:
        return f"<RouteComment id={self.id} route_id={self.route_id}>"
