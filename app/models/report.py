"""
Report Modeli (Polimorfik Referans)
===================================
PRD Bölüm 10.2 + 11.1 - ``reports`` tablosu.

PRD 11.1 (aynen):
    "Polimorfik Referans: reports.target_type + target_id (FK yok; check constraint)."

target_type: place | photo | review | route | user.
Bütünlük: target_type kolonu sadece geçerli enum değerleri kabul eder; target_id
kolonu FK olmaksızın UUID tutar (polimorfik). Uygulama katmanı join yapacaktır.

PRD 11 - USERS ||--o{ REPORTS (reporter_id); PLACES ||--o{ REPORTS (target).
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ReportAutoAction, ReportStatus, ReportTargetType
from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum

if TYPE_CHECKING:
    from app.models.user import User


class Report(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``reports`` — polimorfik kullanıcı şikayet kayıtları (PRD 10.2)."""

    __tablename__ = "reports"

    # PRD 11.1: Polimorfik referans (FK YOK; check constraint enum üzerinden uygulanıyor)
    target_type: Mapped[ReportTargetType] = mapped_column(
        pg_enum(ReportTargetType, name="report_target_type"),
        nullable=False,
        index=True,
    )
    target_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    reason: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[ReportStatus] = mapped_column(
        pg_enum(ReportStatus, name="report_status"),
        nullable=False,
        server_default=ReportStatus.AUTO_RESOLVED.value,
    )
    auto_action: Mapped[ReportAutoAction] = mapped_column(
        pg_enum(ReportAutoAction, name="report_auto_action"),
        nullable=False,
        server_default=ReportAutoAction.NONE.value,
    )

    reporter: Mapped["User"] = relationship(back_populates="reports")

    def __repr__(self) -> str:
        return f"<Report id={self.id} target={self.target_type}:{self.target_id}>"
