"""
AI Kararını ``places`` Tablosuna Uygulama
=========================================
PRD §9.4 (OUTPUT_SCHEMA) + §10.1 (places şeması).

Karar türleri:
    * ``merge``  → Tek bir kanonik :class:`Place` insert et (LLM'in ``canonical``
      alanını kullan; eksik alanları kaynak adaylardan tamamla).
    * ``split``  → İki adayı ayrı ayrı :class:`Place` olarak insert et.
    * ``reject`` → Hiçbir yazım yapma (her iki adayı da ele).

PRD §9.6 güvenlik:
    * Output'taki ``canonical`` alanların kaynağı ``primary_source_per_field``
      ile her zaman bir adaya bağlı olmalıdır; aksi halde kararı **reject**'e
      düşür (LLM halüsinasyonu).
    * Confidence eşik kontrolü :mod:`etl.ai.processor`'da yapılır — burası
      sadece kararı uygulayan saf yazım katmanıdır.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from typing import Any

from geoalchemy2.elements import WKTElement
from slugify import slugify
from sqlalchemy.orm import Session

from app.core.enums import AIDecisionType
from app.models.place import Place

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Veri tipleri
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ParsedDecision:
    """LLM yanıtının ``OUTPUT_SCHEMA`` ile doğrulanmış hâli."""

    decision: AIDecisionType
    confidence: float
    canonical: dict[str, Any] | None
    primary_source_per_field: dict[str, str] | None
    reasoning: str | None


@dataclass(slots=True)
class ApplyResult:
    """Kararın uygulanma sonucu (insert edilen Place id'leri + lineage)."""

    written_place_ids: list[uuid.UUID]
    canonical_used: dict[str, Any] | None
    note: str


# ---------------------------------------------------------------------------
# LLM yanıtı doğrulama (PRD §9.4)
# ---------------------------------------------------------------------------
_ALLOWED_DECISIONS = {"merge", "split", "reject"}


def parse_decision(parsed: dict[str, Any]) -> ParsedDecision:
    """
    Gemini'den dönen JSON dict'i :class:`ParsedDecision`'a indirger ve PRD §9.4
    şemasına uygunluğunu doğrular.

    Raises
    ------
    ValueError
        Şema ihlali (eksik alan, geçersiz ``decision``, ``confidence``
        aralık dışı, ``canonical`` ``merge``'de eksik).
    """
    if not isinstance(parsed, dict):
        raise ValueError(f"LLM yanıtı dict değil: {type(parsed).__name__}")

    decision_raw = str(parsed.get("decision", "")).strip().lower()
    if decision_raw not in _ALLOWED_DECISIONS:
        raise ValueError(
            f"Geçersiz 'decision' değeri: {decision_raw!r}. "
            f"Beklenen: {sorted(_ALLOWED_DECISIONS)}"
        )

    try:
        confidence = float(parsed.get("confidence", 0))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"'confidence' float'a çevrilemedi: {exc}") from exc
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"'confidence' [0.0, 1.0] aralığında olmalı: {confidence}")

    canonical = parsed.get("canonical")
    if canonical is not None and not isinstance(canonical, dict):
        raise ValueError(f"'canonical' dict olmalı, alındı: {type(canonical).__name__}")

    if decision_raw == "merge" and not canonical:
        raise ValueError("'merge' kararı için 'canonical' alanı zorunludur")

    primary_source_per_field: dict[str, str] | None = None
    if canonical:
        psf = canonical.get("primary_source_per_field")
        if psf is not None:
            if not isinstance(psf, dict):
                raise ValueError(
                    "'canonical.primary_source_per_field' dict olmalı, alındı: "
                    f"{type(psf).__name__}"
                )
            primary_source_per_field = {
                str(k): str(v) for k, v in psf.items() if v is not None
            }

    reasoning = parsed.get("reasoning")
    reasoning_text = str(reasoning).strip() if reasoning else None
    if reasoning_text and len(reasoning_text) > 200:
        # PRD §9.4: max 200 karakter. Kes ve uyar.
        logger.warning(
            "LLM reasoning 200 karakter aştı (%d), kesiliyor",
            len(reasoning_text),
        )
        reasoning_text = reasoning_text[:200]

    return ParsedDecision(
        decision=AIDecisionType(decision_raw),
        confidence=confidence,
        canonical=canonical,
        primary_source_per_field=primary_source_per_field,
        reasoning=reasoning_text,
    )


