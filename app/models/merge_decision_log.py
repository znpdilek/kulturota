"""
MergeDecisionLog Modeli
=======================
PRD Bölüm 8.5 + 10.2 - dedup / merge kararlarının lineage'ı.
PRD Bölüm 11 - ETL_RUN_LOG ||--o{ MERGE_DECISION_LOG;
                PLACES ||--o{ MERGE_DECISION_LOG.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.etl_run_log import ETLRunLog
    from app.models.place import Place


class MergeDecisionLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``merge_decision_log`` — Gold katmanı merge kararları (PRD 8.5)."""

    __tablename__ = "merge_decision_log"

    etl_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("etl_run_log.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # PRD 11: PLACES ||--o{ MERGE_DECISION_LOG : decided_for
    place_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("places.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Merge'a giren aday kayıt id'leri (lineage)
    source_record_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )

    score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    geo_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    name_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    category_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # PRD 8.5: source-priority merge stratejisi snapshot'ı
    primary_source_per_field: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)  # auto_merge / queued / discarded
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    etl_run: Mapped["ETLRunLog"] = relationship(back_populates="merge_decisions")
    place: Mapped["Place | None"] = relationship(back_populates="merge_decisions")

    def __repr__(self) -> str:
        return f"<MergeDecisionLog id={self.id} decision={self.decision}>"
