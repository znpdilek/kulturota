"""
KültürRota — ETL Pipeline (İzmir Pilot)
=======================================
PRD v2.0 · Bölüm 8 (Veri Kaynakları ve ETL Pipeline).

Bu paket Bronze → Silver → Gold medallion mimarisinin **Extract**, **Normalize**
ve **Deduplicate/Write** adımlarını içerir. Otonom AI Karar Katmanı (PRD Bölüm 9)
ve Apache Airflow / Prefect orkestrasyonu **bu adımın kapsamı dışındadır**.

Alt paketler
------------
* ``etl.extract``    — Overpass (OSM), Wikidata SPARQL ve Bizizmir Açık Veri
  kaynaklarından ham (Bronze) snapshot alır.
* ``etl.normalize``  — Bronze çıktıları kanonik **Silver** şemasına (``RawPlace``)
  eşler; Türkçe casefold, NFC normalize, kategori taksonomisi uygular.
* ``etl.dedup``      — Geohash-7 bloklama, haversine + token-set ratio + kategori
  uyumu ağırlıklı skoru ve eşik kurallarını işletir (PRD 8.5).
* ``etl.load``       — Otomatik birleşen kayıtları ``places`` tablosuna (Gold),
  şüpheli kayıtları ``ai_decision_queue`` tablosuna yazar.
* ``etl.pipelines``  — Tüm adımları İzmir bbox üzerinde uçtan uca çalıştıran
  bağımsız Python script'leri.

D1 Kararı (PRD §2)
------------------
Tüm extract/normalize/load işlemleri **yalnızca İzmir bbox**
(``26.0, 38.0, 28.5, 39.0``) için çalışacak şekilde sabitlenmiştir.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("etl")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
