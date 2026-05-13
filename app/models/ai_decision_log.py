"""
AIDecisionLog Modeli (Mentor Direktifi)
=======================================
PRD Bölüm 10.2 - ``ai_decision_log`` tablosu. Tam audit izi (PRD 9.6).
PRD Bölüm 11 - AI_DECISION_QUEUE ||--o{ AI_DECISION_LOG.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AIDecisionType, AIModelProvider
from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum

if TYPE_CHECKING:
    from app.models.ai_decision_queue import AIDecisionQueue


class AIDecisionLog(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``ai_decision_log`` (PRD 10.2)."""

    __tablename__ = "ai_decision_log"

    queue_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ai_decision_queue.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    model_provider: Mapped[AIModelProvider] = mapped_column(
        pg_enum(AIModelProvider, name="ai_model_provider"),
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    decision: Mapped[AIDecisionType] = mapped_column(
        pg_enum(AIDecisionType, name="ai_decision_type"),
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)

    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    queue: Mapped["AIDecisionQueue"] = relationship(back_populates="logs")

    def __repr__(self) -> str:
        return f"<AIDecisionLog id={self.id} decision={self.decision}>"
