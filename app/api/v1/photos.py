"""
Photos Endpoint'leri (Adım 6 — Medya Yönetimi)
==============================================
PRD §12.2 — ``POST /v1/places/{id}/photos`` (Auth + multipart).
PRD §13   — Medya ve Depolama Mimarisi (S3/MinIO).
PRD §14.3 — F3 Fotoğraf Yükleme akışı.

Bu endpoint *kanonik* form `/api/v1/photos` üzerinden çalışır; ``place_id``
multipart form alanından alınır. Bu tasarım PRD §12.2'deki
``/v1/places/{id}/photos`` ile semantik olarak özdeştir ve istemciye iki
seçenek sunar (gelecekte alias router eklenebilir).

Rate Limiting (PRD §12.1): Auth uç olduğu için **300 req/dk** sınırı uygulanır.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status

from app.api.deps import CurrentUser, DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.schemas.photo import PhotoListResponse, PhotoUploadResponse
from app.services import media_service

AUTH_LIMIT = settings.RATE_LIMIT_AUTH_PER_MIN
PUBLIC_LIMIT = settings.RATE_LIMIT_PUBLIC_PER_MIN

router = APIRouter(prefix="/photos", tags=["photos"])
# Mekana ait foto galerisi `/places/{id}/photos` altında public okuma sunar.
places_photos_router = APIRouter(prefix="/places", tags=["photos"])


@router.post(
    "",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mekana (ve opsiyonel rotaya) fotoğraf yükle (multipart)",
    description=(
        "PRD §12.2 + §13 + §14.3 (F3).\n\n"
        "**Multipart form alanları**:\n"
        "- `place_id` (zorunlu, UUID): Fotoğrafın bağlanacağı mekan.\n"
        "- `route_id` (opsiyonel, UUID): Kullanıcının kendi rotasına ekleyecekse.\n"
        "- `file` (zorunlu, binary): `.jpg` veya `.png`, **max 5MB**.\n\n"
        "**Güvenlik**: Yüklenen dosya magic-byte ile doğrulanır, Pillow ile "
        "re-encode edilir ve EXIF GPS bilgisi (PRD §17.3) temizlenir.\n\n"
        "**Lisans**: PRD §20.4 — kullanıcı UGC varsayılan `CC BY-NC 4.0`.\n\n"
        "**Moderasyon**: Yeni kayıt `is_approved=false` durumunda başlar; "
        "NSFW + perceptual hash moderasyon servisi sonraki adımda işler "
        "(PRD F3)."
    ),
    dependencies=[Depends(rate_limit("photos.upload", limit=AUTH_LIMIT))],
    responses={
        400: {"description": "Bozuk görsel ya da boş dosya."},
        401: {"description": "Bearer token eksik veya geçersiz."},
        403: {"description": "Rota başkasına ait."},
        404: {"description": "Mekan veya rota bulunamadı."},
        413: {"description": "5MB sınırı aşıldı."},
        415: {"description": "Sadece .jpg ve .png kabul edilir."},
        502: {"description": "Object storage erişilemedi."},
    },
)
async def upload_photo(
    db: DbSession,
    user: CurrentUser,
    place_id: Annotated[uuid.UUID, Form(description="Hedef mekan UUID.")],
    file: Annotated[UploadFile, File(description="JPEG veya PNG; ≤ 5MB.")],
    route_id: Annotated[
        uuid.UUID | None,
        Form(description="Opsiyonel: kullanıcının sahip olduğu rota UUID'si."),
    ] = None,
) -> PhotoUploadResponse:
    raw_bytes = await file.read()
    # FastAPI/Starlette UploadFile boyut sınırı vermez; servis katmanı 5MB
    # eşiğini erken-reject ile uygular (PRD §17.4).
    try:
        return media_service.upload_photo(
            db,
            user=user,
            place_id=place_id,
            route_id=route_id,
            raw_bytes=raw_bytes,
            declared_mime=file.content_type,
        )
    finally:
        await file.close()


@places_photos_router.get(
    "/{place_id}/photos",
    response_model=PhotoListResponse,
    summary="Mekanın foto galerisini getir",
    description=(
        "Yalnızca yayınlanmış (``is_approved=true``) kayıtları döner. "
        "MVP'de tüm fotoğraflar otomatik yayınlanır; editör onayı yoktur."
    ),
    dependencies=[Depends(rate_limit("photos.list", limit=PUBLIC_LIMIT))],
)
def list_photos(
    place_id: uuid.UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PhotoListResponse:
    return media_service.list_photos(
        db, place_id=place_id, limit=limit, offset=offset
    )


__all__ = ["router", "places_photos_router", "upload_photo"]
