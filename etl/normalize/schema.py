"""
Silver Katmanı Kanonik Şeması
=============================
PRD §8.4: "Tüm kayıtlar tek bir kanonik şemaya (``raw_place``) eşlenir."

:class:`RawPlace` her kaynaktan (Overpass, Wikidata, Bizizmir, Portal) gelen ham
kayıtların **dönüştürülmüş**, **normalize edilmiş** Silver temsilidir. Bu obje
hem dedup katmanına hem de Gold yazımına (PRD §8.5) girdi olur.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# Atıf bloğunda kullanılan SPDX-uyumlu lisans kısa kodları (PRD §20.1)
LICENSE_ODBL = "ODbL-1.0"
LICENSE_CC0 = "CC0-1.0"
LICENSE_CC_BY_4 = "CC-BY-4.0"
LICENSE_PUBLIC_DOMAIN = "PublicDomain"


@dataclass(slots=True)
class OpeningHourSlot:
    """Tek bir çalışma saati aralığı — Silver geçici temsil."""

    day_of_week: int  # 0 = Pazartesi, 6 = Pazar (PRD §10.2)
    opens_at: str | None = None  # "HH:MM" (24h) ya da None (kapalı)
    closes_at: str | None = None
    is_closed_special: bool = False
    season_start: str | None = None  # ISO "YYYY-MM-DD"
    season_end: str | None = None
    source: str = "osm"  # bizizmir/osm/llm/scrape (PRD §10.2)


@dataclass(slots=True)
class RawPlace:
    """
    Kaynak-bağımsız kanonik kayıt (PRD §8.4 ``raw_place``).

    Bu obje bir **mekan adayıdır** — henüz Gold ``places`` tablosuna yazılmış
    değildir. Dedup motoru bu objeleri ``geohash-7`` bloklarına dağıtıp
    pairwise skor hesaplar (PRD §8.5).
    """

    # --- Köken (kaynak) -----------------------------------------------------
    source: str  # 'osm' | 'wikidata' | 'bizizmir' | 'portal'
    source_id: str  # 'node/123', 'Q43332', 'bizizmir:res123:row7' ...
    source_url: str | None = None  # ham kayda referans (audit izi)
    license: str = LICENSE_PUBLIC_DOMAIN  # PRD §20 atıf politikası

    # --- Çok-dilli isim (PRD §8.4 + §10.1) ---------------------------------
    name_tr: str | None = None
    name_en: str | None = None
    name_de: str | None = None
    name_fr: str | None = None
    name_ar: str | None = None
    other_names: dict[str, str] = field(default_factory=dict)  # diğer ``lang -> label``

    # --- Konum (PRD §8.4 Geofence) -----------------------------------------
    lat: float | None = None
    lng: float | None = None

    # --- Kategoriler (PRD §8.5 category_score) -----------------------------
    # canonical_categories: ETL taksonomisi (etl.normalize.category_taxonomy).
    # raw_categories: kaynaktan gelen ham etiketler (örn. "tourism=museum").
    canonical_categories: list[str] = field(default_factory=list)
    raw_categories: list[str] = field(default_factory=list)

    # --- Algoritmik etiketler (PRD §10.1 ``etiketler``) --------------------
    tags: list[str] = field(default_factory=list)

    # --- Çalışma saatleri (PRD §10.2 + §8.4) -------------------------------
    opening_hours: list[OpeningHourSlot] = field(default_factory=list)

    # --- Açıklama (PRD §10.1) ----------------------------------------------
    description_tr: str | None = None
    description_en: str | None = None

    # --- Görsel ve dış kimlikler -------------------------------------------
    cover_photo_url: str | None = None
    wikidata_id: str | None = None  # 'Q43332'
    wikipedia_url_tr: str | None = None
    wikipedia_url_en: str | None = None
    osm_type: str | None = None  # 'node' | 'way' | 'relation'
    osm_id: int | None = None

    # --- Tarihsel + UNESCO (PRD §10.1) -------------------------------------
    tarihi_yapim_yili: int | None = None
    unesco: bool = False

    # --- Eksik veri sinyalleri (PRD §8.4 → ai_decision_queue) --------------
    has_required_fields: bool = True
    missing_field_reasons: list[str] = field(default_factory=list)

    # --- Audit / lineage ----------------------------------------------------
    extracted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    raw_payload: dict[str, Any] | None = None  # Bronze referansı için ham kayıt

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    def best_name(self) -> str | None:
        """Skorlama ve slug için tercih sırasıyla en uygun ismi döner."""
        return (
            self.name_tr
            or self.name_en
            or self.name_de
            or self.name_fr
            or self.name_ar
            or next(iter(self.other_names.values()), None)
        )

    def all_names(self) -> list[str]:
        """Token-set ratio karşılaştırması için tüm dil varyantları."""
        names = [
            self.name_tr,
            self.name_en,
            self.name_de,
            self.name_fr,
            self.name_ar,
            *self.other_names.values(),
        ]
        return [n for n in names if n]

    def attribution_block(self) -> dict[str, Any]:
        """PRD §20: ``places.kaynak_atif`` JSONB satırı için tek-kaynak özeti."""
        return {
            "src": self.source,
            "id": self.source_id,
            "url": self.source_url,
            "license": self.license,
        }

    def to_isim_jsonb(self) -> dict[str, str]:
        """``places.isim`` jsonb formatına çevir."""
        result: dict[str, str] = {}
        if self.name_tr:
            result["tr"] = self.name_tr
        if self.name_en:
            result["en"] = self.name_en
        if self.name_de:
            result["de"] = self.name_de
        if self.name_fr:
            result["fr"] = self.name_fr
        if self.name_ar:
            result["ar"] = self.name_ar
        for lang, label in self.other_names.items():
            result.setdefault(lang, label)
        return result

    def to_aciklama_jsonb(self) -> dict[str, str] | None:
        if not (self.description_tr or self.description_en):
            return None
        out: dict[str, str] = {}
        if self.description_tr:
            out["tr"] = self.description_tr
        if self.description_en:
            out["en"] = self.description_en
        return out


__all__ = [
    "LICENSE_CC0",
    "LICENSE_CC_BY_4",
    "LICENSE_ODBL",
    "LICENSE_PUBLIC_DOMAIN",
    "OpeningHourSlot",
    "RawPlace",
]
