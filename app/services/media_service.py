"""
Medya Servisi — Fotoğraf Yükleme Orkestrasyonu
==============================================
PRD §13 — Medya ve Depolama Mimarisi.
PRD §14.3 (F3) — Fotoğraf Yükleme + Otomatik Moderasyon akışı.
PRD §17.3 + §17.4 — KVKK (EXIF GPS temizliği) + Upload Güvenliği.

Bu servis, ``POST /v1/photos`` endpoint'inin tek giriş noktasıdır. Sıralı
sorumluluklar:

    1. Mekan (``place_id``) ve opsiyonel rota (``route_id``) sahipliği
       doğrulaması (PRD §11.1).
    2. Görsel doğrulama + sanitize (`exif_service.sanitize_image`):
       MIME, boyut, decode, EXIF GPS temizliği.
    3. S3/MinIO'ya temizlenmiş baytları yaz (`storage_service`).
    4. ``photos`` tablosuna satır oluştur ve commit et.

PRD F3'te tanımlanan **NSFW + perceptual hash + duplicate** sonraki AI
moderasyon adımına bırakılmıştır; bu yüzden yeni kayıtların
``is_approved = false`` olarak başlaması mimari kuraldır.
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ProblemDetailsError
from app.models.photo import Photo
from app.models.place import Place
from app.models.route import Route
from app.models.user import User
from app.schemas.photo import PhotoUploadResponse
from app.services.exif_service import SanitizedImage, sanitize_image
from app.services.storage_service import StorageService, get_storage_service

logger = logging.getLogger(__name__)

# S3 object key prefix'i — PRD §13: places altında izole edilir, bucket içi
# erişim kontrolü için yardımcıdır.
_KEY_PREFIX: Final = "places"


def upload_photo(
    db: Session,
    *,
    user: User,
    place_id: uuid.UUID,
    route_id: uuid.UUID | None,
    raw_bytes: bytes,
    declared_mime: str | None,
    storage: StorageService | None = None,
) -> PhotoUploadResponse:
    """Tek bir fotoğrafı uçtan uca yükleme akışını yürütür.

    Args:
        db: Aktif SQLAlchemy session.
        user: ``CurrentUser`` dependency'sinden gelen yetkili kullanıcı.
        place_id: Hedef mekan UUID.
        route_id: Opsiyonel; PRD §10.2 ``photos.route_id nullable``.
        raw_bytes: Multipart dosyasının tüm baytları.
        declared_mime: ``UploadFile.content_type``.
        storage: Testte mock'lamak için DI; üretimde modul cache'i.

    Raises:
        ProblemDetailsError: 400/404/413/415/502 — kullanıcıya RFC 7807.

    Returns:
        :class:`PhotoUploadResponse` — yeni photo kaydının özet temsili.
    """
    storage = storage or get_storage_service()

    # --- 1) Mekan & rota doğrulaması --------------------------------------
    place = _get_published_place(db, place_id)
    if route_id is not None:
        _assert_route_ownership(db, user.id, route_id)

    # --- 2) Görsel sanitize + EXIF (PRD §17.3 + §17.4) --------------------
    sanitized: SanitizedImage = sanitize_image(raw_bytes, declared_mime=declared_mime)
    logger.info(
        "Görsel sanitize edildi: place_id=%s user_id=%s mime=%s size=%d gps=%s",
        place_id,
        user.id,
        sanitized.content_type,
        len(sanitized.cleaned_bytes),
        sanitized.gps is not None,
    )

    # --- 3) Bucket hazır mı? (lokal dev için lazy-create) -----------------
    storage.ensure_bucket()

    # --- 4) Object key + S3 yükleme ---------------------------------------
    photo_uuid = uuid.uuid4()
    object_key = f"{_KEY_PREFIX}/{place_id}/{photo_uuid}.{sanitized.extension}"

    metadata = {
        "place-id": str(place_id),
        "user-id": str(user.id),
        "license": "CC-BY-NC-4.0",  # PRD §20.4 varsayılan.
    }
    if route_id is not None:
        metadata["route-id"] = str(route_id)

    public_url = storage.upload_bytes(
        key=object_key,
        data=sanitized.cleaned_bytes,
        content_type=sanitized.content_type,
        metadata=metadata,
    )

    # --- 5) DB satırı (PRD §10.2 photos) ----------------------------------
    # PRD F3: NSFW + perceptual hash adımı sonraki moderasyon servisinde
    # yapılır → ``is_approved=False`` bilinçli varsayılandır.
    photo = Photo(
        id=photo_uuid,
        place_id=place_id,
        user_id=user.id,
        route_id=route_id,
        url=public_url,
        thumb_url=public_url,  # MVP: thumbnail pipeline'ı ileri adımda.
        width=sanitized.width,
        height=sanitized.height,
        taken_at=sanitized.taken_at,
        exif=sanitized.exif_sanitized or None,
        license="CC BY-NC 4.0",
        is_approved=False,
    )

    db.add(photo)
    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        # DB yazımı başarısızsa S3'teki orphan objeyi temizle (best-effort).
        storage.delete_object(object_key)
        logger.exception("photos commit başarısız, S3 objesi temizlendi: key=%s", object_key)
        raise ProblemDetailsError(
            status=500,
            title="Internal Server Error",
            detail="Fotoğraf kaydedilemedi; dosya silindi, tekrar deneyiniz.",
            code="media.persist_failed",
        ) from exc

    db.refresh(photo)

    return PhotoUploadResponse(
        id=photo.id,
        place_id=photo.place_id,
        user_id=photo.user_id,
        route_id=photo.route_id,
        url=photo.url,
        thumb_url=photo.thumb_url,
        width=photo.width,
        height=photo.height,
        license=photo.license,
        is_approved=photo.is_approved,
        taken_at=photo.taken_at,
        created_at=photo.created_at,
        exif_had_gps=sanitized.gps is not None,
    )


# --- Internal validations --------------------------------------------------
def _get_published_place(db: Session, place_id: uuid.UUID) -> Place:
    """Mekanın varlığını ve yayın bayrağını doğrular (PRD 11.1 soft-delete)."""
    place = db.scalar(
        select(Place).where(
            Place.id == place_id,
            Place.is_published.is_(True),
        )
    )
    if place is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Mekan bulunamadı veya yayında değil.",
            code="media.place_not_found",
        )
    return place


def _assert_route_ownership(db: Session, user_id: uuid.UUID, route_id: uuid.UUID) -> None:
    """Rota gerçekten kullanıcıya mı ait? (PRD §11.1 yetki bütünlüğü).

    Bu adımda rota oluşturma kapsamında değiliz; yine de fotoğrafı yanlış
    rotaya iliştirmeye izin vermemek için sahiplik kontrolü yapılır.
    """
    route = db.scalar(select(Route).where(Route.id == route_id))
    if route is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Belirtilen rota bulunamadı.",
            code="media.route_not_found",
        )
    if route.owner_id != user_id:
        raise ProblemDetailsError(
            status=403,
            title="Forbidden",
            detail="Bu rotaya fotoğraf yükleme yetkiniz yok.",
            code="media.route_forbidden",
        )
