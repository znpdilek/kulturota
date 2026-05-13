"""
Overpass API Extractor (OSM)
============================
PRD §8.1 #1: ``tourism=museum``, ``historic=*`` etiketli POI koordinatları
(ana lokasyon). Lisans: **ODbL** — "© OpenStreetMap contributors".

D1 (Pilot): Yalnızca **İzmir bbox** içinde sorgu çalışır.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from etl.config import (
    IZMIR_BBOX,
    OVERPASS_ENDPOINT,
    OVERPASS_TIMEOUT_S,
    BoundingBox,
)
from etl.extract.base import (
    BronzeArtifact,
    ExtractError,
    http_client,
    write_bronze_snapshot,
)

logger = logging.getLogger(__name__)


_NETWORK_ERRORS: tuple[type[BaseException], ...] = (
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.RemoteProtocolError,
)


# PRD §8.1: ``tourism=museum`` + ``historic=*`` (geniş, kültürel miras kapsayıcı).
# Ek filtreler — ören yeri ve dini/sivil tarihi yapılar.
_OVERPASS_QL_TEMPLATE = """
[out:json][timeout:{timeout}];
(
  node["tourism"="museum"]({bbox});
  way["tourism"="museum"]({bbox});
  relation["tourism"="museum"]({bbox});

  node["historic"]({bbox});
  way["historic"]({bbox});
  relation["historic"]({bbox});

  node["heritage"]({bbox});
  way["heritage"]({bbox});
  relation["heritage"]({bbox});

  node["tourism"="artwork"]["artwork_type"~"sculpture|statue|monument"]({bbox});
  way["tourism"="artwork"]["artwork_type"~"sculpture|statue|monument"]({bbox});

  node["tourism"="attraction"]["historic"]({bbox});
  way["tourism"="attraction"]["historic"]({bbox});
);
out center tags;
""".strip()


def build_query(bbox: BoundingBox = IZMIR_BBOX, *, timeout_s: int = OVERPASS_TIMEOUT_S) -> str:
    """Overpass QL sorgusunu bbox parametresine bağla."""
    return _OVERPASS_QL_TEMPLATE.format(
        bbox=bbox.as_overpass_box(),
        timeout=timeout_s,
    )


def fetch(
    *,
    bbox: BoundingBox = IZMIR_BBOX,
    endpoint: str = OVERPASS_ENDPOINT,
    persist_bronze: bool = True,
) -> tuple[dict[str, Any], BronzeArtifact | None]:
    """
    Overpass API'den İzmir bbox'ı için OSM POI'lerini çek.

    Returns
    -------
    tuple
        ``(raw_payload, bronze_artifact)`` — payload Overpass'ın orijinal
        JSON cevabı; ``persist_bronze=False`` ise ``bronze_artifact`` ``None``.
    """
    query = build_query(bbox)
    logger.info("Overpass fetch başlıyor: endpoint=%s bbox=%s", endpoint, bbox.as_overpass_box())

    try:
        with http_client(timeout=OVERPASS_TIMEOUT_S + 30) as client:
            response = client.post(endpoint, data={"data": query})
    except _NETWORK_ERRORS as exc:
        raise ExtractError(f"Overpass network hatası: {exc}") from exc

    if response.status_code != 200:
        raise ExtractError(
            f"Overpass HTTP {response.status_code}: {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExtractError(f"Overpass yanıtı JSON değil: {exc}") from exc

    elements = payload.get("elements", []) or []
    logger.info("Overpass fetch tamamlandı: %d element", len(elements))

    artifact: BronzeArtifact | None = None
    if persist_bronze:
        artifact = write_bronze_snapshot(
            source="overpass",
            payload=payload,
            record_count=len(elements),
            metadata={
                "endpoint": endpoint,
                "query": query,
                "bbox": bbox.as_dict(),
                "license": "ODbL-1.0",
                "attribution": "© OpenStreetMap contributors",
                "api_version": payload.get("version"),
                "generator": payload.get("generator"),
                "osm_timestamp": payload.get("osm3s", {}).get("timestamp_osm_base"),
            },
        )
    return payload, artifact


__all__ = ["build_query", "fetch"]
