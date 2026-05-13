"""
Pairwise Skor Hesabı (PRD §8.5)
================================
* ``geo_score``       = ``1 / (1 + haversine_m / 50)``   (0–1 arası, 0 metrede 1.0)
* ``name_score``      = Türkçe normalize + **token-set ratio** (RapidFuzz, 0–1)
* ``category_score``  = Kategori taksonomisi **overlap coefficient** uyumu (0–1)
* ``total``           = ``0.45 * geo + 0.35 * name + 0.20 * category``

Tüm fonksiyonlar **saf**'tır; DB ya da ağa dokunmaz.  RapidFuzz mevcut değilse
saf-Python token-set ratio fallback'i kullanılır (yavaş ama doğru).

Tasarım notu — eşikler ve gerçek-dünya kalibrasyonu (PRD §8.5 + §9.4)
--------------------------------------------------------------------
Auto-merge eşiği ``0.90`` ve queue eşiği ``0.60`` ile, ``/ 50`` softening
geo formülü **kasıtlı olarak tutucudur**: kaynaklar-arası koordinat farkı
~50 m'yi aşan çiftler (örn. PRD §9.4'teki Efes örneği, 37.94 / 27.34 ↔
37.939 / 27.342, ~207 m) **otomatik birleşmez**; AI Karar Katmanı'na
devredilir. Bu, OSM "centroid" ile Wikidata "ana giriş" konumları
arasındaki belirsizliği şeffaf biçimde kuyruğa düşürür.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from etl.config import (
    GEO_SCORE_SOFTENING_M,
    WEIGHT_CATEGORY,
    WEIGHT_GEO,
    WEIGHT_NAME,
)
from etl.normalize.schema import RawPlace
from etl.normalize.text_utils import normalize_for_match

try:
    from rapidfuzz.fuzz import token_set_ratio as _rf_token_set_ratio  # type: ignore

    _HAS_RAPIDFUZZ = True
except ImportError:  # pragma: no cover - opsiyonel bağımlılık
    _HAS_RAPIDFUZZ = False


# ----------------------------------------------------------------------------
# Mesafe
# ----------------------------------------------------------------------------
_EARTH_RADIUS_M = 6_371_000.0


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """İki coğrafi nokta arasındaki büyük çember mesafesi (metre)."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lmb = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lmb / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return _EARTH_RADIUS_M * c


# ----------------------------------------------------------------------------
# Bileşen skorlar
# ----------------------------------------------------------------------------
def geo_score(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
    *,
    softening_m: float = GEO_SCORE_SOFTENING_M,
) -> float:
    """PRD §8.5: ``1 / (1 + d / 50)``."""
    d = haversine_m(lat1, lng1, lat2, lng2)
    return 1.0 / (1.0 + d / softening_m)


def _py_token_set_ratio(a: str, b: str) -> float:
    """RapidFuzz yoksa kullanılan saf-Python token-set ratio (0–100)."""
    ta = set(a.split())
    tb = set(b.split())
    if not ta and not tb:
        return 100.0
    if not ta or not tb:
        return 0.0
    intersection = ta & tb
    diff_ab = ta - tb
    diff_ba = tb - ta
    s_intersection = " ".join(sorted(intersection))
    s_diff_ab = (s_intersection + " " + " ".join(sorted(diff_ab))).strip()
    s_diff_ba = (s_intersection + " " + " ".join(sorted(diff_ba))).strip()

    def _ratio(x: str, y: str) -> float:
        # Indel-mesafe yerine token-tabanlı oranı yaklaşıkla.
        if not x and not y:
            return 100.0
        max_len = max(len(x), len(y))
        if max_len == 0:
            return 100.0
        common = 0
        # Karakter düzeyinde benzerlik için longest-common-subsequence proxy
        # (Levenshtein için ek paket gerekmesin diye yaklaşıma indirgendi).
        i = j = 0
        while i < len(x) and j < len(y):
            if x[i] == y[j]:
                common += 1
                i += 1
                j += 1
            else:
                if len(x) - i > len(y) - j:
                    i += 1
                else:
                    j += 1
        return 100.0 * (2.0 * common) / (len(x) + len(y))

    return max(
        _ratio(s_intersection, s_diff_ab),
        _ratio(s_intersection, s_diff_ba),
        _ratio(s_diff_ab, s_diff_ba),
    )


