"""
Overpass Normalizer
===================
Overpass API JSON çıktısını :class:`RawPlace` listesine eşler.

PRD §8.4 kuralları:
    * lat/lon zorunlu; yoksa **discard**.
    * name yoksa kayıt yine de oluşturulur ama ``has_required_fields=False``
      ve ``missing_field_reasons=["name"]`` ile işaretlenir → AI Queue (Adım 3).
    * Unicode NFC + Türkçe casefold (text_utils).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from etl.config import IZMIR_BBOX, MIN_NAME_LENGTH, BoundingBox
from etl.normalize.category_taxonomy import (
    osm_raw_categories,
    osm_tags_to_canonical,
)
from etl.normalize.schema import LICENSE_ODBL, OpeningHourSlot, RawPlace
from etl.normalize.text_utils import normalize_text

logger = logging.getLogger(__name__)


# OSM ``opening_hours`` etiketi karmaşık bir DSL kullanır.
# Bu Silver adımında basit "Mo-Fr 09:00-17:00; Sa 10:00-16:00" gibi formları
# parse ederiz; karmaşık olanlar ham metin olarak ``raw_payload`` içinde kalır.
_OSM_DOW_TR = {
    "Mo": 0, "Tu": 1, "We": 2, "Th": 3, "Fr": 4, "Sa": 5, "Su": 6,
    "PH": -1,  # public holiday → skip
}


def _osm_id(element: dict[str, Any]) -> str:
    """``node/123``, ``way/456``, ``relation/789`` formatında deterministik ID."""
    return f"{element.get('type')}/{element.get('id')}"


def _extract_coord(element: dict[str, Any]) -> tuple[float | None, float | None]:
    """node ise lat/lon, way/relation ise ``center.lat/lon``."""
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center")
    if isinstance(center, dict) and "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def _multilang_name(tags: dict[str, str]) -> dict[str, str | None]:
    """OSM ``name``, ``name:tr``, ``name:en``, ... etiketlerinden dil-bazlı isimler."""
    base = normalize_text(tags.get("name"))
    return {
        "tr": normalize_text(tags.get("name:tr")) or base,
        "en": normalize_text(tags.get("name:en")),
        "de": normalize_text(tags.get("name:de")),
        "fr": normalize_text(tags.get("name:fr")),
        "ar": normalize_text(tags.get("name:ar")),
        "base": base,
    }


def _parse_osm_opening_hours(raw: str | None) -> list[OpeningHourSlot]:
    """
    Çok basit bir OSM opening_hours parser'ı. Karmaşık form (Su[1], 24/7,
    PH off, ay aralıkları) ham olarak ``raw_payload`` içinde bırakılır;
    Silver'da yalnızca temel haftalık çizelge çıkarılır.
    """
    slots: list[OpeningHourSlot] = []
    if not raw:
        return slots
    raw = raw.strip()
    if not raw or raw.lower() == "off":
        return slots
    if raw == "24/7":
        for d in range(7):
            slots.append(
                OpeningHourSlot(
                    day_of_week=d, opens_at="00:00", closes_at="23:59", source="osm"
                )
            )
        return slots

    for segment in (s.strip() for s in raw.split(";") if s.strip()):
        # Beklenen kalıp: "Mo-Fr 09:00-17:00" veya "Sa 10:00-14:00"
        parts = segment.split(" ", 1)
        if len(parts) != 2:
            continue
        day_part, time_part = parts[0], parts[1]
        try:
            opens, closes = (t.strip() for t in time_part.split("-", 1))
        except ValueError:
            continue
        days = _expand_dow(day_part)
        for d in days:
            if d < 0:
                continue
            slots.append(
                OpeningHourSlot(
                    day_of_week=d,
                    opens_at=opens,
                    closes_at=closes,
                    source="osm",
                )
            )
    return slots


def _expand_dow(token: str) -> list[int]:
    if "-" in token:
        start_s, end_s = token.split("-", 1)
        start = _OSM_DOW_TR.get(start_s)
        end = _OSM_DOW_TR.get(end_s)
        if start is None or end is None or start < 0 or end < 0:
            return []
        if start <= end:
            return list(range(start, end + 1))
        return list(range(start, 7)) + list(range(0, end + 1))
    if "," in token:
        out: list[int] = []
        for t in token.split(","):
            t = t.strip()
            if t in _OSM_DOW_TR and _OSM_DOW_TR[t] >= 0:
                out.append(_OSM_DOW_TR[t])
        return out
    if token in _OSM_DOW_TR:
        v = _OSM_DOW_TR[token]
        return [v] if v >= 0 else []
    return []


def _parse_year(raw: str | None) -> int | None:
    """``"-200"`` → -200 (M.Ö. 200), ``"1450"`` → 1450, hatalıysa None."""
    if not raw:
        return None
    raw = raw.strip()
    sign = 1
    if raw.startswith("-"):
        sign = -1
        raw = raw[1:]
    # Bazı OSM start_date değerleri "1450 CE", "C12", "1450-04" gibi formlarda gelir.
    digits = ""
    for ch in raw:
        if ch.isdigit():
            digits += ch
        else:
            break
    if not digits:
        return None
    try:
        return sign * int(digits)
    except ValueError:
        return None


def normalize_overpass(
    payload: dict[str, Any],
    *,
    bbox: BoundingBox = IZMIR_BBOX,
) -> list[RawPlace]:
    """
    Overpass JSON cevabını :class:`RawPlace` listesine eşle.

    Parameters
    ----------
    payload : dict
        Overpass API yanıtı (``{"elements": [...]}``).
    bbox : BoundingBox
        Geofence kutusu — D1 gereği yalnızca İzmir bbox kayıtları geçer.
    """
    elements: Iterable[dict[str, Any]] = payload.get("elements") or []
    out: list[RawPlace] = []
    geofence_dropped = 0
    coord_dropped = 0

    for el in elements:
        lat, lng = _extract_coord(el)
        if lat is None or lng is None:
            coord_dropped += 1
            continue
        # D1 — Geofence (PRD §8.4)
        if not bbox.contains(lat, lng):
            geofence_dropped += 1
            continue

        tags = el.get("tags") or {}
        names = _multilang_name(tags)
        canonical_cats = osm_tags_to_canonical(tags)
        raw_cats = osm_raw_categories(tags)

        wd_qid = tags.get("wikidata")
        wikipedia_tr = tags.get("wikipedia:tr") or tags.get("wikipedia")
        if wikipedia_tr and ":" in wikipedia_tr and not wikipedia_tr.startswith("http"):
            # "tr:Efes" → "https://tr.wikipedia.org/wiki/Efes"
            lang, _, title = wikipedia_tr.partition(":")
            wikipedia_tr = f"https://{lang}.wikipedia.org/wiki/{title.replace(' ', '_')}"

        rp = RawPlace(
            source="osm",
            source_id=_osm_id(el),
            source_url=f"https://www.openstreetmap.org/{_osm_id(el)}",
            license=LICENSE_ODBL,
            name_tr=names["tr"],
            name_en=names["en"],
            name_de=names["de"],
            name_fr=names["fr"],
            name_ar=names["ar"],
            lat=lat,
            lng=lng,
            canonical_categories=canonical_cats,
            raw_categories=raw_cats,
            opening_hours=_parse_osm_opening_hours(tags.get("opening_hours")),
            wikidata_id=wd_qid if (wd_qid and wd_qid.startswith("Q")) else None,
            wikipedia_url_tr=wikipedia_tr,
            osm_type=el.get("type"),
            osm_id=el.get("id"),
            tarihi_yapim_yili=_parse_year(tags.get("start_date") or tags.get("year")),
            unesco=any(
                "unesco" in str(v).lower() for v in tags.values()
            ),
            raw_payload=el,
        )

        # PRD §8.4 — name_tr veya name_en eksikse missing_field bayrağı
        if not rp.best_name() or len(rp.best_name() or "") < MIN_NAME_LENGTH:
            rp.has_required_fields = False
            rp.missing_field_reasons.append("name")
        if not rp.canonical_categories:
            rp.missing_field_reasons.append("category")

        out.append(rp)

    logger.info(
        "Overpass normalize: %d kayıt (coord_drop=%d, geofence_drop=%d)",
        len(out),
        coord_dropped,
        geofence_dropped,
    )
    return out


__all__ = ["normalize_overpass"]
