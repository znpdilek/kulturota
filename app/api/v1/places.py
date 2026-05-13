"""
Places Endpoint'leri
====================
PRD §12.2 — Temel mekan uçları.

Rate Limiting (PRD §12.1) → **Public 60 req/dk**.

Bbox formatı: ``min_lon,min_lat,max_lon,max_lat`` (Mapbox / GeoJSON konvansiyonu).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.core.exceptions import ProblemDetailsError
from app.schemas.place import (
    NearbyListResponse,
    PlaceDetail,
    PlaceListResponse,
)
from app.services import place_service

PUBLIC_LIMIT = settings.RATE_LIMIT_PUBLIC_PER_MIN

router = APIRouter(prefix="/places", tags=["places"])

# Sayfa boyutu sınırları — PRD §12.1: cursor-based ileride genişletilecek.
# `_LIMIT_MAX` Keşfet panelindeki "Tümü" akışı için 500 noktaya çıkarıldı;
# bu sınır harita render performansını koruyacak şekilde belirlendi.
_LIMIT_DEFAULT = 100
_LIMIT_MAX = 500


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 4:
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="bbox formatı: min_lon,min_lat,max_lon,max_lat",
            code="places.invalid_bbox",
        )
    try:
        min_lon, min_lat, max_lon, max_lat = (float(p) for p in parts)
    except ValueError as exc:
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="bbox değerleri ondalık sayı olmalı.",
            code="places.invalid_bbox",
        ) from exc

    if not (-180 <= min_lon <= 180 and -180 <= max_lon <= 180):
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="bbox longitude değerleri -180/+180 aralığında olmalı.",
            code="places.invalid_bbox",
        )
    if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="bbox latitude değerleri -90/+90 aralığında olmalı.",
            code="places.invalid_bbox",
        )
    if min_lon >= max_lon or min_lat >= max_lat:
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="bbox: min değerleri max değerlerinden küçük olmalı.",
            code="places.invalid_bbox",
        )
    return min_lon, min_lat, max_lon, max_lat


@router.get(
    "",
    response_model=PlaceListResponse,
    summary="Filtrelenmiş mekan listesi (bbox / kategori / isim)",
    dependencies=[Depends(rate_limit("places.list", limit=PUBLIC_LIMIT))],
)
def list_places(
    db: DbSession,
    bbox: Annotated[
        str | None,
        Query(
            description="`min_lon,min_lat,max_lon,max_lat`",
            examples=["26.0,38.0,28.5,39.0"],
        ),
    ] = None,
    category: Annotated[
        list[str] | None,
        Query(
            description="Tek bir veya birden fazla kategori (overlap).",
            examples=[["museum"], ["historic", "archaeological_site"]],
        ),
    ] = None,
    q: Annotated[
        str | None,
        Query(min_length=1, max_length=120, description="İsim/slug ILIKE araması."),
    ] = None,
    unesco: Annotated[bool | None, Query(description="Sadece UNESCO mirası.")] = None,
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX)] = _LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PlaceListResponse:
    return place_service.list_places(
        db,
        bbox=_parse_bbox(bbox),
        categories=category,
        q=q,
        unesco=unesco,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/nearby",
    response_model=NearbyListResponse,
    summary="PostGIS ST_DWithin ile yakındaki mekanlar",
    dependencies=[Depends(rate_limit("places.nearby", limit=PUBLIC_LIMIT))],
)
def nearby(
    db: DbSession,
    lat: Annotated[float, Query(ge=-90, le=90, description="WGS84 latitude.")],
    lng: Annotated[float, Query(ge=-180, le=180, description="WGS84 longitude.")],
    radius: Annotated[
        int,
        Query(
            ge=1,
            le=50_000,
            description="Yarıçap (metre); maksimum 50.000 m.",
        ),
    ] = 5000,
    category: Annotated[list[str] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX)] = _LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> NearbyListResponse:
    return place_service.nearby_places(
        db,
        lat=lat,
        lng=lng,
        radius_m=radius,
        categories=category,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{place_id}",
    response_model=PlaceDetail,
    summary="Mekan detayı ve atıf bilgileri",
    dependencies=[Depends(rate_limit("places.detail", limit=PUBLIC_LIMIT))],
)
def get_place(place_id: uuid.UUID, db: DbSession) -> PlaceDetail:
    return place_service.get_place(db, place_id)
