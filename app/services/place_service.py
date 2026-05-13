"""
Place Servisi
=============
PRD §10.1 + §12.2 + §18.2.

Sorumluluklar:

    * Filtreli mekan listesi (bbox / kategori / isim arama).
    * Mekan detayı.
    * PostGIS ``ST_DWithin`` ile yakındaki mekanlar.

Tüm sorgular ``places.is_published = true`` filtresi uygular (PRD 11.1
soft-delete bayrağı).
"""

from __future__ import annotations

import logging
import uuid
from typing import Iterable

from geoalchemy2 import Geography, Geometry
from geoalchemy2.functions import (
    ST_Distance,
    ST_DWithin,
    ST_Intersects,
    ST_MakeEnvelope,
)
from geoalchemy2.shape import to_shape
from sqlalchemy import (
    String,
    and_,
    cast,
    func,
    or_,
    select,
)
from sqlalchemy.orm import Session

from app.core.exceptions import ProblemDetailsError
from app.models.place import Place
from app.schemas.place import (
    AttributionItem,
    Coordinate,
    NearbyListResponse,
    NearbyPlace,
    PlaceDetail,
    PlaceListMeta,
    PlaceListResponse,
    PlaceSummary,
)

logger = logging.getLogger(__name__)

# Yakın sorgu için maksimum sınırlar — kötü amaçlı geniş tarama engeli.
MAX_NEARBY_RADIUS_M = 50_000
MAX_BBOX_DEGREES = 5.0


# --- Helpers ---------------------------------------------------------------
def _coord_of(place: Place) -> Coordinate:
    """``geography(Point)`` → ``Coordinate``."""
    shp = to_shape(place.koordinat)
    return Coordinate(lat=shp.y, lng=shp.x)


def _summary_of(place: Place) -> PlaceSummary:
    return PlaceSummary(
        id=place.id,
        slug=place.slug,
        isim=place.isim,
        kategori=list(place.kategori or []),
        koordinat=_coord_of(place),
        kapak_foto_url=place.kapak_foto_url,
        unesco=place.unesco,
        kalite_skoru=float(place.kalite_skoru) if place.kalite_skoru is not None else None,
    )


def _detail_of(place: Place) -> PlaceDetail:
    bbox: dict[str, object] | None = None
    if place.bbox is not None:
        shp = to_shape(place.bbox)
        if shp is not None and not shp.is_empty:
            bbox = {"type": shp.geom_type, "wkt": shp.wkt}
    kaynak: list[AttributionItem] | None = None
    if place.kaynak_atif:
        kaynak = [AttributionItem(**item) for item in place.kaynak_atif]
    return PlaceDetail(
        id=place.id,
        slug=place.slug,
        isim=place.isim,
        kategori=list(place.kategori or []),
        koordinat=_coord_of(place),
        bbox=bbox,
        ziyaret_bilgisi=place.ziyaret_bilgisi,
        etiketler=list(place.etiketler or []),
        tarihi_yapim_yili=place.tarihi_yapim_yili,
        unesco=place.unesco,
        kapak_foto_url=place.kapak_foto_url,
        aciklama=place.aciklama,
        aciklama_source=place.aciklama_source,
        kaynak_atif=kaynak,
        kalite_skoru=float(place.kalite_skoru) if place.kalite_skoru is not None else None,
        merged_from=list(place.merged_from) if place.merged_from else None,
        is_published=place.is_published,
        created_at=place.created_at,
        updated_at=place.updated_at,
    )


def _normalize_categories(categories: Iterable[str] | None) -> list[str]:
    if not categories:
        return []
    return [c.strip().lower() for c in categories if c and c.strip()]


