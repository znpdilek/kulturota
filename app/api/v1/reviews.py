"""
Reviews Endpoint'leri (Adım 8 — Sosyal Özellikler / Yorum MVP)
==============================================================
PRD §12.2 — ``/v1/places/{place_id}/reviews`` ailesi.

Endpoint özeti
--------------
========================  =================================================
``POST   /v1/places/{place_id}/reviews``                    Yorum + puan ekle.
``GET    /v1/places/{place_id}/reviews``                    Yorum listele.
``DELETE /v1/places/{place_id}/reviews/{review_id}``        Kendi yorumumu sil.
========================  =================================================

Rate Limiting (PRD §12.1)
    * ``GET``      → Public 60 req/dk.
    * ``POST``     → Auth 300 req/dk.
    * ``DELETE``   → Auth 300 req/dk.

MVP sınırları (kullanıcı talebi)
--------------------------------
* Yalnızca temel yorum (CRUD: create/list/delete) kapsamdadır.
* Takip ilişkisi (followers/following), yorumlara yanıt verme
  (nested/threaded comments) ve bildirim altyapısı **kapsam dışıdır**.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.schemas.review import (
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
)
from app.services import review_service

AUTH_LIMIT = settings.RATE_LIMIT_AUTH_PER_MIN
PUBLIC_LIMIT = settings.RATE_LIMIT_PUBLIC_PER_MIN

router = APIRouter(prefix="/places", tags=["reviews"])

_LIMIT_DEFAULT = 20
_LIMIT_MAX = 100


@router.post(
    "/{place_id}/reviews",
    response_model=ReviewResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mekana yorum ve 1-5 puan bırak",
    description=(
        "PRD §10.2 + §12.2.\n\n"
        "Auth zorunludur. Bir kullanıcı bir mekana **yalnızca bir yorum** "
        "bırakabilir; yeniden yazmak için önce mevcut yorumu silmelisiniz.\n\n"
        "Mekanın yayında (``is_published=true``) olması gerekir; yayından "
        "kaldırılmış kayıtlara yorum yazılamaz."
    ),
    dependencies=[Depends(rate_limit("reviews.create", limit=AUTH_LIMIT))],
    responses={
        401: {"description": "Bearer token eksik veya geçersiz."},
        404: {"description": "Mekan bulunamadı veya yayında değil."},
        409: {"description": "Bu mekana zaten bir yorumunuz var."},
        422: {"description": "Validation: rating 1-5 aralığında olmalı."},
    },
)
def create_review(
    place_id: uuid.UUID,
    payload: ReviewCreate,
    user: CurrentUser,
    db: DbSession,
) -> ReviewResponse:
    return review_service.create_review(db, user, place_id, payload)


@router.get(
    "/{place_id}/reviews",
    response_model=ReviewListResponse,
    summary="Mekanın yorum listesini getir",
    description=(
        "En yeni yorumlar üstte (``created_at DESC``). Halka açık bir uçtur; "
        "auth gerektirmez (PRD §12.1 Public 60 req/dk).\n\n"
        "Cevap zarfında ``aggregate`` bloğu mekanın ortalama puanı ve toplam "
        "yorum sayısını taşır — yıldız rozetini istemcide hızlı beslemek için."
    ),
    dependencies=[Depends(rate_limit("reviews.list", limit=PUBLIC_LIMIT))],
)
def list_reviews(
    place_id: uuid.UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX)] = _LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReviewListResponse:
    return review_service.list_reviews(db, place_id, limit=limit, offset=offset)


@router.delete(
    "/{place_id}/reviews/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Kendi yorumumu sil",
    description=(
        "Auth zorunludur. Yalnızca yorumun **sahibi** silebilir; başka birinin "
        "yorumunu silmeye çalışmak 404 döner (PRD §17 — bilgi sızıntısı önlemi)."
    ),
    dependencies=[Depends(rate_limit("reviews.delete", limit=AUTH_LIMIT))],
    response_class=Response,
    responses={
        401: {"description": "Bearer token eksik veya geçersiz."},
        404: {"description": "Yorum bulunamadı veya sahibi siz değilsiniz."},
    },
)
def delete_review(
    place_id: uuid.UUID,
    review_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    review_service.delete_review(db, user, place_id, review_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
