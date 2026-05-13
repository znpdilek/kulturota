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
import re
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

from app.core.config import settings
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


# ---------------------------------------------------------------------------
# Türkçe isim çözümleyici — PRD §8.4 ETL `name:tr` boş kaldığında uygulama
# katmanında küçük bir terim haritası ile fallback uygular. Bu sayede ETL
# yeniden çalıştırılmadan da Keşfet panelinde Türkçe etiketler görünür.
# ---------------------------------------------------------------------------
_TR_TERM_MAP: dict[str, str] = {
    "ancient city": "Antik Kenti",
    "ancient theatre": "Antik Tiyatrosu",
    "ancient theater": "Antik Tiyatrosu",
    "archaeological site": "Arkeolojik Alanı",
    "archaeological museum": "Arkeoloji Müzesi",
    "museum": "Müzesi",
    "mosque": "Camii",
    "castle": "Kalesi",
    "fortress": "Kalesi",
    "tower": "Kulesi",
    "bath": "Hamamı",
    "baths": "Hamamı",
    "library": "Kütüphanesi",
    "fountain": "Çeşmesi",
    "aqueduct": "Su Kemeri",
    "church": "Kilisesi",
    "basilica": "Bazilikası",
    "synagogue": "Sinagogu",
    "ruins": "Ören Yeri",
    "agora": "Agorası",
    "necropolis": "Nekropolü",
    "theatre": "Tiyatrosu",
    "theater": "Tiyatrosu",
}

_PROPER_NAME_MAP: dict[str, str] = {
    "ephesus": "Efes",
    "pergamon": "Bergama",
    "pergamum": "Bergama",
    "smyrna": "İzmir (Smyrna)",
    "izmir": "İzmir",
    "kadifekale": "Kadifekale",
    "asclepion": "Asklepion",
    "celsus library": "Celsus Kütüphanesi",
    "house of the virgin mary": "Meryem Ana Evi",
    "temple of artemis": "Artemis Tapınağı",
    "agora of smyrna": "Smyrna Agorası",
    "konak square": "Konak Meydanı",
}


def _translate_to_turkish(value: str | None) -> str | None:
    """İngilizce isimden basit Türkçe karşılığı üretmeye çalış.

    Tam eşleşme önce ``_PROPER_NAME_MAP`` üzerinden aranır; bulunamazsa
    terim sözlüğü ile parça-replace uygulanır. Bu fonksiyon tam çevirmen
    değildir; ETL boşluklarını kullanıcı dostu bir gösterimle örtmeyi
    amaçlar.
    """
    if not value:
        return value
    lower = value.strip().lower()
    if not lower:
        return value
    if lower in _PROPER_NAME_MAP:
        return _PROPER_NAME_MAP[lower]
    result = value
    changed = False
    for en, tr in _TR_TERM_MAP.items():
        if en in lower:
            pattern = re.compile(re.escape(en), re.IGNORECASE)
            result = pattern.sub(tr, result)
            changed = True
    return result if changed else value


def _resolve_isim(isim: dict[str, object] | None) -> dict[str, object]:
    """``isim`` JSONB'ını Türkçe-öncelikli olarak normalize et."""
    if not isim:
        return {"tr": "İsimsiz Mekan"}
    out = dict(isim)
    tr = (out.get("tr") or "").strip() if isinstance(out.get("tr"), str) else None
    en = (out.get("en") or "").strip() if isinstance(out.get("en"), str) else None

    if not tr:
        # En son çare: Türkçe için İngilizce ismi çevir
        candidate = en or next(
            (
                str(v).strip()
                for v in out.values()
                if isinstance(v, str) and v.strip()
            ),
            None,
        )
        if candidate:
            out["tr"] = _translate_to_turkish(candidate) or candidate
    elif en and tr.lower() == en.lower():
        # `tr` ve `en` aynı (ETL fallback'i): yine de çeviri dener.
        translated = _translate_to_turkish(tr)
        if translated and translated != tr:
            out["tr"] = translated
    return out


# --- Helpers ---------------------------------------------------------------
def _coord_of(place: Place) -> Coordinate:
    """``geography(Point)`` → ``Coordinate``."""
    shp = to_shape(place.koordinat)
    return Coordinate(lat=shp.y, lng=shp.x)


