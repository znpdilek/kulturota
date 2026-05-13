"""
PlaceTag Modeli (Many-to-Many: Place ↔ Tag)
===========================================
PRD Bölüm 10.2 - ``place_tags (place_id, tag_id, weight, source)``.
PRD Bölüm 11.1 - Many-to-Many bileşik PK.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base

if TYPE_CHECKING:
    from app.models.place import Place
    from app.models.tag import Tag


class PlaceTag(Base):
    """``place_tags`` — M2M köprü (bileşik PK)."""

    __tablename__ = "place_tags"

    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="CASCADE"),
        primary_key=True,
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tags.id", ondelete="CASCADE"),
        primary_key=True,
    )

    weight: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    # Kaynak: algoritmik / wikidata / osm / llm / manual
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)

    place: Mapped["Place"] = relationship(back_populates="place_tags")
    tag: Mapped["Tag"] = relationship(back_populates="place_tags")

    def __repr__(self) -> str:
        return f"<PlaceTag place_id={self.place_id} tag_id={self.tag_id}>"
