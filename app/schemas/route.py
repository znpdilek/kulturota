"""
Route Şemaları
==============
PRD §10.2 (``routes`` + ``route_stops``) + §12.2 (``/v1/routes`` ailesi).
Adım 7 — Rota Yönetimi (Core MVP).

Bu modül üç katman sunar:

    * :class:`RouteSummary`              — Liste cevaplarında dönen minimal model.
    * :class:`RouteDetail`               — Detay cevabında ``stops`` sıralı liste.
    * :class:`RouteStopWithPlace`        — GET detayında sunulan stop öğesi;
      mekanın temel bilgisini (isim + koordinat + slug) inline taşır.

MVP sınırları (kullanıcı talebi gereği)
---------------------------------------
* Algoritmik rota optimizasyonu **YOK** (TSP, kısıtlı VRP vb. — PRD §15.1
  ileri adımlarda).
* İki mekan arası süre/mesafe hesabı **YOK**.
* Sosyal alanlar (``route_likes``, ``route_comments``) bu adımda dokunulmaz.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.core.enums import RouteDifficulty
from app.schemas.place import Coordinate

# ``routes.title`` PRD §10.2 → String(200). Min uzunluk UI deneyimi için.
_TITLE_MIN = 3
_TITLE_MAX = 200
_THEME_MAX = 80
_NOTES_MAX = 1_000


# ---------------------------------------------------------------------------
# Route — request payload'ları
# ---------------------------------------------------------------------------
class RouteCreate(BaseModel):
    """``POST /v1/routes`` payload'ı.

    Tüm alanlar opsiyonel hariç ``title``. PRD §10.2 ``est_duration_min`` ve
    ``total_distance_km`` rota motoru tarafından üretildiği için bu uçtan
    kabul edilmez (MVP yaklaşımı).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Annotated[str, Field(min_length=_TITLE_MIN, max_length=_TITLE_MAX)]
    description: Annotated[
        dict[str, Any] | None,
        Field(
            default=None,
            description=(
                "Çok dilli açıklama (örn. {'tr': '...', 'en': '...'}). "
                "Serbest JSONB; sunucu içeriği yorumlamaz."
            ),
        ),
    ] = None
    theme: Annotated[str | None, Field(default=None, max_length=_THEME_MAX)] = None
    is_public: bool = False
    cover_image_url: AnyHttpUrl | None = None
    difficulty: RouteDifficulty | None = None

    @field_validator("title")
    @classmethod
    def _strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < _TITLE_MIN:
            raise ValueError(f"Başlık en az {_TITLE_MIN} karakter olmalı.")
        return cleaned


