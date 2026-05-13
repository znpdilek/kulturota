"""
ETLRunLog Modeli
================
PRD Bölüm 8.3 + 10.2 - ``etl_run_log``: pipeline gözlemlenebilirliği ve veri lineage.
PRD Bölüm 11 - ETL_RUN_LOG ||--o{ MERGE_DECISION_LOG.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.merge_decision_log import MergeDecisionLog


class ETLRunLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``etl_run_log`` (PRD 8.3 + 10.2)."""

    __tablename__ = "etl_run_log"

    dag_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False)  # overpass/wikidata/bizizmir/portal
    # PRD 8.3: idempotency_key
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)  # success / failed / partial

    records_extracted: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_loaded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # PRD 11: ETL_RUN_LOG ||--o{ MERGE_DECISION_LOG
    merge_decisions: Mapped[list["MergeDecisionLog"]] = relationship(
        back_populates="etl_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<ETLRunLog id={self.id} dag_id={self.dag_id} status={self.status}>"
