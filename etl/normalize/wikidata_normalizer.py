"""
Wikidata Normalizer
===================
Wikidata SPARQL Results JSON (``head`` + ``results.bindings``) çıktısını
:class:`RawPlace` listesine eşler.

PRD §8.4 + §20.1: Wikidata içeriği CC0; yine de kaynak referansı tutulur.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from etl.config import IZMIR_BBOX, MIN_NAME_LENGTH, BoundingBox
from etl.normalize.category_taxonomy import wikidata_qids_to_canonical
from etl.normalize.schema import LICENSE_CC0, RawPlace
from etl.normalize.text_utils import normalize_text

logger = logging.getLogger(__name__)


# "Point(27.34 37.94)"
_WKT_POINT_RE = re.compile(r"Point\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)")


def _parse_point(wkt: str | None) -> tuple[float | None, float | None]:
    """WKT POINT(lng lat) → (lat, lng)."""
    if not wkt:
        return None, None
    m = _WKT_POINT_RE.search(wkt)
    if not m:
        return None, None
    try:
        lng = float(m.group(1))
        lat = float(m.group(2))
    except ValueError:
        return None, None
    return lat, lng


def _binding_value(binding: dict[str, Any], key: str) -> str | None:
    cell = binding.get(key)
    if not cell:
        return None
    val = cell.get("value")
    return normalize_text(val) if isinstance(val, str) else None


def _qid_from_uri(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1] if uri.startswith("http") else uri


def _parse_inception_year(raw: str | None) -> int | None:
    """SPARQL ``xsd:dateTime`` veya ``xsd:gYear`` → int yıl."""
    if not raw:
        return None
    sign = 1
    val = raw
    if val.startswith("-"):
        sign = -1
        val = val[1:]
    m = re.match(r"(\d{1,5})", val)
    if not m:
        return None
    try:
        return sign * int(m.group(1))
    except ValueError:
        return None


def _commons_url(image_value: str | None) -> str | None:
    """
    Wikidata P18 değeri ``"File:Foo.jpg"`` veya doğrudan URL.  Önyüzde
    kullanılabilir özel-resolver URL'i döner (CC0/CC-BY Wikimedia).
    """
    if not image_value:
        return None
    if image_value.startswith("http"):
        return image_value
    title = image_value.replace(" ", "_")
    return (
        "https://commons.wikimedia.org/wiki/Special:FilePath/"
        + title
    )


def normalize_wikidata(
    payload: dict[str, Any],
    *,
    bbox: BoundingBox = IZMIR_BBOX,
) -> list[RawPlace]:
    """
    Wikidata SPARQL JSON sonucunu :class:`RawPlace` listesine eşle.
    """
    bindings: Iterable[dict[str, Any]] = payload.get("results", {}).get("bindings") or []
    out: list[RawPlace] = []
    coord_dropped = 0
    geofence_dropped = 0

    for b in bindings:
        item_uri = _binding_value(b, "item")
        qid = _qid_from_uri(item_uri)
        if not qid:
            continue

        coord_wkt = _binding_value(b, "coord")
        lat, lng = _parse_point(coord_wkt)
        if lat is None or lng is None:
            coord_dropped += 1
            continue
        if not bbox.contains(lat, lng):
            geofence_dropped += 1
            continue

        name_tr = _binding_value(b, "nameTr")
        name_en = _binding_value(b, "nameEn") or _binding_value(b, "itemLabel")
        name_de = _binding_value(b, "nameDe")
        name_fr = _binding_value(b, "nameFr")
        name_ar = _binding_value(b, "nameAr")

        type_ids_raw = _binding_value(b, "typeIds")
        canonical_cats = wikidata_qids_to_canonical(type_ids_raw)

        heritage_qid = _qid_from_uri(_binding_value(b, "heritageStatus"))
        unesco = bool(heritage_qid) and heritage_qid in {"Q9259"}  # Q9259 = UNESCO WHS

        rp = RawPlace(
            source="wikidata",
            source_id=qid,
            source_url=f"https://www.wikidata.org/wiki/{qid}",
            license=LICENSE_CC0,
            name_tr=name_tr,
            name_en=name_en,
            name_de=name_de,
            name_fr=name_fr,
            name_ar=name_ar,
            lat=lat,
            lng=lng,
            canonical_categories=canonical_cats,
            raw_categories=[
                f"wikidata={q}" for q in (type_ids_raw or "").split("|") if q
            ],
            cover_photo_url=_commons_url(_binding_value(b, "image")),
            wikidata_id=qid,
            wikipedia_url_tr=_binding_value(b, "wikipediaTr"),
            wikipedia_url_en=_binding_value(b, "wikipediaEn"),
            tarihi_yapim_yili=_parse_inception_year(_binding_value(b, "inception")),
            unesco=unesco,
            raw_payload=b,
        )

        if not rp.best_name() or len(rp.best_name() or "") < MIN_NAME_LENGTH:
            rp.has_required_fields = False
            rp.missing_field_reasons.append("name")
        if not rp.canonical_categories:
            rp.missing_field_reasons.append("category")

        out.append(rp)

    logger.info(
        "Wikidata normalize: %d kayıt (coord_drop=%d, geofence_drop=%d)",
        len(out),
        coord_dropped,
        geofence_dropped,
    )
    return out


__all__ = ["normalize_wikidata"]
