"""
PRD §9.4 — Prompt Tasarımı
==========================
``ai_decision_queue`` satırının ``payload`` JSON'ı doğrudan PRD §9.4'teki
prompt formatına çevrilir. LLM'den SADECE belirtilen şemada **JSON** dönmesi
beklenir — başka açıklama, markdown veya kod bloğu yok.

PRD'deki örnek üzerinden hizalama:

    SYSTEM: Sen kültürel miras veri uzmanısın. İki aday kayıt veriliyor.
    Bunların aynı mekan olup olmadığına karar ver. SADECE JSON döndür.

    USER:
    {
      "candidate_A": { "source": "osm", "name": "Efes Antik Kenti", ... },
      "candidate_B": { "source": "wikidata", "name_tr": "Efes", ... }
    }

    OUTPUT_SCHEMA:
    {
      "decision": "merge | split | reject",
      "confidence": 0.0..1.0,
      "canonical": {
        "name_tr": "...",
        "name_en": "...",
        "lat": ..., "lng": ...,
        "primary_source_per_field": {...}
      },
      "reasoning": "Kısa Türkçe açıklama (max 200 karakter)"
    }

PRD §9.6 prompt-injection koruması:
    * Kaynak veriden gelen string'ler ``json.dumps`` ile escape edilir.
    * Maksimum uzunluk truncate uygulanır.
    * System message kaynak veriden bağımsız sabittir.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

# PRD §9.4 — System prompt birebir hizalı (Türkçe).
# Bu metin, kaynak veriden bağımsızdır → prompt-injection olamaz.
SYSTEM_PROMPT: str = (
    "Sen kültürel miras veri uzmanısın. İki aday kayıt veriliyor. "
    "Bunların aynı mekan olup olmadığına karar ver. SADECE JSON döndür. "
    "Açıklama, markdown, kod bloğu, ek metin EKLEME. "
    "JSON şeması aşağıdaki gibi olmalıdır:\n"
    "{\n"
    '  "decision": "merge | split | reject",\n'
    '  "confidence": 0.0..1.0,\n'
    '  "canonical": {\n'
    '    "name_tr": "...",\n'
    '    "name_en": "...",\n'
    '    "lat": ..., "lng": ...,\n'
    '    "primary_source_per_field": {"isim":"...","koordinat":"...","kategori":"...","aciklama":"..."}\n'
    "  },\n"
    '  "reasoning": "Kısa Türkçe açıklama (max 200 karakter)"\n'
    "}\n"
    "Kurallar:\n"
    "- 'decision' alanı yalnızca 'merge', 'split' veya 'reject' olabilir.\n"
    "- 'merge': iki aday aynı mekanın iki kaynaktaki temsilidir; tek "
    "kanonik kayıt üret.\n"
    "- 'split': iki aday FARKLI mekanlardır; ayrı yayınla.\n"
    "- 'reject': iki aday da geçersiz / eksik / hatalı; her ikisini ele.\n"
    "- 'canonical' alanı SADECE 'merge' kararında dolu olmalı; aksi halde null.\n"
    "- 'canonical.primary_source_per_field' her alan için hangi adayın "
    "kaynağından (örn. 'osm', 'wikidata', 'bizizmir') geldiğini belirtir.\n"
    "- 'confidence' kararın gerçekçi olasılığıdır (0.0-1.0, ondalık).\n"
    "- 'reasoning' maksimum 200 karakter, sadece Türkçe."
)

# PRD §9.6 — Prompt injection'a karşı uzunluk sınırı.
MAX_FIELD_LENGTH: int = 2000
MAX_OPENING_HOURS: int = 14


def _truncate(value: Any, *, limit: int = MAX_FIELD_LENGTH) -> Any:
    """String alanları PRD §9.6 gereği maksimum uzunluğa kes."""
    if isinstance(value, str) and len(value) > limit:
        return value[: limit - 3] + "..."
    return value


def _sanitize_candidate(raw: dict[str, Any] | None) -> dict[str, Any]:
    """
    Kuyruk payload'undaki aday dict'i PRD §9.4'teki kompakt formata indirger.

    Yalnızca LLM kararı için gerekli alanları bırakır; gereksiz / hassas
    metadata'yı (lisans hash'leri, ham JSONB vb.) prompt'a sokmaz.
    """
    if not raw:
        return {}

    keep_keys = (
        "source",
        "source_id",
        "name_tr",
        "name_en",
        "name_de",
        "name_fr",
        "name_ar",
        "lat",
        "lng",
        "canonical_categories",
        "raw_categories",
        "tags",
        "wikidata_id",
        "osm_type",
        "osm_id",
        "tarihi_yapim_yili",
        "unesco",
        "description_tr",
        "description_en",
    )
    sanitized: dict[str, Any] = {}
    for k in keep_keys:
        v = raw.get(k)
        if v is None or v == "" or v == [] or v == {}:
            continue
        sanitized[k] = _truncate(v)

    oh = raw.get("opening_hours") or []
    if oh:
        # En fazla 14 slot — istisnai olarak fazlası prompt'u şişirir.
        sanitized["opening_hours_count"] = len(oh)
        sanitized["opening_hours"] = [
            {
                "day_of_week": s.get("day_of_week"),
                "opens_at": s.get("opens_at"),
                "closes_at": s.get("closes_at"),
                "source": s.get("source"),
            }
            for s in oh[:MAX_OPENING_HOURS]
        ]

    return sanitized


def build_user_prompt(payload: dict[str, Any]) -> str:
    """
    ``ai_decision_queue.payload``'dan PRD §9.4 formatında USER prompt üret.

    Parameters
    ----------
    payload : dict
        :func:`etl.load.queue_writer._queue_payload`'dan gelen dict.
        Beklenen anahtarlar: ``candidate_a``, ``candidate_b``, ``scores``,
        ``blocking``.

    Returns
    -------
    str
        Tek bir JSON metni — LLM'e USER turn olarak verilecek.
    """
    user_block = {
        "candidate_A": _sanitize_candidate(payload.get("candidate_a")),
        "candidate_B": _sanitize_candidate(payload.get("candidate_b")),
        "dedup_signals": {
            "score_total": (payload.get("scores") or {}).get("total"),
            "geo_score": (payload.get("scores") or {}).get("geo"),
            "name_score": (payload.get("scores") or {}).get("name"),
            "category_score": (payload.get("scores") or {}).get("category"),
            "distance_m": (payload.get("scores") or {}).get("distance_m"),
            "geohash": (payload.get("blocking") or {}).get("geohash"),
        },
    }
    return json.dumps(user_block, ensure_ascii=False, separators=(",", ":"))


def hash_prompt(system_prompt: str, user_prompt: str) -> str:
    """
    Deterministik prompt hash (PRD §9.3 — idempotent cache anahtarı).

    Aynı (system, user) ikilisi için her zaman aynı hash üretilir. Bu sayede:
        * Aynı kayıt input hash'i aynı karar üretir.
        * ``ai_decision_log.prompt_hash`` üzerinden audit izlenebilir.
    """
    digest = hashlib.sha256()
    digest.update(system_prompt.encode("utf-8"))
    digest.update(b"\x1f")  # ASCII unit separator
    digest.update(user_prompt.encode("utf-8"))
    return digest.hexdigest()


__all__ = [
    "MAX_FIELD_LENGTH",
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "hash_prompt",
]
