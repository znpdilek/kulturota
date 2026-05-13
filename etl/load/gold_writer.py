"""
Gold Writer — ``places`` tablosuna yazım
========================================
PRD §8.5 + §10.1: Otomatik birleştirilen :class:`DedupCluster`'ları kanonik
:class:`Place` (Gold) tablosuna **upsert** eder. Ayrıca her cluster için
:class:`MergeDecisionLog` satırı yazarak alan-bazlı kaynak öncelik kararı
audit altına alınır (PRD §8.5 #4).

Bu modül **LLM/AI çağrısı yapmaz** — yalnızca skor ≥ 0.90 olan
deterministic merge kararları için kullanılır. Düşük güvenli kayıtlar
:mod:`etl.load.queue_writer` üzerinden ``ai_decision_queue``'ya yazılır.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from geoalchemy2.elements import WKTElement
from slugify import slugify
from sqlalchemy.orm import Session

from app.core.enums import OpeningHoursSource
from app.models.merge_decision_log import MergeDecisionLog
from app.models.opening_hours import OpeningHours
from app.models.place import Place
from etl.dedup.deduper import DedupCluster
from etl.normalize.schema import OpeningHourSlot, RawPlace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slug üretimi
# ---------------------------------------------------------------------------
def _generate_slug(
    db: Session,
    canonical: RawPlace,
    *,
    max_length: int = 160,
    max_tries: int = 25,
) -> str:
    """
    SEO-dostu slug üret; çakışırsa sonuna ``-2``, ``-3``, ... ekle.

    Çakışmazlık DB UNIQUE constraint ile garanti edilir; bu fonksiyon en
    fazla ``max_tries`` deneme yapar, başaramazsa rastgele suffix ekler.
    """
    base = canonical.best_name() or canonical.wikidata_id or canonical.source_id
    slug_base = slugify(base, max_length=max_length - 6, lowercase=True)
    if not slug_base:
        slug_base = f"yer-{uuid.uuid4().hex[:8]}"

    candidate = slug_base
    for i in range(1, max_tries + 1):
        exists = db.query(Place.id).filter(Place.slug == candidate).limit(1).one_or_none()
        if exists is None:
            return candidate
        candidate = f"{slug_base}-{i + 1}"

    return f"{slug_base}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Place mapping
# ---------------------------------------------------------------------------
def _kaynak_atif_block(cluster: DedupCluster) -> list[dict[str, Any]]:
    """PRD §10.1 ``places.kaynak_atif`` — kümeye katılan her kaydın atıf satırı."""
    seen_keys: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for rec in cluster.members:
        key = (rec.source, rec.source_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(rec.attribution_block())
    return out


def _ziyaret_bilgisi_block(canonical: RawPlace) -> dict[str, Any]:
    """PRD §10.1: ``acilis_kapanis``, ``muzekart_gecerli`` (D2 statik), ``giris_ucretleri``."""
    block: dict[str, Any] = {
        # D2: Müzekart resmi API yok; statik bayrak — varsayılan False.
        "muzekart_gecerli": False,
        "giris_ucretleri": None,
    }
    if canonical.opening_hours:
        block["acilis_kapanis"] = [
            {
                "day_of_week": s.day_of_week,
                "opens_at": s.opens_at,
                "closes_at": s.closes_at,
                "is_closed_special": s.is_closed_special,
                "source": s.source,
            }
            for s in canonical.opening_hours
        ]
    return block


def _kalite_skoru(cluster: DedupCluster) -> float:
    """
    Basit DQ skoru: cluster için minimum pair skoru (singleton ise 0.95).
    """
    if cluster.is_singleton:
        return 0.95
    return round(cluster.min_pair_score, 2)


def _to_opening_hours_rows(slots: list[OpeningHourSlot], place_id: uuid.UUID) -> list[OpeningHours]:
    rows: list[OpeningHours] = []
    for slot in slots:
        if slot.day_of_week is None or not (0 <= slot.day_of_week <= 6):
            continue
        opens_t = _parse_hhmm(slot.opens_at)
        closes_t = _parse_hhmm(slot.closes_at)
        try:
            source_enum = OpeningHoursSource(slot.source)
        except ValueError:
            # Bilinmeyen kaynak: OSM fallback olarak işaretle
            source_enum = OpeningHoursSource.OSM
        rows.append(
            OpeningHours(
                place_id=place_id,
                day_of_week=slot.day_of_week,
                opens_at=opens_t,
                closes_at=closes_t,
                is_closed_special=slot.is_closed_special,
                source=source_enum,
            )
        )
    return rows


def _parse_hhmm(value: str | None):
    """``"09:30"`` → :class:`datetime.time`; geçersizse ``None``."""
    if not value:
        return None
    from datetime import time

    try:
        hh, mm = value.split(":", 1)
        return time(int(hh), int(mm))
    except (ValueError, TypeError):
        return None


def _coordinate_wkt(canonical: RawPlace) -> WKTElement:
    """PostGIS ``geography(Point, 4326)`` için WKT element üret."""
    return WKTElement(
        f"POINT({canonical.lng} {canonical.lat})",
        srid=4326,
        extended=False,
    )


def _build_place(
    db: Session,
    cluster: DedupCluster,
) -> Place:
    canonical = cluster.canonical
    slug = _generate_slug(db, canonical)
    return Place(
        id=uuid.uuid4(),
        slug=slug,
        isim=canonical.to_isim_jsonb(),
        kategori=canonical.canonical_categories or [],
        koordinat=_coordinate_wkt(canonical),
        bbox=None,
        ziyaret_bilgisi=_ziyaret_bilgisi_block(canonical),
        etiketler=canonical.tags or [],
        tarihi_yapim_yili=canonical.tarihi_yapim_yili,
        unesco=canonical.unesco,
        kapak_foto_url=canonical.cover_photo_url,
        aciklama=canonical.to_aciklama_jsonb(),
        aciklama_source=("wikipedia" if canonical.source == "wikidata" and canonical.description_tr else None),
        kaynak_atif=_kaynak_atif_block(cluster),
        kalite_skoru=_kalite_skoru(cluster),
        merged_from=None,  # Cluster üyelerinin önceki place_id'leri yok (ilk yazım).
        is_published=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def write_clusters_to_gold(
    db: Session,
    clusters: list[DedupCluster],
    *,
    etl_run_id: uuid.UUID | None = None,
) -> tuple[list[Place], list[MergeDecisionLog]]:
    """
    Otomatik merge cluster'larını ``places`` tablosuna yaz; her cluster için
    bir :class:`MergeDecisionLog` satırı (lineage) üret.

    Bu fonksiyon TX'i kapatmaz (caller ``db.commit()`` çağırmalıdır) — bu
    sayede aynı pipeline run'ında diğer yazımlarla atomik birlikte gönderilir.

    Returns
    -------
    tuple
        ``(written_places, written_logs)``
    """
    written_places: list[Place] = []
    written_logs: list[MergeDecisionLog] = []

    for cluster in clusters:
        place = _build_place(db, cluster)
        db.add(place)
        db.flush()  # place.id kullanılabilsin

        # Opening hours alt-tabloya
        oh_rows = _to_opening_hours_rows(cluster.canonical.opening_hours, place.id)
        for row in oh_rows:
            db.add(row)

        # Merge decision lineage
        if etl_run_id is not None:
            log = MergeDecisionLog(
                id=uuid.uuid4(),
                etl_run_id=etl_run_id,
                place_id=place.id,
                source_record_ids=None,
                score=cluster.min_pair_score,
                geo_score=None,
                name_score=None,
                category_score=None,
                primary_source_per_field=cluster.primary_source_per_field,
                decision="auto_merge" if not cluster.is_singleton else "auto_insert",
                note=(
                    f"members={len(cluster.members)} sources="
                    + ",".join(sorted({m.source for m in cluster.members}))
                ),
            )
            db.add(log)
            written_logs.append(log)

        written_places.append(place)

    logger.info(
        "Gold yazıldı: %d place (auto_merge=%d, singleton=%d)",
        len(written_places),
        sum(1 for c in clusters if not c.is_singleton),
        sum(1 for c in clusters if c.is_singleton),
    )
    return written_places, written_logs


__all__ = ["write_clusters_to_gold"]