# ---------------------------------------------------------------------------
# PRD §9.6: source-binding doğrulama
# ---------------------------------------------------------------------------
def _verify_source_binding(
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
    primary_source_per_field: dict[str, str] | None,
) -> bool:
    """
    PRD §9.6 — Output'taki tüm alanlar input adaylarının kaynaklarından birine
    bağlı olmalı. Aksi halde reject'e düşür (LLM halüsinasyonu).

    Not: ``primary_source_per_field`` opsiyonel; verilmemişse zayıf onay
    döner — caller karara göre işlem yapar (merge'de zorunlu).
    """
    if not primary_source_per_field:
        return False

    allowed_sources = {
        str(candidate_a.get("source") or "").lower(),
        str(candidate_b.get("source") or "").lower(),
    }
    allowed_sources.discard("")

    for field, src in primary_source_per_field.items():
        if str(src).lower() not in allowed_sources:
            logger.warning(
                "PRD §9.6 ihlali: '%s' alanı bilinmeyen kaynağa bağlı (%s ∉ %s)",
                field,
                src,
                sorted(allowed_sources),
            )
            return False
    return True


# ---------------------------------------------------------------------------
# Slug üretimi (gold_writer.py ile aynı kontrat — DRY için copy yerine
# minimal local kopya: queue runner'ın DB'ye yazımı bağımsız tutulur)
# ---------------------------------------------------------------------------
def _generate_unique_slug(
    db: Session,
    base_name: str,
    *,
    max_length: int = 160,
    max_tries: int = 25,
) -> str:
    """SEO-dostu slug üret; çakışırsa sayısal suffix ekle."""
    slug_base = slugify(base_name or "", max_length=max_length - 6, lowercase=True)
    if not slug_base:
        slug_base = f"yer-{uuid.uuid4().hex[:8]}"

    candidate = slug_base
    for i in range(1, max_tries + 1):
        exists = db.query(Place.id).filter(Place.slug == candidate).limit(1).one_or_none()
        if exists is None:
            return candidate
        candidate = f"{slug_base}-{i + 1}"
    return f"{slug_base}-{uuid.uuid4().hex[:6]}"


# ---------------------------------------------------------------------------
# Place builder yardımcıları
# ---------------------------------------------------------------------------
def _coalesce(*values: Any) -> Any:
    """İlk None olmayan + "anlamlı" değeri döner."""
    for v in values:
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        if isinstance(v, (list, tuple, set, dict)) and not v:
            continue
        return v
    return None


