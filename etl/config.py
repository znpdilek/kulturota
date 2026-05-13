"""
ETL Konfigürasyonu
==================
PRD §8 (ETL Pipeline) ve §2 D1 (Pilot Şehir = İzmir) için tüm sabitler.

Hiçbir extract/normalize/dedup fonksiyonu doğrudan ``app.core.config.settings``
kullanmaz; ETL için izole, override edilebilir bir sabit kümesi tutulur.
``BoundingBox`` değerleri PRD'deki ``bbox=26.0,38.0,28.5,39.0`` ile birebir
aynıdır ve **DEĞİŞTİRİLMEMELİDİR** (D1 kararı).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# ----------------------------------------------------------------------------
# D1 — Pilot bbox (PRD §2 ve §8.1)
# ----------------------------------------------------------------------------
@dataclass(frozen=True)
class BoundingBox:
    """``(west, south, east, north)`` köşeleriyle dikdörtgensel coğrafi kutu."""

    west: float
    south: float
    east: float
    north: float

    def contains(self, lat: float, lng: float) -> bool:
        """Bir nokta bbox içinde mi? (PRD §8.4 Geofence kuralı)."""
        return self.south <= lat <= self.north and self.west <= lng <= self.east

    def as_overpass_box(self) -> str:
        """Overpass QL ``(south,west,north,east)`` formatında string."""
        return f"{self.south},{self.west},{self.north},{self.east}"

    def as_dict(self) -> dict[str, float]:
        return {
            "west": self.west,
            "south": self.south,
            "east": self.east,
            "north": self.north,
        }


# PRD §2 D1 + §8.1: İzmir pilot bbox — DEĞİŞTİRMEYİN.
IZMIR_BBOX: BoundingBox = BoundingBox(
    west=26.0,
    south=38.0,
    east=28.5,
    north=39.0,
)


# ----------------------------------------------------------------------------
# Bronze Lake (PRD §8.3) — yerel filesystem partition'ları
# ----------------------------------------------------------------------------
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
BRONZE_DIR: Path = Path(
    os.getenv("ETL_BRONZE_DIR", str(PROJECT_ROOT / "etl" / "bronze"))
).resolve()


# ----------------------------------------------------------------------------
# Extract — HTTP endpoint'leri (env ile override edilebilir)
# ----------------------------------------------------------------------------
OVERPASS_ENDPOINT: str = os.getenv(
    "ETL_OVERPASS_ENDPOINT",
    "https://overpass-api.de/api/interpreter",
)
WIKIDATA_SPARQL_ENDPOINT: str = os.getenv(
    "ETL_WIKIDATA_SPARQL_ENDPOINT",
    "https://query.wikidata.org/sparql",
)
BIZIZMIR_CKAN_BASE_URL: str = os.getenv(
    "ETL_BIZIZMIR_BASE_URL",
    "https://acikveri.bizizmir.com",
)

# Bizizmir CKAN dataset arama anahtarları (PRD §8.1: çalışma saatleri/günleri)
BIZIZMIR_SEARCH_QUERIES: tuple[str, ...] = (
    "müze",
    "kültürel mekan",
    "tarihi yerler",
)


# Overpass server-side timeout (saniye); HTTP timeout bunun üstüne bir buffer ekler.
OVERPASS_TIMEOUT_S: int = int(os.getenv("ETL_OVERPASS_TIMEOUT", "180"))

# Genel HTTP zaman aşımları (saniye)
HTTP_TIMEOUT_S: float = float(os.getenv("ETL_HTTP_TIMEOUT", "60"))

# PRD §20: User-Agent zorunlu (OSM kullanım politikası).
USER_AGENT: str = os.getenv(
    "ETL_USER_AGENT",
    "KulturRota-ETL/0.1 (+contact: data@kulturrota.example)",
)


# ----------------------------------------------------------------------------
# Silver — eksik veri kuralları (PRD §8.4)
# ----------------------------------------------------------------------------
# PRD §8.4: name_tr veya name_en yoksa ai_decision_queue'ya düşer.
REQUIRE_ANY_NAME: bool = True

# Çok kısa isimleri (örn. tek karakter, sadece sayı) reddet.
MIN_NAME_LENGTH: int = 2


# ----------------------------------------------------------------------------
# Gold — Dedup eşikleri (PRD §8.5)
# ----------------------------------------------------------------------------
# Geohash hassasiyeti — PRD §8.5 "Block by Geohash-7 (~150m × 150m)".
GEOHASH_PRECISION: int = 7

# Pairwise skor ağırlıkları (PRD §8.5)
WEIGHT_GEO: float = 0.45
WEIGHT_NAME: float = 0.35
WEIGHT_CATEGORY: float = 0.20

# Geo skor "yumuşatma" sabiti (metre) — PRD §8.5: ``1 / (1 + d / 50)``.
#
# 50 m kasıtlı tutucu: kaynaklar-arası ~10-30 m'lik gerçek POI uyumlarında
# geo_score yüksek (~0.83-0.62) kalır → name+category güçlüyse auto-merge.
# 100 m+ farklarda geo_score hızla düşer (~0.33) → PRD §9.4'teki örnekte
# olduğu gibi kayıt AI Karar Katmanı'na devredilir (queue).
#
# Bu sabit değiştirilirse mentor onayı alın — auto-merge yanlış birleştirme
# (false positive) risk profilini doğrudan etkiler.
GEO_SCORE_SOFTENING_M: float = 50.0

# Eşikler — PRD §8.5
AUTO_MERGE_THRESHOLD: float = 0.90
QUEUE_THRESHOLD: float = 0.60

# Komşu geohash bloklarını da kıyasla? Sınırda olan kayıtları yakalar.
COMPARE_NEIGHBOR_BLOCKS: bool = True


# ----------------------------------------------------------------------------
# Source priority — Merge alanında hangi kaynağın değeri öncelikli? (PRD §8.5)
# ----------------------------------------------------------------------------
SOURCE_PRIORITY: dict[str, tuple[str, ...]] = {
    # Koordinat → OSM en güvenilir.
    "koordinat": ("osm", "wikidata", "bizizmir", "portal"),
    # Çok-dilli isim → Wikidata canonical.
    "isim": ("wikidata", "osm", "bizizmir", "portal"),
    # Kategori taksonomisi → OSM tag'leri en zengin.
    "kategori": ("osm", "wikidata", "portal", "bizizmir"),
    # Tescil/UNESCO → Resmi portal.
    "tescil": ("portal", "wikidata", "osm"),
    # Açıklama → Wikidata/Wikipedia.
    "aciklama": ("wikidata", "portal", "osm"),
    # Görsel → Wikidata (CC0 Wikimedia).
    "kapak_foto_url": ("wikidata", "portal", "osm"),
    # Çalışma saatleri → Bizizmir (D1 pilot kaynağı).
    "opening_hours": ("bizizmir", "osm", "portal"),
    # Yapım yılı → Wikidata.
    "tarihi_yapim_yili": ("wikidata", "portal", "osm"),
}


# ----------------------------------------------------------------------------
# AI Karar Kuyruğu (PRD §10.2) — eşik altı kayıtlar için sebep kodları
# ----------------------------------------------------------------------------
# Bu sabitler ``app.core.enums.AIDecisionReason`` ile birebir eşleşmelidir.
QUEUE_REASON_LOW_CONFIDENCE: str = "low_confidence"
QUEUE_REASON_MISSING_FIELD: str = "missing_field"
QUEUE_REASON_CONFLICT: str = "conflict"
QUEUE_REASON_GEOFENCE: str = "geofence"


__all__ = [
    "AUTO_MERGE_THRESHOLD",
    "BIZIZMIR_CKAN_BASE_URL",
    "BIZIZMIR_SEARCH_QUERIES",
    "BRONZE_DIR",
    "BoundingBox",
    "COMPARE_NEIGHBOR_BLOCKS",
    "GEOHASH_PRECISION",
    "GEO_SCORE_SOFTENING_M",
    "HTTP_TIMEOUT_S",
    "IZMIR_BBOX",
    "MIN_NAME_LENGTH",
    "OVERPASS_ENDPOINT",
    "OVERPASS_TIMEOUT_S",
    "PROJECT_ROOT",
    "QUEUE_REASON_CONFLICT",
    "QUEUE_REASON_GEOFENCE",
    "QUEUE_REASON_LOW_CONFIDENCE",
    "QUEUE_REASON_MISSING_FIELD",
    "QUEUE_THRESHOLD",
    "REQUIRE_ANY_NAME",
    "SOURCE_PRIORITY",
    "USER_AGENT",
    "WEIGHT_CATEGORY",
    "WEIGHT_GEO",
    "WEIGHT_NAME",
    "WIKIDATA_SPARQL_ENDPOINT",
]
