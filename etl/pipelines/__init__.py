"""
ETL — Uçtan Uca Pipeline Scriptleri (İzmir Pilot)
================================================
Apache Airflow / Prefect henüz devreye alınmadı (PRD §8.7); bu paket
her pipeline'ı **bağımsız Python script** olarak sağlar.

Çalıştırma örnekleri::

    # Tek bir kaynak için yalnız extract:
    python -m etl.pipelines.run_izmir_pilot --only overpass

    # Uçtan uca İzmir pipeline'ı:
    python -m etl.pipelines.run_izmir_pilot
"""
