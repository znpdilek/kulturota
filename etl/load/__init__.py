"""
ETL — Load Katmanı
==================
PRD §8.5 + §10:
    * Otomatik birleşen cluster'lar :class:`Place` (Gold) tablosuna yazılır.
    * Şüpheli çiftler :class:`AIDecisionQueue` tablosuna yazılır
      (AI karar mekanizması Adım 3'te işleyecek).
    * Pipeline run'ı :class:`ETLRunLog` ile audit altına alınır.
"""

from etl.load.etl_run import close_etl_run, open_etl_run
from etl.load.gold_writer import write_clusters_to_gold
from etl.load.queue_writer import write_queue_entries

__all__ = [
    "close_etl_run",
    "open_etl_run",
    "write_clusters_to_gold",
    "write_queue_entries",
]
