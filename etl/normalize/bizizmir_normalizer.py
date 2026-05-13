"""
Bizizmir Açık Veri Normalizer
=============================
Bizizmir CKAN ``datastore_search`` satırlarını :class:`RawPlace` listesine
eşler. PRD §8.1 #3: Bizizmir verisinin **birincil sözleşmesi** İzmir müzeleri
için **çalışma saatleri/günleri** sağlamaktır; ek olarak isim + (varsa)
koordinat da Silver kaydına işlenir.

Dataset şemaları portala göre değişebileceği için bu normalizer **defansif**
çalışır — bilinen kolon alias'larını dener, bulamadığı alanları boş bırakır.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Iterable

from etl.config import IZMIR_BBOX, MIN_NAME_LENGTH, BoundingBox
from etl.normalize.schema import LICENSE_CC_BY_4, OpeningHourSlot, RawPlace
from etl.normalize.text_utils import normalize_text, tr_casefold

logger = logging.getLogger(__name__)


# Bilinen / muhtemel kolon adları (Bizizmir + benzer CKAN şemaları).
_NAME_KEYS = ("ad", "adi", "isim", "ad_tr", "ad_t", "mekan_adi", "name")
_LAT_KEYS = ("enlem", "latitude", "lat", "y", "y_coord")
_LNG_KEYS = ("boylam", "longitude", "lon", "lng", "x", "x_coord")
_OPEN_HOURS_KEYS = ("calisma_saatleri", "acilis_kapanis", "saatler", "opening_hours")
_CATEGORY_KEYS = ("kategori", "tur", "tip", "category")
_ADDRESS_KEYS = ("adres", "address", "konum")
_LICENSE_DEFAULT = LICENSE_CC_BY_4


_TR_DAY_TO_INT = {
    "pazartesi": 0,
    "salı": 1, "sali": 1,
    "çarşamba": 2, "carsamba": 2,
    "perşembe": 3, "persembe": 3,
    "cuma": 4,
    "cumartesi": 5,
    "pazar": 6,
}

_TIME_RANGE_RE = re.compile(
    r"(\d{1,2}[:.]\d{2})\s*[-–—]\s*(\d{1,2}[:.]\d{2})"
)


def _first_key(row: dict[str, Any], candidates: tuple[str, ...]) -> Any:
    """Bir satırda tanınan ilk kolon değerini döndür."""
    lower = {tr_casefold(str(k)): k for k in row.keys()}
    for c in candidates:
        if c in lower:
            return row[lower[c]]
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.replace(",", ".").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _parse_opening_hours_text(raw: str | None) -> list[OpeningHourSlot]:
    """
    Türkçe metin çalışma saatlerinden temel ``OpeningHourSlot`` üret.

    Desteklenen örnekler:
        * ``"Pazartesi-Pazar 09:00-17:00"``
        * ``"Hafta içi 09:00-17:00, Hafta sonu kapalı"``
        * ``"Salı kapalı, diğer günler 10:00-18:00"``
    """
    slots: list[OpeningHourSlot] = []
    if not raw:
        return slots
    text = tr_casefold(normalize_text(raw) or "")
    if not text:
        return slots

    # 1) Tüm haftaya uygulanabilen genel aralık.
    universal_match = _TIME_RANGE_RE.search(text)
    universal_opens, universal_closes = (None, None)
    if universal_match and ("her gün" in text or "pazartesi-pazar" in text):
        universal_opens = universal_match.group(1).replace(".", ":")
        universal_closes = universal_match.group(2).replace(".", ":")
        for d in range(7):
            slots.append(
                OpeningHourSlot(
                    day_of_week=d,
                    opens_at=universal_opens,
                    closes_at=universal_closes,
                    source="bizizmir",
                )
            )
        return slots

    # 2) Hafta içi / hafta sonu özel ifadeleri.
    if "hafta içi" in text or "hafta ici" in text:
        m = _TIME_RANGE_RE.search(text)
        if m:
            for d in range(5):  # Pzt–Cuma
                slots.append(
                    OpeningHourSlot(
                        day_of_week=d,
                        opens_at=m.group(1).replace(".", ":"),
                        closes_at=m.group(2).replace(".", ":"),
                        source="bizizmir",
                    )
                )

    # 3) Bireysel gün eşleşmeleri ("salı 10:00-18:00", "pazar kapalı")
    for token, dow in _TR_DAY_TO_INT.items():
        if token in text:
            window = re.search(
                rf"{token}\s*[^a-zçğıöşü0-9]{{0,3}}([^,;]*)", text
            )
            if not window:
                continue
            chunk = window.group(1)
            if "kapalı" in chunk or "kapali" in chunk:
                slots.append(
                    OpeningHourSlot(
                        day_of_week=dow,
                        is_closed_special=True,
                        source="bizizmir",
                    )
                )
                continue
            m = _TIME_RANGE_RE.search(chunk)
            if m:
                slots.append(
                    OpeningHourSlot(
                        day_of_week=dow,
                        opens_at=m.group(1).replace(".", ":"),
                        closes_at=m.group(2).replace(".", ":"),
                        source="bizizmir",
                    )
                )

    return slots


def _normalize_row(
    row: dict[str, Any],
    *,
    dataset_name: str,
    resource_id: str | None,
    license_id: str | None,
    bbox: BoundingBox,
) -> RawPlace | None:
    name = normalize_text(str(_first_key(row, _NAME_KEYS) or ""))
    if not name or len(name) < MIN_NAME_LENGTH:
        return None

    lat = _coerce_float(_first_key(row, _LAT_KEYS))
    lng = _coerce_float(_first_key(row, _LNG_KEYS))

    # Bizizmir bazı satırlarda koordinat içermez (sadece çalışma saati).
    # PRD §8.4: lat/lng yoksa discard.  Adres+ad ile dedup yapılamaz.
    if lat is None or lng is None:
        return None
    if not bbox.contains(lat, lng):
        return None

    category_raw = normalize_text(str(_first_key(row, _CATEGORY_KEYS) or "") or "")
    canonical_cats: list[str] = []
    if category_raw:
        cf = tr_casefold(category_raw)
        if "müze" in cf or "muze" in cf:
            canonical_cats.append("museum")
        elif "ören" in cf or "oren" in cf or "antik" in cf:
            canonical_cats.append("archaeological_site")
        elif "cami" in cf:
            canonical_cats.append("mosque")
        elif "kilise" in cf:
            canonical_cats.append("church")
        elif "kale" in cf:
            canonical_cats.append("castle")

    row_id = (
        row.get("_id")
        or row.get("id")
        or hash(frozenset(row.items()))  # son çare deterministik fingerprint
    )
    source_id = f"bizizmir:{resource_id or dataset_name}:{row_id}"

    rp = RawPlace(
        source="bizizmir",
        source_id=source_id,
        source_url=None,
        license=license_id or _LICENSE_DEFAULT,
        name_tr=name,
        lat=lat,
        lng=lng,
        canonical_categories=canonical_cats,
        raw_categories=[f"bizizmir={category_raw}"] if category_raw else [],
        opening_hours=_parse_opening_hours_text(
            normalize_text(str(_first_key(row, _OPEN_HOURS_KEYS) or "") or "")
        ),
        raw_payload={"dataset": dataset_name, "resource_id": resource_id, "row": row},
    )

    if not rp.best_name():
        rp.has_required_fields = False
        rp.missing_field_reasons.append("name")
    if not rp.canonical_categories:
        rp.missing_field_reasons.append("category")

    return rp


def normalize_bizizmir(
    payload: dict[str, Any],
    *,
    bbox: BoundingBox = IZMIR_BBOX,
) -> list[RawPlace]:
    """
    Bizizmir CKAN payload'ını (``{"datasets": [...]}``) :class:`RawPlace`
    listesine eşle. Geofence ve eksik koordinat kuralları PRD §8.4 ile aynı.
    """
    datasets: Iterable[dict[str, Any]] = payload.get("datasets") or []
    out: list[RawPlace] = []
    for ds in datasets:
        ds_name = ds.get("name", "?")
        license_id = ds.get("license_id")
        for resource in ds.get("resources") or []:
            res_id = resource.get("id")
            for row in resource.get("records") or []:
                rp = _normalize_row(
                    row,
                    dataset_name=ds_name,
                    resource_id=res_id,
                    license_id=license_id,
                    bbox=bbox,
                )
                if rp is not None:
                    out.append(rp)

    logger.info("Bizizmir normalize: %d kayıt", len(out))
    return out


__all__ = ["normalize_bizizmir"]
