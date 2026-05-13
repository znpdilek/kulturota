"""
RouteStop Modeli
================
PRD Bölüm 10.2 - ``route_stops`` tablosu.
PRD Bölüm 11.1:
    * ``route_stops.place_id → places(mekan_id)``  ON DELETE RESTRICT.
    * ``UNIQUE(route_id, order_index)`` ile sıralama bütünlüğü.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.place import Place
    from app.models.route import Route


class RouteStop(UUIDPrimaryKeyMixin, Base):
    """``route_stops`` — rotaya ait sıralı duraklar (PRD 10.2)."""

    __tablename__ = "route_stops"

    route_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # PRD 11.1: place_id ON DELETE RESTRICT
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_arrival: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        # PRD 10.2 + 11.1: bir rotada iki stop aynı pozisyona düşemez
        UniqueConstraint("route_id", "order_index", name="route_order"),
    )

    # --- İlişkiler ----------------------------------------------------------
    route: Mapped["Route"] = relationship(back_populates="stops")
    place: Mapped["Place"] = relationship(back_populates="route_stops")

    def __repr__(self) -> str:
        return f"<RouteStop route_id={self.route_id} order={self.order_index}>"