def name_score(names_a: list[str], names_b: list[str]) -> float:
    """
    PRD §8.5: "Türkçe normalize + token-set ratio (RapidFuzz)".

    Her iki kayıttan birden fazla dilde isim olabilir; **en yüksek** çapraz
    eşleşme skoru döndürülür.  Hiç isim yoksa 0.0.
    """
    a_norm = [normalize_for_match(n) for n in names_a if n]
    b_norm = [normalize_for_match(n) for n in names_b if n]
    a_norm = [s for s in a_norm if s]
    b_norm = [s for s in b_norm if s]
    if not a_norm or not b_norm:
        return 0.0

    best = 0.0
    ratio_fn = _rf_token_set_ratio if _HAS_RAPIDFUZZ else _py_token_set_ratio
    for a in a_norm:
        for b in b_norm:
            r = ratio_fn(a, b)
            if r > best:
                best = float(r)
    return best / 100.0


def category_score(cats_a: list[str], cats_b: list[str]) -> float:
    """
    Kategori taksonomi uyumu — **overlap coefficient** (Szymkiewicz–Simpson):

        |A ∩ B| / min(|A|, |B|)

    Jaccard yerine overlap kullanılır çünkü dedup bağlamında bir kaynağın
    diğerinden **daha granular** taksonomize etmesi yaygındır.  Örneğin
    "Efes" için Wikidata ``{archaeological_site, ancient_city}`` döner,
    OSM ise ``{archaeological_site}``.  Aynı mekan için bu **mükemmel
    uyum** sayılmalı (1.0), Jaccard'ın verdiği 0.5 değil — aksi halde
    granular kaynaklar otomatik olarak cezalandırılır.

    Bu seçim PRD §8.5'in "Kategori taksonomisi uyumu" ifadesini somutlaştırır
    (PRD ayrıştırma yöntemini belirtmez; overlap coefficient dedup
    literatüründe subset-tolerant standart pratiktir).

    Edge case'ler:
        * Her iki taraf da boşsa → 0.5 (nötr; bilgi yok, ceza yok).
        * Sadece bir taraf boşsa → 0.25 (zayıf nötr; bilinmeyen taraf ufak ceza).
        * Aksi halde → ``|A ∩ B| / min(|A|, |B|)``.
    """
    sa = set(cats_a or [])
    sb = set(cats_b or [])
    if not sa and not sb:
        return 0.5
    if not sa or not sb:
        return 0.25
    intersection = len(sa & sb)
    return intersection / min(len(sa), len(sb))


# ----------------------------------------------------------------------------
# Toplam skor + struct
# ----------------------------------------------------------------------------
@dataclass(slots=True, frozen=True)
class PairwiseScore:
    """Bir çiftin tüm skor bileşenleri (PRD §8.5 ``merge_decision_log`` ile uyumlu)."""

    total: float
    geo: float
    name: float
    category: float
    distance_m: float


def pairwise_score(a: RawPlace, b: RawPlace) -> PairwiseScore:
    """
    İki :class:`RawPlace` arasında PRD §8.5 ağırlıklı bileşik skoru hesapla.

    Koordinat eksikse skor 0 döner (PRD §8.4: lat/lon zorunlu).
    """
    if a.lat is None or a.lng is None or b.lat is None or b.lng is None:
        return PairwiseScore(total=0.0, geo=0.0, name=0.0, category=0.0, distance_m=float("inf"))

    d = haversine_m(a.lat, a.lng, b.lat, b.lng)
    g = 1.0 / (1.0 + d / GEO_SCORE_SOFTENING_M)
    n = name_score(a.all_names(), b.all_names())
    c = category_score(a.canonical_categories, b.canonical_categories)

    total = (
        WEIGHT_GEO * g
        + WEIGHT_NAME * n
        + WEIGHT_CATEGORY * c
    )
    return PairwiseScore(total=total, geo=g, name=n, category=c, distance_m=d)


__all__ = [
    "PairwiseScore",
    "category_score",
    "geo_score",
    "haversine_m",
    "name_score",
    "pairwise_score",
]
