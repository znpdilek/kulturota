"""
Route Modeli
============
PRD Bölüm 10.2 ``routes`` tablosu.
PRD Bölüm 11 - ROUTES bir USER tarafından sahiplenilir, çok ROUTE_STOPS içerir.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import RouteDifficulty
from app.db.base_class import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum

if TYPE_CHECKING:
    from app.models.route_comment import RouteComment
    from app.models.route_like import RouteLike
    from app.models.route_stop import RouteStop
    from app.models.user import User


class Route(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """``routes`` — Kullanıcı rotaları (PRD 10.2)."""

    __tablename__ = "routes"

    # --- Sahiplik (PRD 11: USERS ||--o{ ROUTES) -----------------------------
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- İçerik --------------------------------------------------------------
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    theme: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Yayın ---------------------------------------------------------------
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    cover_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Hesaplanan metrikler (rota motoru çıktısı) -------------------------
    est_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_distance_km: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    difficulty: Mapped[RouteDifficulty | None] = mapped_column(
        pg_enum(RouteDifficulty, name="route_difficulty"),
        nullable=True,
    )

    # --- İlişkiler (PRD Bölüm 11) -------------------------------------------
    owner: Mapped["User"] = relationship(back_populates="routes")
    stops: Mapped[list["RouteStop"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        order_by="RouteStop.order_index",
        passive_deletes=True,
    )
    likes: Mapped[list["RouteLike"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    comments: Mapped[list["RouteComment"]] = relationship(
        back_populates="route",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Route id={self.id} title={self.title!r}>"
