"""
Wikidata SPARQL Extractor
=========================
PRD §8.1 #2: Çok dilli isimler, yapım yılları, tarihi açıklamalar, Wikipedia
kapak fotoğrafları. Lisans: **CC0** — atıf zorunlu değil; yine de kaynak gösterilir.

D1 (Pilot): ``wikibase:box`` SERVICE'i ile **İzmir bbox** sınırlandırması yapılır.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from etl.config import (
    IZMIR_BBOX,
    WIKIDATA_SPARQL_ENDPOINT,
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


# Kültürel miras kapsayıcı Q-ID kümesi (PRD §8.1).
# Q33506        Museum
# Q839954       Archaeological site
# Q570116       Tourist attraction (heritage filtreli)
# Q15661340     Ancient city
# Q44539        Temple
# Q16970        Church building
# Q32815        Mosque
# Q12518        Tower
# Q23413        Castle
# Q16560        Palace
# Q15243209     Historic district
# Q24398318     Religious building
# Q35112127     Historic site
_SPARQL_TEMPLATE = """
SELECT DISTINCT ?item ?itemLabel
       (SAMPLE(?coord) AS ?coord)
       (SAMPLE(?inception) AS ?inception)
       (SAMPLE(?image) AS ?image)
       (SAMPLE(?heritageStatus) AS ?heritageStatus)
       (SAMPLE(?nameTr) AS ?nameTr)
       (SAMPLE(?nameEn) AS ?nameEn)
       (SAMPLE(?nameDe) AS ?nameDe)
       (SAMPLE(?nameFr) AS ?nameFr)
       (SAMPLE(?nameAr) AS ?nameAr)
       (GROUP_CONCAT(DISTINCT ?typeId; separator="|") AS ?typeIds)
WHERE {{
  SERVICE wikibase:box {{
    ?item wdt:P625 ?coord .
    bd:serviceParam wikibase:cornerSouthWest "Point({west} {south})"^^geo:wktLiteral .
    bd:serviceParam wikibase:cornerNorthEast "Point({east} {north})"^^geo:wktLiteral .
  }}
  VALUES ?type {{
    wd:Q33506 wd:Q839954 wd:Q570116 wd:Q15661340
    wd:Q44539 wd:Q16970  wd:Q32815  wd:Q12518
    wd:Q23413 wd:Q16560  wd:Q15243209 wd:Q24398318
    wd:Q35112127
  }}
  ?item wdt:P31/wdt:P279* ?type .
  BIND(?type AS ?typeId)

  OPTIONAL {{ ?item wdt:P571 ?inception . }}
  OPTIONAL {{ ?item wdt:P18 ?image . }}
  OPTIONAL {{ ?item wdt:P1435 ?heritageStatus . }}

  OPTIONAL {{ ?item rdfs:label ?nameTr . FILTER(LANG(?nameTr) = "tr") }}
  OPTIONAL {{ ?item rdfs:label ?nameEn . FILTER(LANG(?nameEn) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?nameDe . FILTER(LANG(?nameDe) = "de") }}
  OPTIONAL {{ ?item rdfs:label ?nameFr . FILTER(LANG(?nameFr) = "fr") }}
  OPTIONAL {{ ?item rdfs:label ?nameAr . FILTER(LANG(?nameAr) = "ar") }}

  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "tr,en". }}
}}
GROUP BY ?item ?itemLabel
LIMIT {limit}
""".strip()


def build_query(bbox: BoundingBox = IZMIR_BBOX, *, limit: int = 5000) -> str:
    """SPARQL sorgusunu bbox + limit ile bağla."""
    return _SPARQL_TEMPLATE.format(
        west=bbox.west,
        south=bbox.south,
        east=bbox.east,
        north=bbox.north,
        limit=limit,
    )


def fetch(
    *,
    bbox: BoundingBox = IZMIR_BBOX,
    endpoint: str = WIKIDATA_SPARQL_ENDPOINT,
    limit: int = 5000,
    persist_bronze: bool = True,
) -> tuple[dict[str, Any], BronzeArtifact | None]:
    """
    Wikidata SPARQL endpoint'inden bbox içindeki kültürel miras kayıtlarını çek.

    Returns
    -------
    tuple
        ``(raw_payload, bronze_artifact)`` — payload Wikidata SPARQL JSON
        Results formatı (``head`` + ``results.bindings``).
    """
    query = build_query(bbox, limit=limit)
    logger.info("Wikidata fetch başlıyor: endpoint=%s bbox=%s", endpoint, bbox.as_dict())

    headers = {"Accept": "application/sparql-results+json"}
    try:
        with http_client(headers=headers) as client:
            response = client.get(endpoint, params={"query": query})
    except _NETWORK_ERRORS as exc:
        raise ExtractError(f"Wikidata network hatası: {exc}") from exc

    if response.status_code != 200:
        raise ExtractError(
            f"Wikidata HTTP {response.status_code}: {response.text[:300]}"
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise ExtractError(f"Wikidata yanıtı JSON değil: {exc}") from exc

    bindings = payload.get("results", {}).get("bindings", []) or []
    logger.info("Wikidata fetch tamamlandı: %d binding", len(bindings))

    artifact: BronzeArtifact | None = None
    if persist_bronze:
        artifact = write_bronze_snapshot(
            source="wikidata",
            payload=payload,
            record_count=len(bindings),
            metadata={
                "endpoint": endpoint,
                "query": query,
                "bbox": bbox.as_dict(),
                "license": "CC0-1.0",
                "attribution": "Wikidata (CC0)",
                "limit": limit,
            },
        )
    return payload, artifact


__all__ = ["build_query", "fetch"]
