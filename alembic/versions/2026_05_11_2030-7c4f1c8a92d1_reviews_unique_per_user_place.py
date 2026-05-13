"""reviews unique per user/place (Adım 8 — Sosyal MVP)

Revision ID: 7c4f1c8a92d1
Revises: 63be629b1bf2
Create Date: 2026-05-11 20:30:00.000000+00:00

PRD §10.2 ``reviews`` + §11.1 referans bütünlüğü.

Adım 8 (Sosyal Özellikler — Yorum & Beğeni MVP) kapsamında bir kullanıcının
**aynı mekana yalnızca bir yorum** bırakabilmesini DB seviyesinde garanti
ediyoruz. Servis katmanı zaten aynı kuralı uygular; bu unique constraint
yarış koşullarına (concurrent POST) karşı son savunma hattıdır.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "7c4f1c8a92d1"
down_revision: Union[str, None] = "63be629b1bf2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_reviews_place_user",
        "reviews",
        ["place_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reviews_place_user", "reviews", type_="unique")
