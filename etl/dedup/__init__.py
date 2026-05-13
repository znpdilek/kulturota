"""
ETL — Dedup & Gold Katmanı
==========================
PRD §8.5 algoritmasının saf-Python uygulaması:

1. Geohash-7 ile bloklama (≈ 150m × 150m).
2. Pairwise skor: ``0.45 * geo + 0.35 * name + 0.20 * category``.
3. Eşik kuralları:
   * ``>= 0.90`` → otomatik merge (Gold).
   * ``0.60 - 0.90`` → ``ai_decision_queue``.
   * ``< 0.60`` → ayrı kayıt veya discard.
4. Merge stratejisi: alan bazlı source-priority (PRD §8.5).
"""

from etl.dedup.deduper import DedupResult, DedupCluster, QueuedPair, dedup_records
from etl.dedup.geohash import encode as geohash_encode, neighbors as geohash_neighbors
from etl.dedup.scoring import (
    PairwiseScore,
    category_score,
    geo_score,
    haversine_m,
    name_score,
    pairwise_score,
)

__all__ = [
    "DedupCluster",
    "DedupResult",
    "PairwiseScore",
    "QueuedPair",
    "category_score",
    "dedup_records",
    "geo_score",
    "geohash_encode",
    "geohash_neighbors",
    "haversine_m",
    "name_score",
    "pairwise_score",
]