def _summary_of(place: Place) -> PlaceSummary:
    return PlaceSummary(
        id=place.id,
        slug=place.slug,
        isim=_resolve_isim(place.isim),
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
        isim=_resolve_isim(place.isim),
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
def _izmir_boundary_geom() -> object:
    """İzmir simplified polygon → PostGIS geometry (SRID 4326)."""
    return func.ST_GeomFromText(settings.IZMIR_BOUNDARY_WKT, 4326)


def _dedupe_summaries(items: list[PlaceSummary]) -> list[PlaceSummary]:
    """Aynı isim + ~yakın koordinatlı kayıtları teke indir.

    ETL dedup adımı (PRD §8.5) eşik altı clusterları kaçırabilir; API
    seviyesinde son bir savunma hattı uygulanır. Anahtar:
    ``(slug-base, lat-3decimal, lng-3decimal)``.
    """
    seen: dict[tuple, PlaceSummary] = {}
    for item in items:
        # Türkçe ismi normalize et (boşluk + case)
        name_tr = ""
        if isinstance(item.isim, dict):
            tr = item.isim.get("tr") or item.isim.get("en") or ""
            name_tr = str(tr).strip().lower()
        # Koordinat hassasiyeti ~110m (3 ondalık)
        key = (
            name_tr,
            round(item.koordinat.lat, 3),
            round(item.koordinat.lng, 3),
        )
        existing = seen.get(key)
        if existing is None:
            seen[key] = item
            continue
        # Tekrar: kalite skoru yüksek olanı tut.
        existing_score = existing.kalite_skoru or 0.0
        new_score = item.kalite_skoru or 0.0
        if new_score > existing_score:
            seen[key] = item
    return list(seen.values())


def list_places(
    db: Session,
    *,
    bbox: tuple[float, float, float, float] | None,
    categories: list[str] | None,
    q: str | None,
    unesco: bool | None,
    limit: int,
    offset: int,
    enforce_izmir: bool = True,
) -> PlaceListResponse:
    """Filtreli mekan listesi (PRD §12.2 — ``GET /v1/places``).

    Args:
        bbox: ``(min_lon, min_lat, max_lon, max_lat)``.
        categories: ``places.kategori && ARRAY[...]`` (overlap).
        q: İsim araması — ``isim->>'tr'`` veya ``isim->>'en'`` ILIKE.
        unesco: True ise sadece UNESCO Dünya Mirası.
        limit/offset: Sayfalama.
        enforce_izmir: True ise İzmir il poligonu zorunlu uygulanır.
    """
    filters: list = [Place.is_published.is_(True)]

    place_geom = cast(Place.koordinat, Geometry(srid=4326))

    if bbox is not None:
        min_lon, min_lat, max_lon, max_lat = bbox
        if (max_lon - min_lon) > MAX_BBOX_DEGREES or (max_lat - min_lat) > MAX_BBOX_DEGREES:
            raise ProblemDetailsError(
                status=400,
                title="Bad Request",
                detail=f"Bbox kenarı en fazla {MAX_BBOX_DEGREES}° olabilir.",
                code="places.bbox_too_large",
            )
        envelope = ST_MakeEnvelope(min_lon, min_lat, max_lon, max_lat, 4326)
        filters.append(ST_Intersects(place_geom, envelope))

    # PRD §8.4 + D1 — pilot şehir İzmir; tüm sorgular il sınırı içinde kalır.
    if enforce_izmir:
        filters.append(func.ST_Within(place_geom, _izmir_boundary_geom()))

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
    raw_items = [_summary_of(p) for p in db.scalars(stmt).all()]
    # API seviyesinde tekilleştirme (ETL clustering eşiği altı kalanları yakalar)
    items = _dedupe_summaries(raw_items)

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

    place_geom = cast(Place.koordinat, Geometry(srid=4326))
    filters: list = [
        Place.is_published.is_(True),
        ST_DWithin(Place.koordinat, origin, radius_m),
        # PRD §8.4 + D1 — İzmir il sınırı dışı kalan koordinatlar sızmasın.
        func.ST_Within(place_geom, _izmir_boundary_geom()),
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