class RouteUpdate(BaseModel):
    """``PUT /v1/routes/{id}`` — PATCH semantiği (yalnızca verilen alanlar).

    En az bir alan gönderilmelidir; aksi halde 422 döner.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: Annotated[
        str | None,
        Field(default=None, min_length=_TITLE_MIN, max_length=_TITLE_MAX),
    ] = None
    description: dict[str, Any] | None = None
    theme: Annotated[str | None, Field(default=None, max_length=_THEME_MAX)] = None
    is_public: bool | None = None
    cover_image_url: AnyHttpUrl | None = None
    difficulty: RouteDifficulty | None = None

    @model_validator(mode="after")
    def _require_at_least_one(self) -> "RouteUpdate":
        if not self.model_fields_set:
            raise ValueError("Güncellenecek en az bir alan göndermelisiniz.")
        return self


# ---------------------------------------------------------------------------
# Route — response modelleri
# ---------------------------------------------------------------------------
class RouteSummary(BaseModel):
    """Liste cevabında dönen minimal rota modeli (PRD §10.2)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: dict[str, Any] | None = None
    theme: str | None = None
    is_public: bool
    cover_image_url: str | None = None
    est_duration_min: int | None = None
    total_distance_km: float | None = None
    difficulty: RouteDifficulty | None = None
    stop_count: int = Field(
        default=0,
        description="Rotaya bağlı stop sayısı (sıralama bütünlüğü için).",
    )
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# RouteStop — request payload'ları
# ---------------------------------------------------------------------------
class RouteStopCreate(BaseModel):
    """``POST /v1/routes/{id}/stops`` payload'ı.

    ``order_index`` opsiyoneldir; gönderilmezse sunucu **mevcut max + 1**
    atayarak stop'u listenin sonuna ekler. Açıkça gönderildiğinde
    ``(route_id, order_index)`` UNIQUE constraint (PRD §10.2) nedeniyle
    çakışırsa 409 döner — kullanıcı önce farklı bir sıra seçmelidir.
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    place_id: uuid.UUID
    order_index: Annotated[int | None, Field(default=None, ge=0, le=10_000)] = None
    planned_arrival: datetime | None = None
    planned_duration_min: Annotated[
        int | None,
        Field(default=None, ge=1, le=24 * 60),
    ] = None
    notes: Annotated[str | None, Field(default=None, max_length=_NOTES_MAX)] = None


class RouteStopUpdate(BaseModel):
    """``PATCH /v1/routes/{id}/stops/{stop_id}`` — kısmi güncelleme.

    ``order_index`` değişikliğine bu adımda izin **verilmez**: rota motoru
    (PRD §15.1) ileride yeniden sıralamayı algoritmik yapacaktır. Sıralamayı
    elle değiştirmek için stop'u silip yeniden ekleyin (sıralı liste mantığı).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    planned_arrival: datetime | None = None
    planned_duration_min: Annotated[
        int | None,
        Field(default=None, ge=1, le=24 * 60),
    ] = None
    notes: Annotated[str | None, Field(default=None, max_length=_NOTES_MAX)] = None

    @model_validator(mode="after")
    def _require_at_least_one(self) -> "RouteStopUpdate":
        if not self.model_fields_set:
            raise ValueError("Güncellenecek en az bir alan göndermelisiniz.")
        return self


# ---------------------------------------------------------------------------
# RouteStop — response modelleri
# ---------------------------------------------------------------------------
class PlaceMini(BaseModel):
    """Stop yanıtlarında inline gelen mekan özet bilgisi.

    PRD §12.2 detay uçları "isim + koordinat" zorunlu kontratı; ileride
    galeri/açıklama gerekiyorsa ``/v1/places/{id}`` çağrısı yapılır.
    """

    id: uuid.UUID
    slug: str
    isim: dict[str, Any]
    koordinat: Coordinate
    kategori: list[str] = Field(default_factory=list)
    kapak_foto_url: str | None = None


class RouteStopWithPlace(BaseModel):
    """``GET /v1/routes/{id}/stops`` ve ``RouteDetail.stops`` öğesi.

    Sıralama ``order_index`` artan yönde sunulur (PRD §10.2 unique constraint
    sayesinde stabildir).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    route_id: uuid.UUID
    place_id: uuid.UUID
    order_index: int
    planned_arrival: datetime | None = None
    planned_duration_min: int | None = None
    notes: str | None = None
    place: PlaceMini


class RouteStopListResponse(BaseModel):
    """``GET /v1/routes/{id}/stops`` cevap zarfı."""

    items: list[RouteStopWithPlace]
    total: int


# ---------------------------------------------------------------------------
# Route detail (ordered stops embedded)
# ---------------------------------------------------------------------------
class RouteDetail(RouteSummary):
    """``GET /v1/routes/{id}`` — rota + sıralı stop listesi (PRD §12.2)."""

    stops: list[RouteStopWithPlace] = Field(default_factory=list)


class RouteListResponse(BaseModel):
    """``GET /v1/routes`` cevap zarfı."""

    items: list[RouteSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


__all__ = [
    "PlaceMini",
    "RouteCreate",
    "RouteDetail",
    "RouteListResponse",
    "RouteStopCreate",
    "RouteStopListResponse",
    "RouteStopUpdate",
    "RouteStopWithPlace",
    "RouteSummary",
    "RouteUpdate",
]
