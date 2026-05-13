"""
ETL — Extract Katmanı
=====================
PRD §8.3: Bronze (ham veri gölü) için kaynak-spesifik çekiciler.

* :mod:`etl.extract.overpass`  — OSM Overpass API
* :mod:`etl.extract.wikidata`  — Wikidata SPARQL
* :mod:`etl.extract.bizizmir`  — Bizizmir Açık Veri (CKAN)

Her çekici, payload'ı kanonik bir Bronze partition'ına (`bronze/source=.../yyyy=.../mm=.../dd=.../...json`)
yazar ve **hiçbir dönüşüm uygulamaz** (PRD §8.3 sözleşmesi).
"""

from etl.extract.base import (
    BronzeArtifact,
    ExtractError,
    idempotency_key,
    write_bronze_snapshot,
)

__all__ = [
    "BronzeArtifact",
    "ExtractError",
    "idempotency_key",
    "write_bronze_snapshot",
]
