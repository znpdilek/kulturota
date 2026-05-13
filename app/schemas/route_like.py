"""
Route Like Şemaları (Adım 8 — Sosyal Özellikler / Beğeni MVP)
=============================================================
PRD §10.2 ``route_likes`` tablosu + §12.2 ``/v1/routes/{route_id}/likes``
endpoint ailesinin response DTO'ları.

MVP yaklaşımı (kullanıcı talebi)
--------------------------------
* Sadece **like / unlike** akışı kapsamdadır. ``route_likes`` tablosu PK'i
  ``(user_id, route_id)`` bileşik olduğu için doğal olarak idempotenttir:
  ikinci ``POST`` çağrısı **409 değil, 200 (zaten beğenilmiş)** döner;
  ikinci ``DELETE`` çağrısı **204 (zaten beğenilmemiş)** olur.
* "Beğenenler listesi", takip ilişkisi (followers/following) ve bildirim
  altyapısı bu adımda **kapsam dışıdır**.

Request gövdesi yoktur — kaynak hedefini path parametresi belirler:
``POST /v1/routes/{route_id}/likes``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RouteLikeStatus(BaseModel):
    """``GET /v1/routes/{route_id}/likes`` cevap zarfı.

    Belirli bir rota için mevcut kullanıcının beğeni durumu + toplam
    beğeni sayısı. Frontend kalp ikonunu beslemek için bu uçtan tek
    seferde her iki bilgiyi alır.
    """

    model_config = ConfigDict(from_attributes=True)

    route_id: uuid.UUID
    liked: bool = Field(
        ...,
        description=(
            "Mevcut kullanıcı bu rotayı beğenmiş mi? (auth zorunlu olduğu için "
            "anonim çağrıda bu uç 401 döner)."
        ),
    )
    like_count: int = Field(
        ...,
        ge=0,
        description="Rotanın toplam beğeni sayısı (route_likes COUNT(*)).",
    )
    liked_at: datetime | None = Field(
        default=None,
        description=(
            "Kullanıcının beğeniyi bıraktığı an (sadece liked=true olduğunda "
            "dolu)."
        ),
    )


class RouteLikeResponse(RouteLikeStatus):
    """``POST /v1/routes/{route_id}/likes`` ve ``DELETE`` cevap zarfı.

    :class:`RouteLikeStatus`'a ek olarak ``action`` alanı, istemcinin
    UI'ı kolayca güncelleyebilmesi için bu çağrının ne yaptığını bildirir:
    ``created`` (yeni beğeni), ``already_liked`` (zaten vardı), ``removed``
    (kaldırıldı), ``not_liked`` (zaten beğenilmemiş).
    """

    action: str = Field(
        ...,
        description="created | already_liked | removed | not_liked",
        examples=["created", "already_liked", "removed", "not_liked"],
    )


__all__ = [
    "RouteLikeResponse",
    "RouteLikeStatus",
]
