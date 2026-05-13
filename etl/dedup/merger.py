"""
Source-Priority Merge
=====================
PRD §8.5 #4: "Merge Stratejisi — Her alan için *source-priority* (örn. tescil
için Kültür Portalı, koordinat için OSM, isim için Wikidata)."

:func:`merge_cluster` bir grup :class:`RawPlace` adayını tek bir kanonik
:class:`RawPlace`'a indirger; ayrıca alan-bazlı kaynak özetini
``primary_source_per_field`` JSONB satırına çevrilecek şekilde döner
(``merge_decision_log`` lineage'ı için).
"""

from __future__ import annotations

from typing import Any

from etl.config import SOURCE_PRIORITY
from etl.normalize.schema import RawPlace


def _is_meaningful(value: Any) -> bool:
    """
    Bir alanın "anlamlı dolu" sayılıp sayılmayacağını belirler.

    ``None``, boş string, boş koleksiyon → anlamsız.
    ``False`` ve ``0`` → anlamlı (örn. ``tarihi_yapim_yili=0`` veya
    ``unesco=False`` gibi explicit değerler).
    """
    if value is None:
        return False
    if isinstance(value, str):
        return value != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def _pick_value(
    records_by_source: dict[str, list[RawPlace]],
    sources_in_priority_order: tuple[str, ...],
    attr: str,
) -> tuple[Any, str | None]:
    """
    Verilen attribute için, priority sırasıyla ilk anlamlı değeri döner.

    Returns ``(value, source_used)`` — bulunamazsa ``(None, None)``.
    """
    for src in sources_in_priority_order:
        for rec in records_by_source.get(src, []):
            val = getattr(rec, attr, None)
            if _is_meaningful(val):
                return val, src
    return None, None


def _pick_list_union(
    records_by_source: dict[str, list[RawPlace]],
    sources_in_priority_order: tuple[str, ...],
    attr: str,
) -> tuple[list[Any], dict[str, list[str]]]:
    """
    Liste alanlar için tüm kaynaklardaki değerleri birleştir; lineage için
    "hangi kaynak hangi değeri kattı" sözlüğü döner.
    """
    union: list[Any] = []
    seen: set[Any] = set()
    contribution: dict[str, list[str]] = {}
    for src in sources_in_priority_order:
        for rec in records_by_source.get(src, []):
            for val in (getattr(rec, attr, None) or []):
                if val in seen:
                    continue
                seen.add(val)
                union.append(val)
                contribution.setdefault(src, []).append(str(val))
    return union, contribution