# --- Public API ------------------------------------------------------------
def list_places(
    db: Session,
    *,
    bbox: tuple[float, float, float, float] | None,
    categories: list[str] | None,
    q: str | None,
    unesco: bool | None,
    limit: int,
    offset: int,
) -> PlaceListResponse:
    """Filtreli mekan listesi (PRD §12.2 — ``GET /v1/places``).

    Args:
        bbox: ``(min_lon, min_lat, max_lon, max_lat)``.
        categories: ``places.kategori && ARRAY[...]`` (overlap).
        q: İsim araması — ``isim->>'tr'`` veya ``isim->>'en'`` ILIKE.
        unesco: True ise sadece UNESCO Dünya Mirası.
        limit/offset: Sayfalama.
    """
    filters: list = [Place.is_published.is_(True)]

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        if (max_lon - min_lon) > MAX_BBOX_DEGREES or (max_lat - min_lat) > MAX_BBOX_DEGREES:
            raise ProblemDetailsError(
                status=400,
                title="Bad Request",
                detail=f"Bbox kenarı en fazla {MAX_BBOX_DEGREES}° olabilir.",
                code="places.bbox_too_large",
            )
        # geography → geometry cast; ST_MakeEnvelope SRID parametresi alır.
        envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        place_geom = cast(Place.koordinat, Geometry(srid=4326))
        filters.append(ST_Intersects(place_geom, envelope))

    normalized_categories = _normalize_categories(categories)
    if normalized_categories:
        filters.append(Place.kategori.op("&&")(normalized_categories))

    if q:
        like = f"%{q.strip().lower()}%"
        filters.append(
            or_(
                func.lower(cast(Place.isim["tr"], String)).like(like),
                func.lower(cast(Place.isim["en"], String)).like(like),
                Place.slug.ilike(like),
            )
        )

    if unesco is True:
        filters.append(Place.unesco.is_(True))

    where = and_(*filters)

    total = db.scalar(select(func.count()).select_from(Place).where(where)) or 0

    stmt = (
        select(Place)
        .where(where)
        .order_by(
            Place.kalite_skoru.desc().nullslast(),
            Place.updated_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    items = [_summary_of(p) for p in db.scalars(stmt).all()]

    return PlaceListResponse(
        items=items,
        meta=PlaceListMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            has_more=(offset + len(items)) < int(total),
        ),
    )


def get_place(db: Session, place_id: uuid.UUID) -> PlaceDetail:
    """Mekan detayı + atıf bloğu (PRD §12.2 — ``GET /v1/places/{id}``)."""
    place = db.scalar(
        select(Place).where(Place.id == place_id, Place.is_published.is_(True))
    )
    if place is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Mekan bulunamadı.",
            code="places.not_found",
        )
    return _detail_of(place)


def nearby_places(
    db: Session,
    *,
    lat: float,
    lng: float,
    radius_m: int,
    categories: list[str] | None,
    limit: int,
    offset: int,
) -> NearbyListResponse:
    """PostGIS ``ST_DWithin`` ile yakındaki mekanlar (PRD §12.2 + §18.2).

    Args:
        lat/lng: WGS84 sorgu noktası.
        radius_m: Metre cinsinden yarıçap (``ST_DWithin(geography, geography, m)``).
    """
    if radius_m <= 0 or radius_m > MAX_NEARBY_RADIUS_M:
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail=f"Yarıçap 1-{MAX_NEARBY_RADIUS_M} metre arasında olmalı.",
            code="places.invalid_radius",
        )

    # `geography` tipinde mesafe metre cinsindendir → ST_DWithin/ST_Distance
    # girdileri geography olmalı (PRD §18.2: kısa mesafe için yine de SRID 4326).
    origin = cast(
        func.ST_SetSRID(func.ST_MakePoint(lng, lat), 4326),
        Geography(srid=4326),
    )

    filters: list = [
        Place.is_published.is_(True),
        ST_DWithin(Place.koordinat, origin, radius_m),
    ]
    normalized_categories = _normalize_categories(categories)
    if normalized_categories:
        filters.append(Place.kategori.op("&&")(normalized_categories))

    where = and_(*filters)
    total = db.scalar(select(func.count()).select_from(Place).where(where)) or 0

    distance_expr = ST_Distance(Place.koordinat, origin)
    stmt = (
        select(Place, distance_expr.label("distance_m"))
        .where(where)
        .order_by(distance_expr.asc())
        .limit(limit)
        .offset(offset)
    )

    items: list[NearbyPlace] = []
    for place, distance_m in db.execute(stmt).all():
        summary = _summary_of(place)
        items.append(
            NearbyPlace(
                **summary.model_dump(),
                distance_m=float(distance_m or 0.0),
            )
        )

    return NearbyListResponse(
        items=items,
        meta=PlaceListMeta(
            total=int(total),
            limit=limit,
            offset=offset,
            has_more=(offset + len(items)) < int(total),
        ),
        origin=Coordinate(lat=lat, lng=lng),
        radius_m=radius_m,
    )
