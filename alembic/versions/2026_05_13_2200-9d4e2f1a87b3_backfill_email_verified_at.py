"""backfill email_verified_at for legacy users

Revision ID: 9d4e2f1a87b3
Revises: 7c4f1c8a92d1
Create Date: 2026-05-13 22:00:00.000000+00:00

Yeni kayıt akışı (PRD §17.3) e-posta doğrulama adımı zorunlu kılındı.
``email_verified_at IS NULL`` olan kayıtlar artık oturum açamaz. Mevcut
geliştirme/staging veritabanlarındaki kullanıcıların aniden kilitlenmesini
önlemek için bu migration eski kayıtları doğrulanmış sayar (grandfather
clause).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "9d4e2f1a87b3"
down_revision: Union[str, None] = "7c4f1c8a92d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET email_verified_at = NOW() "
        "WHERE email_verified_at IS NULL"
    )


def downgrade() -> None:
    # Geri alınması anlamlı değil — eski kayıtların doğrulama zamanı kaybedilmez.
    pass
