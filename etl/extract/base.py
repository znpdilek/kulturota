"""
Extract — Ortak Yardımcılar
===========================
PRD §8.3 Bronze sözleşmesi:
    * Hiçbir dönüşüm yok, sadece snapshot.
    * Atıf bloğu, API sürümü, sorgu hash'i metadata olarak yazılır.
    * Idempotency için ``idempotency_key`` ``etl_run_log`` tablosuna eşlenir.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from etl.config import BRONZE_DIR, HTTP_TIMEOUT_S, USER_AGENT

logger = logging.getLogger(__name__)


class ExtractError(RuntimeError):
    """Extract aşamasında HTTP/parse hataları için."""


@dataclass(slots=True)
class BronzeArtifact:
    """Yazılan bir Bronze snapshot'ının lokasyonu ve metadata özeti."""

    source: str
    path: Path
    record_count: int
    idempotency_key: str
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------
def http_client(*, timeout: float = HTTP_TIMEOUT_S, **kwargs: Any) -> httpx.Client:
    """KültürRota User-Agent + sane defaults ile httpx Client."""
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip, deflate"}
    headers.update(kwargs.pop("headers", {}) or {})
    return httpx.Client(
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Bronze yazımı
# ---------------------------------------------------------------------------
def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _partition_for(source: str, when: datetime | None = None) -> Path:
    when = when or _utc_now()
    return (
        BRONZE_DIR
        / f"source={source}"
        / f"yyyy={when:%Y}"
        / f"mm={when:%m}"
        / f"dd={when:%d}"
    )


def idempotency_key(source: str, params: dict[str, Any]) -> str:
    """
    PRD §8.3: Tüm fetch işlemleri ``etl_run_log`` tablosuna ``idempotency_key``
    ile yazılır.  Aynı kaynak + parametre seti aynı key'i üretir → re-run güvenli.
    """
    canon = json.dumps(params, sort_keys=True, default=str, ensure_ascii=False)
    digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:24]
    return f"{source}:{digest}"


def write_bronze_snapshot(
    source: str,
    payload: Any,
    *,
    metadata: dict[str, Any] | None = None,
    record_count: int | None = None,
    when: datetime | None = None,
) -> BronzeArtifact:
    """
    PRD §8.3 sözleşmesine uygun ham snapshot'ı diske yazar.

    Çıktı yapısı::

        bronze/source=overpass/yyyy=2026/mm=05/dd=11/<idempotency_key>.json

    Dosya içeriği iki bloktan oluşur:
        * ``metadata`` — kaynak, lisans, atıf, API sürümü, sorgu hash'i.
        * ``data``     — kaynaktan gelen ham payload (dönüştürülmemiş).
    """
    when = when or _utc_now()
    meta = dict(metadata or {})
    meta.setdefault("extracted_at", when.isoformat())
    meta.setdefault("source", source)

    idem_params = {
        "source": source,
        "endpoint": meta.get("endpoint"),
        "query_hash": _payload_hash(meta.get("query")),
        "bbox": meta.get("bbox"),
    }
    key = idempotency_key(source, idem_params)
    meta["idempotency_key"] = key

    partition = _partition_for(source, when)
    partition.mkdir(parents=True, exist_ok=True)
    path = partition / f"{key.replace(':', '_')}.json"

    envelope = {"metadata": meta, "data": payload}
    path.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    rc = record_count if record_count is not None else _estimate_count(payload)
    try:
        display_path: str = str(path.relative_to(BRONZE_DIR.parent))
    except ValueError:
        display_path = str(path)
    logger.info(
        "bronze snapshot yazıldı: source=%s records=%d path=%s",
        source,
        rc,
        display_path,
    )
    return BronzeArtifact(
        source=source,
        path=path,
        record_count=rc,
        idempotency_key=key,
        metadata=meta,
    )


def _payload_hash(value: Any) -> str | None:
    if value is None:
        return None
    canon = value if isinstance(value, str) else json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:16]


def _estimate_count(payload: Any) -> int:
    """Best-effort kayıt sayma — Bronze metadata için sadece istatistik."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for k in ("elements", "results", "records", "items"):
            v = payload.get(k)
            if isinstance(v, list):
                return len(v)
            if isinstance(v, dict) and isinstance(v.get("bindings"), list):
                return len(v["bindings"])
    return 0
