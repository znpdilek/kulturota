"""
Place Şemaları
==============
PRD §10.1 + §12.2.

Şema iki "katman" sunar:

    * :class:`PlaceSummary` — Liste (kart) görünümleri için minimal alanlar.
    * :class:`PlaceDetail`  — Detay sayfası için tüm canonical alanlar +
      atıf bloğu (`kaynak_atif`) ve metadata.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Coordinate(BaseModel):
    """WGS84 koordinat (PRD §10.1: ``geography(Point, 4326)``)."""

    lat: float = Field(..., ge=-90, le=90)
    lng: float = Field(..., ge=-180, le=180)


class AttributionItem(BaseModel):
    """``places.kaynak_atif`` içindeki tek bir kaynak girdisi (PRD §10.1 + §20)."""

    src: str = Field(..., description="osm, wikidata, bizizmir, kulturportali …")
    id: str | None = None
    license: str | None = None
    url: str | None = None


class PlaceSummary(BaseModel):
    """Liste/kart cevaplarında dönen minimal mekan modeli."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    isim: dict[str, Any]
    kategori: list[str]
    koordinat: Coordinate
    kapak_foto_url: str | None
    unesco: bool
    kalite_skoru: float | None


class PlaceListMeta(BaseModel):
    """Cursor-based pagination + ODbL atıf bloğu (PRD §20.2)."""

    total: int
    limit: int
    offset: int
    has_more: bool
    attribution: list[str] = Field(
        default_factory=lambda: [
            "© OpenStreetMap contributors (ODbL 1.0)",
            "Wikidata (CC0)",
            "Bizizmir Açık Veri (CC BY 4.0)",
        ]
    )


class PlaceListResponse(BaseModel):
    """``GET /v1/places`` ve ``GET /v1/places/nearby`` ortak cevap zarfı."""

    items: list[PlaceSummary]
    meta: PlaceListMeta


class NearbyPlace(PlaceSummary):
    """``GET /v1/places/nearby`` cevabında mesafe ek alanıyla döner."""

    distance_m: float = Field(..., description="Sorgu noktasına metre cinsinden mesafe.")


class NearbyListResponse(BaseModel):
    """``GET /v1/places/nearby`` cevap zarfı."""

    items: list[NearbyPlace]
    meta: PlaceListMeta
    origin: Coordinate
    radius_m: int


class PlaceDetail(BaseModel):
    """``GET /v1/places/{id}`` — tüm canonical alanlar + atıf bloğu (PRD §10.1)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    slug: str
    isim: dict[str, Any]
    kategori: list[str]
    koordinat: Coordinate
    bbox: dict[str, Any] | None = None
    ziyaret_bilgisi: dict[str, Any] | None
    etiketler: list[str]
    tarihi_yapim_yili: int | None
    unesco: bool
    kapak_foto_url: str | None
    aciklama: dict[str, Any] | None
    aciklama_source: str | None
    kaynak_atif: list[AttributionItem] | None
    kalite_skoru: float | None
    merged_from: list[uuid.UUID] | None
    is_published: bool
    created_at: datetime
    updated_at: datetime
