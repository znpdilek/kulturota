"""
Dedup Algoritması (PRD §8.5)
============================
Geohash-7 bloklama + pairwise skor + eşik kuralları.

Adımlar:
    1. Her :class:`RawPlace` için ``geohash-7`` üret; aynı geohash'i paylaşan
       kayıtlar (opsiyonel: + komşu bloklar) aday çiftler oluşturur.
    2. Aynı blok içindeki tüm çiftler için ``pairwise_score`` hesapla.
    3. **Union-Find** ile, ``score >= AUTO_MERGE_THRESHOLD (0.90)`` kenarlardan
       cluster oluştur — bunlar "kesin aynı mekan" gruplarıdır.
    4. ``0.60 <= score < 0.90`` aralığındaki kenarları "şüpheli" olarak işaretle.
       Eğer kenarın iki ucu farklı cluster'larda ise, bu çifti
       ``ai_decision_queue``'ya yönlendir (PRD §8.5).
    5. Cluster'ları :func:`merge_cluster` ile tek kanonik ``RawPlace``'a indir.
    6. Cluster içinde olmayıp şüpheli kenarı da olmayan kayıtlar singleton.

Adım 3'teki AI Karar Katmanı (PRD §9) bu modülün **kapsamı dışındadır** — burada
yalnızca kuyruğa yazma sinyali üretilir; LLM çağrısı Adım 3'te.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from etl.config import (
    AUTO_MERGE_THRESHOLD,
    COMPARE_NEIGHBOR_BLOCKS,
    GEOHASH_PRECISION,
    QUEUE_THRESHOLD,
    REQUIRE_ANY_NAME,
)
from etl.dedup.geohash import encode as geohash_encode
from etl.dedup.geohash import neighbors as geohash_neighbors
from etl.dedup.merger import merge_cluster
from etl.dedup.scoring import PairwiseScore, pairwise_score
from etl.normalize.schema import RawPlace

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Sonuç tipleri
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DedupCluster:
    """Otomatik birleştirilen bir Gold kayıt adayı (PRD §8.5)."""

    canonical: RawPlace
    members: list[RawPlace]
    primary_source_per_field: dict[str, str | None]
    geohash: str
    min_pair_score: float
    max_pair_score: float

    @property
    def is_singleton(self) -> bool:
        return len(self.members) == 1


@dataclass(slots=True)
class QueuedPair:
    """``ai_decision_queue``'ya yazılacak şüpheli kayıt çifti (PRD §8.5)."""

    record_a: RawPlace
    record_b: RawPlace
    score: PairwiseScore
    geohash: str
    reason: str = "low_confidence"  # AIDecisionReason ile uyumlu


@dataclass(slots=True)
class DedupResult:
    """Dedup motorunun tüm çıktıları."""

    clusters: list[DedupCluster] = field(default_factory=list)
    queued_pairs: list[QueuedPair] = field(default_factory=list)
    discarded: list[RawPlace] = field(default_factory=list)

    @property
    def gold_writes(self) -> int:
        return len(self.clusters)


# ---------------------------------------------------------------------------
# Union-Find (Disjoint Set Union)
# ---------------------------------------------------------------------------
class _DSU:
    __slots__ = ("parent", "rank")

    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True

    def components(self) -> dict[int, list[int]]:
        out: dict[int, list[int]] = defaultdict(list)
        for i in range(len(self.parent)):
            out[self.find(i)].append(i)
        return out


# ---------------------------------------------------------------------------
# Çekirdek algoritma
# ---------------------------------------------------------------------------
def _bucket_by_geohash(
    records: list[RawPlace],
    precision: int,
) -> dict[str, list[int]]:
    """Her geohash bloğuna ait kayıt indeksleri sözlüğü."""
    buckets: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        if r.lat is None or r.lng is None:
            continue
        gh = geohash_encode(r.lat, r.lng, precision=precision)
        buckets[gh].append(i)
    return buckets


def _build_candidate_pairs(
    buckets: dict[str, list[int]],
    *,
    compare_neighbors: bool,
) -> set[tuple[int, int, str]]:
    """
    Aynı blok (+ opsiyonel komşu blok) içindeki tüm çift kombinasyonlarını üret.

    Pair tuple: ``(i, j, geohash_of_i)`` — i < j garantilenir.
    """
    pairs: set[tuple[int, int, str]] = set()

    if compare_neighbors:
        # Komşuları içeren genişletilmiş blok listesi.
        for gh, members in buckets.items():
            for n_gh in (gh, *geohash_neighbors(gh)):
                neighbour_members = buckets.get(n_gh)
                if not neighbour_members:
                    continue
                for i in members:
                    for j in neighbour_members:
                        if i == j:
                            continue
                        a, b = (i, j) if i < j else (j, i)
                        pairs.add((a, b, gh))
    else:
        for gh, members in buckets.items():
            n = len(members)
            for x in range(n):
                for y in range(x + 1, n):
                    pairs.add((members[x], members[y], gh))
    return pairs


