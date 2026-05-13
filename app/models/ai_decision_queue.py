"""
AIDecisionQueue Modeli (Mentor Direktifi)
=========================================
PRD Bölüm 10.2 - ``ai_decision_queue`` tablosu.
PRD Bölüm 11 - AI_DECISION_QUEUE ||--o{ AI_DECISION_LOG (1:N);
                AI_DECISION_QUEUE }o--o{ PLACES (M:N candidates).

D6 - İnsan küratör yerine otonom AI karar katmanı (PRD Bölüm 9).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    DateTime,
    Integer,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AIDecisionReason, AIDecisionStatus
from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum

if TYPE_CHECKING:
    from app.models.ai_decision_log import AIDecisionLog


class AIDecisionQueue(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``ai_decision_queue`` (PRD 10.2)."""

    __tablename__ = "ai_decision_queue"

    # PRD 10.2: payload jsonb (aday kayıt(lar))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    # PRD 11: many-to-many ilişki places ile FK array olarak (lineage).
    # Burada referans bütünlüğü PG ARRAY üzerinden FK olarak tutulamaz; bu yüzden
    # uygulama katmanı + ai_decision_log üzerinden çapraz kontrol yapılır.
    candidate_place_ids: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=True,
    )

    score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    reason: Mapped[AIDecisionReason] = mapped_column(
        pg_enum(AIDecisionReason, name="ai_decision_reason"),
        nullable=False,
    )
    status: Mapped[AIDecisionStatus] = mapped_column(
        pg_enum(AIDecisionStatus, name="ai_decision_status"),
        nullable=False,
        server_default=AIDecisionStatus.PENDING.value,
        index=True,
    )

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # PRD 11: AI_DECISION_QUEUE ||--o{ AI_DECISION_LOG (1:N)
    logs: Mapped[list["AIDecisionLog"]] = relationship(
        back_populates="queue",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<AIDecisionQueue id={self.id} status={self.status}>"
