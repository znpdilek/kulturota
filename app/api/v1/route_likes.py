"""
Route Like Endpoint'leri (Adım 8 — Sosyal Özellikler / Beğeni MVP)
==================================================================
PRD §12.2 — ``/v1/routes/{route_id}/likes``.

Endpoint özeti
--------------
========================  =================================================
``POST   /v1/routes/{route_id}/likes``     Rotayı beğen (idempotent).
``DELETE /v1/routes/{route_id}/likes``     Beğeniyi geri çek (idempotent).
``GET    /v1/routes/{route_id}/likes``     Kullanıcının durumu + toplam.
========================  =================================================

Rate Limiting (PRD §12.1): tüm uçlar **300 req/dk** auth sınırı altındadır.

İş kuralları
------------
* Rota ``is_public=True`` olmalıdır (kullanıcı talebi).
* Kullanıcı kendi rotasını beğenemez (talep: "başkalarının oluşturduğu").
* Hem ``POST`` hem ``DELETE`` idempotenttir; cevap zarfındaki ``action``
  alanı istemci UI'sının doğru rozet durumunu hesaplamasını sağlar:
  ``created`` | ``already_liked`` | ``removed`` | ``not_liked``.

MVP sınırları (kullanıcı talebi)
--------------------------------
* Beğenenler listesi, takip ilişkisi (followers/following) ve bildirim
  altyapısı bu adımda **kapsam dışıdır**.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.schemas.route_like import RouteLikeResponse, RouteLikeStatus
from app.services import route_like_service

AUTH_LIMIT = settings.RATE_LIMIT_AUTH_PER_MIN

router = APIRouter(prefix="/routes", tags=["route_likes"])


@router.post(
    "/{route_id}/likes",
    response_model=RouteLikeResponse,
    status_code=status.HTTP_200_OK,
    summary="Halka açık rotayı beğen (idempotent)",
    description=(
        "PRD §10.2 ``route_likes`` + §12.2.\n\n"
        "Auth zorunludur. ``route_likes`` PK'i ``(user_id, route_id)`` "
        "bileşik olduğu için işlem doğal olarak idempotenttir: ikinci POST "
        "``action=already_liked`` döner. Yanıttaki ``like_count`` rotanın "
        "güncel toplam beğeni sayısıdır.\n\n"
        "**Kısıt**: Yalnızca ``is_public=true`` rotalar beğenilebilir; kendi "
        "oluşturduğunuz rotaları beğenemezsiniz (400)."
    ),
    dependencies=[Depends(rate_limit("route_likes.create", limit=AUTH_LIMIT))],
    responses={
        400: {"description": "Kendi rotanızı beğenemezsiniz."},
        401: {"description": "Bearer token eksik veya geçersiz."},
        404: {"description": "Rota bulunamadı veya halka açık değil."},
    },
)
def like_route(
    route_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RouteLikeResponse:
    return route_like_service.like_route(db, user, route_id)


@router.delete(
    "/{route_id}/likes",
    response_model=RouteLikeResponse,
    status_code=status.HTTP_200_OK,
    summary="Rota beğenisini geri çek (idempotent)",
    description=(
        "PRD §10.2 ``route_likes``. Auth zorunludur.\n\n"
        "İdempotent: hiç beğenilmemiş bir rotaya DELETE atmak 404 değil, "
        "``action=not_liked`` ile mevcut state'i döndürür. Bu sayede UI "
        "ağ kopmalarında güvenle retry yapabilir."
    ),
    dependencies=[Depends(rate_limit("route_likes.delete", limit=AUTH_LIMIT))],
    responses={
        401: {"description": "Bearer token eksik veya geçersiz."},
    },
)
def unlike_route(
    route_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RouteLikeResponse:
    return route_like_service.unlike_route(db, user, route_id)


@router.get(
    "/{route_id}/likes",
    response_model=RouteLikeStatus,
    summary="Kullanıcının beğeni durumu + toplam beğeni sayısı",
    description=(
        "Mevcut kullanıcının beğeni durumunu (``liked``) ve rotanın toplam "
        "beğeni sayısını (``like_count``) tek seferde döner. Frontend kalp "
        "ikonunu beslemek için bu uca tek istek atar (PRD §18.2 N+1 önleme)."
    ),
    dependencies=[Depends(rate_limit("route_likes.status", limit=AUTH_LIMIT))],
    responses={
        401: {"description": "Bearer token eksik veya geçersiz."},
        404: {"description": "Rota bulunamadı veya halka açık değil."},
    },
)
def get_like_status(
    route_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RouteLikeStatus:
    return route_like_service.get_like_status(db, user, route_id)


__all__ = ["router"]
