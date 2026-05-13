"""
Queue Writer — ``ai_decision_queue`` tablosuna yazım
====================================================
PRD §8.5 + §10.2: Pairwise skor ``0.60 ≤ s < 0.90`` olan şüpheli kayıt
çiftlerini AI Karar Katmanı'nın (Adım 3) işleyeceği kuyruğa yazar.

Bu modül **AI çağrısı yapmaz**; sadece ``payload``, ``candidate_place_ids``,
``score`` ve ``reason`` ile satır oluşturur.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.enums import AIDecisionReason, AIDecisionStatus
from app.models.ai_decision_queue import AIDecisionQueue
from etl.dedup.deduper import QueuedPair
from etl.normalize.schema import OpeningHourSlot, RawPlace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Payload serialization
# ---------------------------------------------------------------------------
def _serialize_opening_hour(slot: OpeningHourSlot) -> dict[str, Any]:
    return {
        "day_of_week": slot.day_of_week,
        "opens_at": slot.opens_at,
        "closes_at": slot.closes_at,
        "is_closed_special": slot.is_closed_special,
        "season_start": slot.season_start,
        "season_end": slot.season_end,
        "source": slot.source,
    }


def _serialize_raw_place(record: RawPlace) -> dict[str, Any]:
    """
    :class:`RawPlace`'i PRD §9.4 prompt'u için sade JSON özetine çevir.

    AI Karar Katmanı (Adım 3) bu payload üzerinden LLM prompt'unu kurar.
    Bu yüzden alan isimleri PRD §9.4'teki örnekle hizalı tutulur.
    """
    return {
        "source": record.source,
        "source_id": record.source_id,
        "source_url": record.source_url,
        "license": record.license,
        "name_tr": record.name_tr,
        "name_en": record.name_en,
        "name_de": record.name_de,
        "name_fr": record.name_fr,
        "name_ar": record.name_ar,
        "other_names": record.other_names or {},
        "lat": record.lat,
        "lng": record.lng,
        "canonical_categories": record.canonical_categories or [],
        "raw_categories": record.raw_categories or [],
        "tags": record.tags or [],
        "opening_hours": [_serialize_opening_hour(s) for s in record.opening_hours],
        "wikidata_id": record.wikidata_id,
        "wikipedia_url_tr": record.wikipedia_url_tr,
        "wikipedia_url_en": record.wikipedia_url_en,
        "osm_type": record.osm_type,
        "osm_id": record.osm_id,
        "tarihi_yapim_yili": record.tarihi_yapim_yili,
        "unesco": record.unesco,
        "cover_photo_url": record.cover_photo_url,
        "description_tr": record.description_tr,
        "description_en": record.description_en,
    }


def _queue_payload(pair: QueuedPair) -> dict[str, Any]:
    """PRD §9.4 prompt'una doğrudan beslenecek JSON özeti."""
    return {
        "candidate_a": _serialize_raw_place(pair.record_a),
        "candidate_b": _serialize_raw_place(pair.record_b),
        "scores": {
            "total": float(pair.score.total),
            "geo": float(pair.score.geo),
            "name": float(pair.score.name),
            "category": float(pair.score.category),
            "distance_m": float(pair.score.distance_m),
        },
        "blocking": {
            "geohash": pair.geohash,
            "precision": len(pair.geohash),
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def write_queue_entries(
    db: Session,
    pairs: list[QueuedPair],
) -> list[AIDecisionQueue]:
    """
    Şüpheli çiftleri ``ai_decision_queue`` tablosuna toplu yaz.

    Returns
    -------
    list[AIDecisionQueue]
        Yazılan satırlar (henüz commit edilmemiş).
    """
    written: list[AIDecisionQueue] = []
    for pair in pairs:
        try:
            reason = AIDecisionReason(pair.reason)
        except ValueError:
            reason = AIDecisionReason.LOW_CONFIDENCE

        entry = AIDecisionQueue(
            id=uuid.uuid4(),
            payload=_queue_payload(pair),
            candidate_place_ids=None,  # Henüz Gold place ID'leri yok; AI sonrası bağlanır.
            score=float(pair.score.total),
            reason=reason,
            status=AIDecisionStatus.PENDING,
            retry_count=0,
        )
        db.add(entry)
        written.append(entry)

    logger.info("ai_decision_queue'ya %d çift yazıldı (reason=low_confidence)", len(written))
    return written


__all__ = ["write_queue_entries"]