def merge_cluster(records: list[RawPlace]) -> tuple[RawPlace, dict[str, str | None]]:
    """
    Bir cluster'ı tek canonical :class:`RawPlace`'a indir.

    Returns
    -------
    canonical : RawPlace
        Birleştirilmiş kanonik kayıt.
    primary_source_per_field : dict
        Her alanın hangi kaynaktan geldiği (``merge_decision_log`` için).
    """
    if not records:
        raise ValueError("merge_cluster: boş kayıt listesi")

    if len(records) == 1:
        rec = records[0]
        return rec, {
            "koordinat": rec.source,
            "isim": rec.source,
            "kategori": rec.source,
            "aciklama": rec.source if (rec.description_tr or rec.description_en) else None,
            "kapak_foto_url": rec.source if rec.cover_photo_url else None,
            "opening_hours": rec.source if rec.opening_hours else None,
            "tarihi_yapim_yili": rec.source if rec.tarihi_yapim_yili else None,
        }

    # Kaynak bazlı bucket
    by_source: dict[str, list[RawPlace]] = {}
    for r in records:
        by_source.setdefault(r.source, []).append(r)

    # --- Koordinat (tek skaler) -------------------------------------------
    lat_pri = SOURCE_PRIORITY["koordinat"]
    lat_val, lat_src = _pick_value(by_source, lat_pri, "lat")
    lng_val, lng_src = _pick_value(by_source, lat_pri, "lng")
    if lat_val is None or lng_val is None:
        # Fallback: ilk record'un koordinatları (cluster oluştuysa zaten dolu)
        ref = next(r for r in records if r.lat is not None and r.lng is not None)
        lat_val, lng_val = ref.lat, ref.lng
        lat_src = lat_src or ref.source

    # --- İsim alanları ----------------------------------------------------
    isim_pri = SOURCE_PRIORITY["isim"]
    name_tr, src_name = _pick_value(by_source, isim_pri, "name_tr")
    name_en, _ = _pick_value(by_source, isim_pri, "name_en")
    name_de, _ = _pick_value(by_source, isim_pri, "name_de")
    name_fr, _ = _pick_value(by_source, isim_pri, "name_fr")
    name_ar, _ = _pick_value(by_source, isim_pri, "name_ar")
    other_names: dict[str, str] = {}
    for r in records:
        for k, v in (r.other_names or {}).items():
            other_names.setdefault(k, v)

    # --- Kategori (union) -------------------------------------------------
    cat_pri = SOURCE_PRIORITY["kategori"]
    canonical_cats, _ = _pick_list_union(by_source, cat_pri, "canonical_categories")
    raw_cats, _ = _pick_list_union(by_source, cat_pri, "raw_categories")
    tags, _ = _pick_list_union(by_source, cat_pri, "tags")

    # --- Açıklama ---------------------------------------------------------
    desc_pri = SOURCE_PRIORITY["aciklama"]
    desc_tr, src_desc = _pick_value(by_source, desc_pri, "description_tr")
    desc_en, _ = _pick_value(by_source, desc_pri, "description_en")

    # --- Görsel -----------------------------------------------------------
    img_pri = SOURCE_PRIORITY["kapak_foto_url"]
    cover, src_cover = _pick_value(by_source, img_pri, "cover_photo_url")

    # --- Çalışma saatleri (union — Bizizmir öncelikli) --------------------
    oh_pri = SOURCE_PRIORITY["opening_hours"]
    opening_hours: list[Any] = []
    src_oh: str | None = None
    for src in oh_pri:
        for rec in by_source.get(src, []):
            if rec.opening_hours:
                opening_hours.extend(rec.opening_hours)
                src_oh = src_oh or src
    # Aynı gün için tekrarları tek seferde tut (en yüksek-öncelikli kaynak öncelikli).
    seen_days: set[int] = set()
    deduped_oh = []
    for slot in opening_hours:
        if slot.day_of_week in seen_days:
            continue
        seen_days.add(slot.day_of_week)
        deduped_oh.append(slot)

    # --- Tescil / UNESCO / yıl --------------------------------------------
    tescil_pri = SOURCE_PRIORITY["tescil"]
    unesco_val, src_unesco = _pick_value(by_source, tescil_pri, "unesco")

    year_pri = SOURCE_PRIORITY["tarihi_yapim_yili"]
    year_val, src_year = _pick_value(by_source, year_pri, "tarihi_yapim_yili")

    # --- Dış kimlikler ----------------------------------------------------
    wikidata_id = next(
        (r.wikidata_id for r in records if r.wikidata_id), None
    )
    wikipedia_tr = next(
        (r.wikipedia_url_tr for r in records if r.wikipedia_url_tr), None
    )
    wikipedia_en = next(
        (r.wikipedia_url_en for r in records if r.wikipedia_url_en), None
    )
    osm_record = next((r for r in records if r.source == "osm"), None)

    primary_record = records[0]

    canonical = RawPlace(
        source=primary_record.source,
        source_id=primary_record.source_id,
        source_url=primary_record.source_url,
        license=primary_record.license,
        name_tr=name_tr,
        name_en=name_en,
        name_de=name_de,
        name_fr=name_fr,
        name_ar=name_ar,
        other_names=other_names,
        lat=float(lat_val) if lat_val is not None else None,
        lng=float(lng_val) if lng_val is not None else None,
        canonical_categories=canonical_cats,
        raw_categories=raw_cats,
        tags=tags,
        opening_hours=deduped_oh,
        description_tr=desc_tr,
        description_en=desc_en,
        cover_photo_url=cover,
        wikidata_id=wikidata_id,
        wikipedia_url_tr=wikipedia_tr,
        wikipedia_url_en=wikipedia_en,
        osm_type=osm_record.osm_type if osm_record else None,
        osm_id=osm_record.osm_id if osm_record else None,
        tarihi_yapim_yili=int(year_val) if year_val is not None else None,
        unesco=bool(unesco_val) if unesco_val is not None else False,
        has_required_fields=True,
        missing_field_reasons=[],
        raw_payload={"merged_from": [r.source_id for r in records]},
    )

    primary_source_per_field: dict[str, str | None] = {
        "koordinat": lat_src,
        "isim": src_name,
        "kategori": cat_pri[0] if canonical_cats else None,
        "aciklama": src_desc,
        "kapak_foto_url": src_cover,
        "opening_hours": src_oh,
        "tarihi_yapim_yili": src_year,
        "unesco": src_unesco,
    }
    return canonical, primary_source_per_field


__all__ = ["merge_cluster"]