def dedup_records(
    records: list[RawPlace],
    *,
    precision: int = GEOHASH_PRECISION,
    auto_merge_threshold: float = AUTO_MERGE_THRESHOLD,
    queue_threshold: float = QUEUE_THRESHOLD,
    compare_neighbors: bool = COMPARE_NEIGHBOR_BLOCKS,
    require_name: bool = REQUIRE_ANY_NAME,
) -> DedupResult:
    """
    PRD §8.5 dedup algoritmasını uygula.

    Parameters
    ----------
    records : list[RawPlace]
        Silver katmanından gelen normalize edilmiş kayıtlar (geofence uygulanmış).
    precision : int
        Geohash hassasiyeti (default 7 — PRD §8.5).
    auto_merge_threshold : float
        ``score >= bu`` → otomatik merge.
    queue_threshold : float
        ``score >= bu and < auto_merge_threshold`` → ``ai_decision_queue``.
    compare_neighbors : bool
        Sınır kayıtlar için komşu geohash bloklarını da karşılaştır.
    require_name : bool
        Hiç ismi olmayan kayıtlar discard mı edilsin?

    Returns
    -------
    DedupResult
        Otomatik merge cluster'ları + kuyruğa düşen çiftler + discard'lar.
    """
    n = len(records)
    if n == 0:
        return DedupResult()

    logger.info(
        "Dedup başladı: %d kayıt, precision=%d, auto>=%.2f, queue>=%.2f",
        n,
        precision,
        auto_merge_threshold,
        queue_threshold,
    )

    result = DedupResult()

    # --- Eksik veri filtresi (PRD §8.4) ----------------------------------
    valid_indices: list[int] = []
    for i, r in enumerate(records):
        if r.lat is None or r.lng is None:
            result.discarded.append(r)
            continue
        if require_name and not r.best_name():
            result.discarded.append(r)
            continue
        valid_indices.append(i)

    if not valid_indices:
        logger.warning("Dedup: tüm kayıtlar discard edildi.")
        return result

    working = [records[i] for i in valid_indices]
    m = len(working)

    # --- 1. Geohash bloklama --------------------------------------------
    buckets = _bucket_by_geohash(working, precision=precision)
    logger.info(
        "Dedup: %d kayıt, %d geohash-%d blok (ortalama %.1f kayıt/blok)",
        m,
        len(buckets),
        precision,
        m / max(len(buckets), 1),
    )

    # --- 2. Aday çiftler -------------------------------------------------
    candidate_pairs = _build_candidate_pairs(buckets, compare_neighbors=compare_neighbors)

    # --- 3. Pairwise skor + DSU (kesin merge) ---------------------------
    dsu = _DSU(m)
    edge_score: dict[tuple[int, int], PairwiseScore] = {}
    edge_geohash: dict[tuple[int, int], str] = {}
    ambiguous_edges: list[tuple[int, int]] = []

    for i, j, gh in candidate_pairs:
        score = pairwise_score(working[i], working[j])
        edge_score[(i, j)] = score
        edge_geohash[(i, j)] = gh

        if score.total >= auto_merge_threshold:
            dsu.union(i, j)
        elif score.total >= queue_threshold:
            ambiguous_edges.append((i, j))

    # --- 4. Cluster oluştur ve merge ------------------------------------
    components = dsu.components()
    for root, member_indices in components.items():
        members = [working[idx] for idx in member_indices]

        # min/max pair skoru — sadece cluster içinden
        intra_scores: list[float] = []
        for x in range(len(member_indices)):
            for y in range(x + 1, len(member_indices)):
                a, b = sorted((member_indices[x], member_indices[y]))
                s = edge_score.get((a, b))
                if s is not None:
                    intra_scores.append(s.total)
        min_s = min(intra_scores) if intra_scores else 1.0
        max_s = max(intra_scores) if intra_scores else 1.0

        canonical, lineage = merge_cluster(members)
        gh = geohash_encode(canonical.lat or 0.0, canonical.lng or 0.0, precision=precision)
        result.clusters.append(
            DedupCluster(
                canonical=canonical,
                members=members,
                primary_source_per_field=lineage,
                geohash=gh,
                min_pair_score=min_s,
                max_pair_score=max_s,
            )
        )

    # --- 5. Şüpheli çiftleri kuyruğa düşür ------------------------------
    for i, j in ambiguous_edges:
        ri, rj = dsu.find(i), dsu.find(j)
        if ri == rj:
            # Bir başka 0.9+ kenardan zaten aynı cluster'da → kuyruğa atma.
            continue
        score = edge_score[(i, j)]
        gh = edge_geohash[(i, j)]
        result.queued_pairs.append(
            QueuedPair(
                record_a=working[i],
                record_b=working[j],
                score=score,
                geohash=gh,
                reason="low_confidence",
            )
        )

    logger.info(
        "Dedup tamamlandı: %d cluster (gold yazım), %d şüpheli çift (queue), %d discard",
        len(result.clusters),
        len(result.queued_pairs),
        len(result.discarded),
    )
    return result


__all__ = [
    "DedupCluster",
    "DedupResult",
    "QueuedPair",
    "dedup_records",
]
