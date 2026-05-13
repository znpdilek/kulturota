"""
OpeningHours Modeli
===================
PRD Bölüm 10.2 - ``opening_hours`` tablosu.
Pilot kaynak: İzmir için Bizizmir Açık Veri; günlük güncellenir (PRD 8.1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    SmallInteger,
    Time,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import OpeningHoursSource
from app.db.base_class import Base
from app.db.mixins import UUIDPrimaryKeyMixin
from app.db.types import pg_enum

if TYPE_CHECKING:
    from app.models.place import Place


class OpeningHours(UUIDPrimaryKeyMixin, Base):
    """``opening_hours`` (PRD 10.2)."""

    __tablename__ = "opening_hours"

    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # PRD 10.2: day_of_week 0-6 (Pazartesi-Pazar)
    day_of_week: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    opens_at: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)
    closes_at: Mapped[time | None] = mapped_column(Time(timezone=False), nullable=True)

    # Sezonsal aralık (opsiyonel)
    season_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    season_end: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Özel kapalı gün bayrağı (resmi tatil vb.)
    is_closed_special: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    source: Mapped[OpeningHoursSource] = mapped_column(
        pg_enum(OpeningHoursSource, name="opening_hours_source"),
        nullable=False,
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="day_of_week_range"),
    )

    place: Mapped["Place"] = relationship(back_populates="opening_hours")

    def __repr__(self) -> str:
        return f"<OpeningHours place_id={self.place_id} day={self.day_of_week}>"
