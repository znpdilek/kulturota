"""
Photo Şemaları
==============
PRD §10.2 ``photos`` tablosu için Pydantic DTO'ları.
PRD §12.2 + Adım 6 (Medya Yönetimi).

Bu adımda yalnızca **fotoğraf yükleme** akışı kapsamdadır (PRD F3); galeri
listesi (``GET /v1/places/{id}/photos``) ileriki adımlarda eklenecektir.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class PhotoUploadResponse(BaseModel):
    """``POST /v1/photos`` başarılı yanıt zarfı (HTTP 201).

    PRD §13: yüklenen dosya hem S3 / MinIO'ya yazılır hem de ``photos``
    tablosuna kaydedilir. İstemciye geri dönen tek yetkili URL ``url``
    alanıdır; istemci bu URL ile CDN'den çeker.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID = Field(..., description="Yeni photo kaydının UUID'si.")
    place_id: uuid.UUID
    user_id: uuid.UUID
    route_id: uuid.UUID | None = None

    url: str = Field(..., description="Public erişim URL'i (CDN/MinIO).")
    thumb_url: str | None = Field(
        default=None,
        description="Thumbnail URL'i (MVP'de doğrudan url ile aynıdır; PRD §18.2 "
        "ileri adımda Celery/Arq ile çoklu boyut üretilir).",
    )

    width: int | None = None
    height: int | None = None
    license: str = Field(default="CC BY-NC 4.0", description="PRD §20.4 varsayılan.")
    is_approved: bool = Field(
        default=True,
        description="MVP'de editör paneli yoktur; fotoğraflar anında yayınlanır.",
    )

    taken_at: datetime | None = Field(
        default=None,
        description="EXIF DateTimeOriginal'dan çıkarılmış zaman (varsa).",
    )
    created_at: datetime

    # PRD §17.3: GPS verisi DB'ye yazılmaz, ancak konum doğrulaması için
    # sunucu içinde değerlendirilebilir. Response'a doğrudan koymuyoruz —
    # gizlilik politikası gereği. Yerine "GPS bilgisi bulundu mu" sinyali.
    exif_had_gps: bool = Field(
        default=False,
        description="EXIF'te GPS verisi varsa True döner (KVKK: sunucuda "
        "temizlenir, DB'ye yazılmaz).",
    )


class PhotoListItem(BaseModel):
    """Mekanın foto galerisinde gösterilecek özet öğe."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    place_id: uuid.UUID
    user_id: uuid.UUID
    url: str
    thumb_url: str | None
    width: int | None
    height: int | None
    license: str
    taken_at: datetime | None
    created_at: datetime


class PhotoListResponse(BaseModel):
    """``GET /v1/places/{id}/photos`` cevap zarfı."""

    items: list[PhotoListItem]
    total: int
    limit: int
    offset: int
    has_more: bool


class PhotoUploadProblem(BaseModel):
    """OpenAPI dokümantasyonunda hata örnekleri için (RFC 7807).

    Fiili runtime hatası :class:`app.core.exceptions.ProblemDetailsError`
    tarafından üretilir; bu şema sadece swagger için referanstır.
    """

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    code: str | None = None
