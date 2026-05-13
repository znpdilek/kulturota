"""
Review Şemaları (Adım 8 — Sosyal Özellikler / Yorum MVP)
========================================================
PRD §10.2 ``reviews`` tablosu + §12.2 ``/v1/places/{place_id}/reviews``
endpoint ailesinin request/response DTO'ları.

MVP sınırları (kullanıcı talebi)
--------------------------------
* Sadece **temel yorum** akışı (rating 1-5 + opsiyonel metin) kapsamdadır.
* Yorumlara yanıt verme (nested/threaded comments), takip ilişkisi
  (followers/following) ve bildirim altyapısı bu adımda **kapsam dışıdır**.
* AI toksisite filtresi (``toxicity_score``) ve "helpful" oylama akışı
  ileriki adımlara bırakılmıştır; bu uçlar yalnızca **veri yazma/okuma**
  sözleşmesini doldurur.

PRD §10.2'deki ``reviews`` kolonları:
    id, place_id, user_id, rating (1-5), body, visited_at, helpful_count,
    is_flagged, language, toxicity_score, created_at.

Bir kullanıcı bir mekana **yalnızca bir yorum** bırakabilir (servis katmanı +
``UNIQUE(place_id, user_id)`` constraint — Adım 8 migration).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.user import UserPublic

# PRD §10.2: ``body`` Text kolonu. UX talebi gereği kısa yorumlara da izin
# verilir (örn. "Harika!"); minimum 1, maksimum 2000 karakter.
_BODY_MIN = 1
_BODY_MAX = 2_000


class ReviewCreate(BaseModel):
    """``POST /v1/places/{place_id}/reviews`` payload'ı.

    * ``rating`` (1-5) **zorunludur** — PRD §10.2 SmallInteger 1-5.
    * ``body`` opsiyoneldir; verildiğinde 5–2000 karakter olmalıdır
      (boş ya da tek kelimelik yorumlar değer üretmez).
    * ``visited_at`` opsiyoneldir — kullanıcının fiziksel ziyaret tarihi.

    PRD MVP yaklaşımı: AI toksisite filtresi (``toxicity_score``) ve dil
    sezimi (``language``) sunucu tarafında ileriki adımlarda eklenir; bu
    uçtan dışarıdan **kabul edilmez** (güvenilmez veri girişini engelleme).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    rating: Annotated[
        int,
        Field(
            ge=1,
            le=5,
            description="1-5 arası tam sayı (PRD §10.2 SmallInteger).",
        ),
    ]
    body: Annotated[
        str | None,
        Field(
            default=None,
            min_length=_BODY_MIN,
            max_length=_BODY_MAX,
            description="Serbest metin yorum (opsiyonel).",
        ),
    ] = None
    visited_at: Annotated[
        date | None,
        Field(
            default=None,
            description="Kullanıcının mekanı ziyaret ettiği tarih (ISO-8601).",
        ),
    ] = None

    @field_validator("body")
    @classmethod
    def _normalize_body(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    @field_validator("visited_at")
    @classmethod
    def _validate_visited_at(cls, value: date | None) -> date | None:
        if value is None:
            return None
        today = date.today()
        if value > today:
            raise ValueError("Ziyaret tarihi gelecekte olamaz.")
        return value


class ReviewResponse(BaseModel):
    """``POST /reviews`` ve ``GET /reviews`` öğesi için response DTO.

    PRD §10.2'deki tüm yazılı alanları (helpful_count dahil) içerir; ancak
    moderasyon detayları (``is_flagged``, ``toxicity_score``) MVP'de
    istemciye sızdırılmaz — gizlilik & kötüye kullanım önlemi.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    place_id: uuid.UUID
    rating: int = Field(..., ge=1, le=5)
    body: str | None = None
    visited_at: date | None = None
    helpful_count: int = 0
    language: str | None = None
    created_at: datetime
    author: UserPublic = Field(
        ...,
        description=(
            "Yorum sahibi (kamuya açık minimal alanlar). PRD §12.2 — "
            "``/v1/users/{username}`` profil sözleşmesiyle uyumlu."
        ),
    )


class ReviewListResponse(BaseModel):
    """``GET /v1/places/{place_id}/reviews`` cevap zarfı.

    PRD §12.2 — offset/limit pagination (cursor-based ileriki adımda).
    ``aggregate`` bloğu mekan kartında kullanılacak hızlı özet bilgiyi
    taşır: toplam yorum sayısı + ortalama puan (1-5).
    """

    items: list[ReviewResponse]
    total: int
    limit: int
    offset: int
    has_more: bool
    aggregate: "ReviewAggregate"


class ReviewAggregate(BaseModel):
    """Mekan için yorum özet metrikleri (ortalama + sayım)."""

    total: int = Field(default=0, description="Mekana yapılmış toplam yorum sayısı.")
    average_rating: float | None = Field(
        default=None,
        ge=1.0,
        le=5.0,
        description=(
            "1-5 arası ortalama puan; hiç yorum yoksa null döner. UI'da "
            "yıldız rozetini beslemek için kullanılır."
        ),
    )


# Forward-ref tipini çözmek için (ReviewAggregate sınıfından sonra çözüldü).
ReviewListResponse.model_rebuild()


__all__ = [
    "ReviewAggregate",
    "ReviewCreate",
    "ReviewListResponse",
    "ReviewResponse",
]
