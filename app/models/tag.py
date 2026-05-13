"""
Tag Modeli (Controlled Vocabulary)
==================================
PRD Bölüm 10.2 - ``tags (id, slug, name jsonb, group)``.
PRD Bölüm 11 - TAGS ||--o{ PLACE_TAGS.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.place_tag import PlaceTag


class Tag(UUIDPrimaryKeyMixin, Base):
    """``tags`` — controlled vocabulary (PRD 10.2)."""

    __tablename__ = "tags"

    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    name: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # "group" Python keyword olduğu için kolon adı "group_name"
    group_name: Mapped[str | None] = mapped_column("group", String(64), nullable=True, index=True)

    place_tags: Mapped[list["PlaceTag"]] = relationship(
        back_populates="tag",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Tag id={self.id} slug={self.slug!r}>"
