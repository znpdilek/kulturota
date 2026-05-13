"""
RefreshToken Modeli
===================
PRD §12.1 + §17.2 — **Refresh token rotation + reuse detection**.

Her başarılı `login` veya `refresh` çağrısı bu tabloya bir kayıt ekler.
Token JWT olarak istemciye verilir, ancak ``jti`` (JWT ID) bu tabloda
saklanır. Refresh kullanıldığında:

    * Eski token ``used_at`` ile işaretlenir, yeni token kaydedilir (rotation).
    * Aynı token ikinci kez kullanılırsa → o kullanıcıya ait **tüm** aktif
      refresh token'lar revoke edilir (reuse detection → olası sızıntı).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base
from app.db.mixins import CreatedAtMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class RefreshToken(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """``refresh_tokens`` — rotating refresh token kayıtları (PRD §17.2)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # JWT'nin `jti` claim'i ile birebir eşleşir; UUID v4.
    jti: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    # Önceki refresh token'ın jti'si (rotation chain).
    parent_jti: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)

    ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    user: Mapped["User"] = relationship()

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user={self.user_id} jti={self.jti}>"