_COORD_RE = re.compile(r"^-?\d+(\.\d+)?$")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and _COORD_RE.match(value.strip()):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _build_isim_jsonb(
    candidate: dict[str, Any],
    canonical: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Çok-dilli isim JSONB — LLM canonical öncelikli, eksikleri adaydan tamamla."""
    out: dict[str, str] = {}
    for lang_key in ("name_tr", "name_en", "name_de", "name_fr", "name_ar"):
        lang = lang_key.split("_")[1]  # tr/en/de/fr/ar
        val = None
        if canonical:
            val = canonical.get(lang_key) or canonical.get(lang)
        if not val:
            val = candidate.get(lang_key)
        if val:
            out[lang] = str(val).strip()
    return out


def _build_aciklama_jsonb(candidate: dict[str, Any]) -> dict[str, str] | None:
    tr = candidate.get("description_tr")
    en = candidate.get("description_en")
    if not (tr or en):
        return None
    out: dict[str, str] = {}
    if tr:
        out["tr"] = str(tr)
    if en:
        out["en"] = str(en)
    return out


def _build_kaynak_atif(
    candidates: list[dict[str, Any]],
    *,
    queue_id: uuid.UUID,
    license_map: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """PRD §10.1 ``kaynak_atif`` — her aday için bir satır."""
    license_map = license_map or {
        "osm": "ODbL-1.0",
        "wikidata": "CC0-1.0",
        "bizizmir": "CC-BY-4.0",
        "portal": "PublicDomain",
    }
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for c in candidates:
        src = str(c.get("source") or "").lower()
        sid = str(c.get("source_id") or "")
        if not src or not sid:
            continue
        key = (src, sid)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "src": src,
                "id": sid,
                "license": license_map.get(src, "PublicDomain"),
                "via": "ai_decision_queue",
                "queue_id": str(queue_id),
            }
        )
    return out


def _place_from_candidate(
    db: Session,
    candidate: dict[str, Any],
    *,
    queue_id: uuid.UUID,
    canonical: dict[str, Any] | None = None,
    confidence: float = 0.0,
) -> Place | None:
    """
    Tek bir candidate (+opsiyonel LLM canonical override) için yeni
    :class:`Place` örneği oluştur. Koordinat yoksa ``None`` döner.
    """
    # Koordinat — LLM canonical öncelikli, sonra candidate.
    lat = None
    lng = None
    if canonical:
        lat = _as_float(canonical.get("lat"))
        lng = _as_float(canonical.get("lng"))
    if lat is None or lng is None:
        lat = _as_float(candidate.get("lat"))
        lng = _as_float(candidate.get("lng"))
    if lat is None or lng is None:
        logger.warning(
            "candidate koordinatsız → Place yazılamıyor (queue_id=%s, source=%s id=%s)",
            queue_id,
            candidate.get("source"),
            candidate.get("source_id"),
        )
        return None

    isim = _build_isim_jsonb(candidate, canonical)
    if not isim:
        logger.warning(
            "candidate isimsiz → Place yazılamıyor (queue_id=%s, source=%s id=%s)",
            queue_id,
            candidate.get("source"),
            candidate.get("source_id"),
        )
        return None

    base_name = isim.get("tr") or isim.get("en") or next(iter(isim.values()), "")
    slug = _generate_unique_slug(db, base_name)

    kategori = list(
        _coalesce(
            candidate.get("canonical_categories"),
            candidate.get("raw_categories"),
            [],
        )
        or []
    )
    etiketler = list(candidate.get("tags") or [])

    ziyaret_bilgisi: dict[str, Any] = {
        # D2: Müzekart resmi API yok; statik bayrak.
        "muzekart_gecerli": False,
        "giris_ucretleri": None,
    }
    oh = candidate.get("opening_hours") or []
    if oh:
        ziyaret_bilgisi["acilis_kapanis"] = oh

    place = Place(
        id=uuid.uuid4(),
        slug=slug,
        isim=isim,
        kategori=kategori,
        koordinat=WKTElement(f"POINT({lng} {lat})", srid=4326, extended=False),
        bbox=None,
        ziyaret_bilgisi=ziyaret_bilgisi,
        etiketler=etiketler,
        tarihi_yapim_yili=candidate.get("tarihi_yapim_yili"),
        unesco=bool(candidate.get("unesco") or False),
        kapak_foto_url=candidate.get("cover_photo_url"),
        aciklama=_build_aciklama_jsonb(candidate),
        aciklama_source=("llm-gemini-flash" if canonical else None),
        kaynak_atif=_build_kaynak_atif([candidate], queue_id=queue_id),
        # PRD §9.4 confidence → kalite skoru olarak yazılır (audit + UI için).
        kalite_skoru=round(min(max(confidence, 0.0), 1.0), 2),
        merged_from=None,
        is_published=True,
    )
    return place


def _place_from_merge(
    db: Session,
    candidate_a: dict[str, Any],
    candidate_b: dict[str, Any],
    canonical: dict[str, Any],
    *,
    queue_id: uuid.UUID,
    confidence: float,
) -> Place | None:
    """
    LLM canonical + iki aday → tek bir :class:`Place` (merge).

    Eksik alanlar A → B sırasıyla fallback ile doldurulur.
    """
    merged_candidate: dict[str, Any] = {
        # Source / source_id'leri ATIF için A'dan al; B kayıt atfı kaynak_atif
        # bloğunda ayrıca tutulur.
        "source": candidate_a.get("source"),
        "source_id": candidate_a.get("source_id"),
        # İsim alanları — LLM canonical öncelikli, sonra A→B.
        "name_tr": _coalesce(
            (canonical or {}).get("name_tr"),
            candidate_a.get("name_tr"),
            candidate_b.get("name_tr"),
        ),
        "name_en": _coalesce(
            (canonical or {}).get("name_en"),
            candidate_a.get("name_en"),
            candidate_b.get("name_en"),
        ),
        "name_de": _coalesce(candidate_a.get("name_de"), candidate_b.get("name_de")),
        "name_fr": _coalesce(candidate_a.get("name_fr"), candidate_b.get("name_fr")),
        "name_ar": _coalesce(candidate_a.get("name_ar"), candidate_b.get("name_ar")),
        # Koordinat — LLM canonical öncelikli.
        "lat": _coalesce(
            (canonical or {}).get("lat"),
            candidate_a.get("lat"),
            candidate_b.get("lat"),
        ),
        "lng": _coalesce(
            (canonical or {}).get("lng"),
            candidate_a.get("lng"),
            candidate_b.get("lng"),
        ),
        # Listeler — birleşim.
        "canonical_categories": _union_list(
            candidate_a.get("canonical_categories"),
            candidate_b.get("canonical_categories"),
        ),
        "raw_categories": _union_list(
            candidate_a.get("raw_categories"),
            candidate_b.get("raw_categories"),
        ),
        "tags": _union_list(candidate_a.get("tags"), candidate_b.get("tags")),
        # Diğer skaler alanlar — A→B fallback.
        "tarihi_yapim_yili": _coalesce(
            candidate_a.get("tarihi_yapim_yili"),
            candidate_b.get("tarihi_yapim_yili"),
        ),
        "unesco": bool(candidate_a.get("unesco") or candidate_b.get("unesco")),
        "cover_photo_url": _coalesce(
            candidate_a.get("cover_photo_url"),
            candidate_b.get("cover_photo_url"),
        ),
        "description_tr": _coalesce(
            candidate_a.get("description_tr"),
            candidate_b.get("description_tr"),
        ),
        "description_en": _coalesce(
            candidate_a.get("description_en"),
            candidate_b.get("description_en"),
        ),
        # Çalışma saatleri — birleşim (gün başına ilk gelen kalır).
        "opening_hours": _dedupe_opening_hours(
            (candidate_a.get("opening_hours") or [])
            + (candidate_b.get("opening_hours") or [])
        ),
    }

    place = _place_from_candidate(
        db,
        merged_candidate,
        queue_id=queue_id,
        canonical=canonical,
        confidence=confidence,
    )
    if place is None:
        return None

    # Atıf bloğunu hem A hem B kaynaklarıyla yeniden üret.
    place.kaynak_atif = _build_kaynak_atif(
        [candidate_a, candidate_b], queue_id=queue_id
    )
    place.aciklama_source = "llm-gemini-flash"
    return place


def _union_list(*lists: Any) -> list[Any]:
    """Sıralı union — eklenme sırasını koru, tekrarları at."""
    out: list[Any] = []
    seen: set[Any] = set()
    for lst in lists:
        if not lst:
            continue
        for item in lst:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
    return out


def _dedupe_opening_hours(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aynı gün için ilk gelen slot kalır (kaynak önceliği A → B)."""
    seen_days: set[int] = set()
    out: list[dict[str, Any]] = []
    for slot in slots:
        dow = slot.get("day_of_week")
        if dow is None or dow in seen_days:
            continue
        seen_days.add(dow)
        out.append(slot)
    return out


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def apply_decision(
    db: Session,
    *,
    queue_id: uuid.UUID,
    queue_payload: dict[str, Any],
    decision: ParsedDecision,
) -> ApplyResult:
    """
    PRD §9.4 OUTPUT_SCHEMA'sındaki kararı ``places`` tablosuna uygula.

    Bu fonksiyon ``db.commit()`` çağırmaz — caller (processor) idempotent
    transaction kontrolünü yapar.

    Returns
    -------
    ApplyResult
        Insert edilen Place id'leri + kullanılan canonical dict (audit için).
    """
    candidate_a = queue_payload.get("candidate_a") or {}
    candidate_b = queue_payload.get("candidate_b") or {}

    written_ids: list[uuid.UUID] = []

    if decision.decision == AIDecisionType.REJECT:
        return ApplyResult(
            written_place_ids=[],
            canonical_used=None,
            note="reject: hiçbir aday Gold'a yazılmadı",
        )

    if decision.decision == AIDecisionType.SPLIT:
        # PRD §9.4: 'split' → iki aday ayrı kayıtlardır.
        for cand in (candidate_a, candidate_b):
            place = _place_from_candidate(
                db,
                cand,
                queue_id=queue_id,
                canonical=None,  # split → LLM canonical kullanılmaz
                confidence=decision.confidence,
            )
            if place is None:
                continue
            db.add(place)
            db.flush()
            written_ids.append(place.id)
        return ApplyResult(
            written_place_ids=written_ids,
            canonical_used=None,
            note=f"split: {len(written_ids)} place insert",
        )

    # --- MERGE ---------------------------------------------------------------
    if decision.decision != AIDecisionType.MERGE:  # pragma: no cover (defansif)
        raise ValueError(f"Bilinmeyen karar tipi: {decision.decision}")

    canonical = decision.canonical or {}

    # PRD §9.6: source-binding doğrulama. Geçersizse merge'i iptal et.
    if not _verify_source_binding(
        candidate_a, candidate_b, decision.primary_source_per_field
    ):
        logger.warning(
            "Merge iptal edildi (PRD §9.6 source-binding ihlali) queue_id=%s",
            queue_id,
        )
        return ApplyResult(
            written_place_ids=[],
            canonical_used=canonical,
            note=(
                "merge_aborted: primary_source_per_field doğrulanmadı "
                "(PRD §9.6 halüsinasyon koruması)"
            ),
        )

    place = _place_from_merge(
        db,
        candidate_a,
        candidate_b,
        canonical,
        queue_id=queue_id,
        confidence=decision.confidence,
    )
    if place is None:
        return ApplyResult(
            written_place_ids=[],
            canonical_used=canonical,
            note="merge_aborted: zorunlu alanlar (isim/koordinat) eksik",
        )

    db.add(place)
    db.flush()
    written_ids.append(place.id)
    return ApplyResult(
        written_place_ids=written_ids,
        canonical_used=canonical,
        note=f"merge: 1 place insert (confidence={decision.confidence:.2f})",
    )


__all__ = [
    "ApplyResult",
    "ParsedDecision",
    "apply_decision",
    "parse_decision",
]
