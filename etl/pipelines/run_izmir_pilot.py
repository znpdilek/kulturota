"""
İzmir Pilot — Uçtan Uca ETL Pipeline (Adım 2)
=============================================
PRD §8.2 akışı:

    Extract  →  Bronze  →  Normalize (Silver)  →  Geofence  →  Dedup  →  Gold
                                                                  └──→  ai_decision_queue

D1 (Pilot Şehir): Yalnızca **İzmir bbox** (``26.0, 38.0, 28.5, 39.0``).

LLM / AI çağrısı bu adımda **yok**; Adım 3 (Otonom AI Karar Katmanı, PRD §9)
ayrı bir cron worker olarak ``ai_decision_queue``'yu işleyecek.

Apache Airflow / Prefect DAG'ları PRD §8.7'de tanımlıdır fakat MVP Adım 2
kapsamına dahil değildir; bu script Python invocation ile çalıştırılabilir::

    python -m etl.pipelines.run_izmir_pilot                    # tam akış
    python -m etl.pipelines.run_izmir_pilot --skip-load        # DB yazımı yok
    python -m etl.pipelines.run_izmir_pilot --only overpass    # tek kaynak

Pre-koşullar:
    * PostgreSQL + PostGIS ayakta (PRD §16).
    * Alembic migration'ları uygulanmış (``alembic upgrade head``).
    * ``.env`` dosyasında DB bağlantı bilgileri.
"""

from __future__ import annotations

import argparse
import logging
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from etl.config import IZMIR_BBOX
from etl.dedup.deduper import DedupResult, dedup_records
from etl.extract import bizizmir as ex_bizizmir
from etl.extract import overpass as ex_overpass
from etl.extract import wikidata as ex_wikidata
from etl.extract.base import BronzeArtifact, ExtractError, idempotency_key
from etl.normalize.schema import RawPlace
from etl.normalize import (
    normalize_bizizmir,
    normalize_overpass,
    normalize_wikidata,
)

logger = logging.getLogger("etl.pipelines.izmir_pilot")


ALL_SOURCES: tuple[str, ...] = ("overpass", "wikidata", "bizizmir")


# ---------------------------------------------------------------------------
# Çıkı tipleri
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class SourceStats:
    name: str
    extracted: int = 0
    normalized: int = 0
    artifact_path: str | None = None
    error: str | None = None


@dataclass(slots=True)
class PipelineReport:
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    sources: list[SourceStats] = field(default_factory=list)
    silver_total: int = 0
    geofence_dropped: int = 0
    dedup: DedupResult | None = None
    places_written: int = 0
    queue_written: int = 0
    skipped_load: bool = False
    error: str | None = None

    def summary(self) -> str:
        lines = [
            "=" * 70,
            f"İzmir Pilot ETL Raporu  ({self.started_at.isoformat()})",
            "=" * 70,
            f"Bitiş            : {self.finished_at.isoformat() if self.finished_at else '-'}",
            "",
            "Kaynak istatistikleri",
            "---------------------",
        ]
        for s in self.sources:
            err = f"  HATA: {s.error}" if s.error else ""
            lines.append(
                f"  {s.name:<10} extract={s.extracted:>5}  silver={s.normalized:>5}{err}"
            )
        lines += [
            "",
            f"Silver toplam     : {self.silver_total}",
            f"Geofence dropped  : {self.geofence_dropped}",
        ]
        if self.dedup is not None:
            lines += [
                f"Auto-merge cluster: {len(self.dedup.clusters)}",
                f"   - singleton    : {sum(1 for c in self.dedup.clusters if c.is_singleton)}",
                f"   - merged       : {sum(1 for c in self.dedup.clusters if not c.is_singleton)}",
                f"Queue (0.60–0.90) : {len(self.dedup.queued_pairs)}",
                f"Discard           : {len(self.dedup.discarded)}",
            ]
        if not self.skipped_load:
            lines += [
                "",
                f"Gold yazıldı      : {self.places_written}",
                f"Queue yazıldı     : {self.queue_written}",
            ]
        else:
            lines.append("Load adımı atlandı (--skip-load).")
        if self.error:
            lines += ["", f"HATA              : {self.error}"]
        lines.append("=" * 70)
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extract + Normalize
# ---------------------------------------------------------------------------
def _run_extract_and_normalize(
    sources: Iterable[str],
    *,
    persist_bronze: bool,
) -> tuple[list[RawPlace], list[SourceStats], list[BronzeArtifact]]:
    silver: list[RawPlace] = []
    stats: list[SourceStats] = []
    artifacts: list[BronzeArtifact] = []

    for src in sources:
        s = SourceStats(name=src)
        stats.append(s)
        try:
            if src == "overpass":
                payload, artifact = ex_overpass.fetch(persist_bronze=persist_bronze)
                extract_count = len(payload.get("elements") or [])
                rows = normalize_overpass(payload)
            elif src == "wikidata":
                payload, artifact = ex_wikidata.fetch(persist_bronze=persist_bronze)
                extract_count = len(payload.get("results", {}).get("bindings") or [])
                rows = normalize_wikidata(payload)
            elif src == "bizizmir":
                payload, artifact = ex_bizizmir.fetch(persist_bronze=persist_bronze)
                extract_count = sum(
                    len(r.get("records") or [])
                    for ds in payload.get("datasets", [])
                    for r in ds.get("resources", [])
                )
                rows = normalize_bizizmir(payload)
            else:
                raise ValueError(f"Bilinmeyen kaynak: {src}")

            s.extracted = extract_count
            s.normalized = len(rows)
            s.artifact_path = str(artifact.path) if artifact else None
            silver.extend(rows)
            if artifact:
                artifacts.append(artifact)

        except ExtractError as exc:
            s.error = f"ExtractError: {exc}"
            logger.error("%s extract başarısız: %s", src, exc)
        except Exception as exc:  # noqa: BLE001
            s.error = f"{exc.__class__.__name__}: {exc}"
            logger.exception("%s pipeline beklenmeyen hata", src)

    return silver, stats, artifacts


# ---------------------------------------------------------------------------
# Load (opsiyonel — --skip-load ile atlanır)
# ---------------------------------------------------------------------------
def _run_load(
    dedup_result: DedupResult,
    *,
    artifacts: list[BronzeArtifact],
    sources: list[str],
) -> tuple[int, int]:
    """
    DB'ye yazımı yap; içe import edilen DB bağımlılıkları yalnızca burada
    aktif olur (script ``--skip-load`` ile DB olmadan çalıştırılabilsin diye).
    """
    from app.db.session import SessionLocal
    from etl.load.etl_run import close_etl_run, open_etl_run
    from etl.load.gold_writer import write_clusters_to_gold
    from etl.load.queue_writer import write_queue_entries

    run_idem = idempotency_key(
        "izmir_pilot",
        {
            "sources": sources,
            "bbox": IZMIR_BBOX.as_dict(),
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        },
    )

    places_written = 0
    queue_written = 0
    with SessionLocal() as db:
        run = open_etl_run(
            db,
            dag_id="izmir_pilot",
            source=",".join(sources),
            idempotency_key=run_idem,
            metadata={
                "bbox": IZMIR_BBOX.as_dict(),
                "bronze_artifacts": [str(a.path) for a in artifacts],
            },
        )

        try:
            written_places, _ = write_clusters_to_gold(
                db, dedup_result.clusters, etl_run_id=run.id
            )
            written_queue = write_queue_entries(db, dedup_result.queued_pairs)
            db.commit()
            places_written = len(written_places)
            queue_written = len(written_queue)

            total_extracted = sum(a.record_count for a in artifacts) if artifacts else None
            close_etl_run(
                db,
                run,
                status="success",
                records_extracted=total_extracted,
                records_loaded=places_written + queue_written,
                extra_metadata={
                    "places_written": places_written,
                    "queue_written": queue_written,
                    "discarded": len(dedup_result.discarded),
                },
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            close_etl_run(
                db,
                run,
                status="failed",
                error_message=f"{exc.__class__.__name__}: {exc}",
            )
            raise

    return places_written, queue_written


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------
def run_pipeline(
    *,
    only: list[str] | None = None,
    skip_load: bool = False,
    persist_bronze: bool = True,
) -> PipelineReport:
    """
    Uçtan uca İzmir pilot pipeline'ını çalıştır.
    """
    report = PipelineReport()
    selected = only or list(ALL_SOURCES)

    logger.info(
        "Pipeline başlıyor: sources=%s, skip_load=%s, persist_bronze=%s",
        selected,
        skip_load,
        persist_bronze,
    )

    try:
        # 1-2-3. Extract + Normalize
        silver, stats, artifacts = _run_extract_and_normalize(
            selected, persist_bronze=persist_bronze
        )
        report.sources = stats

        # 4. Geofence (PRD §8.4) — normalizer'lar zaten uygulamış olmalı, fakat
        # ekstra güvence için son bir kez İzmir bbox süzgeci geçer.
        pre_count = len(silver)
        silver = [
            r for r in silver
            if r.lat is not None and r.lng is not None and IZMIR_BBOX.contains(r.lat, r.lng)
        ]
        report.geofence_dropped = pre_count - len(silver)
        report.silver_total = len(silver)
        logger.info(
            "Silver toplam: %d (geofence_drop=%d)",
            report.silver_total,
            report.geofence_dropped,
        )

        # 5. Dedup (PRD §8.5)
        dedup_result = dedup_records(silver)
        report.dedup = dedup_result

        # 6. Load (Gold + Queue)
        if skip_load:
            report.skipped_load = True
            logger.info("--skip-load aktif: DB yazımı atlandı.")
        else:
            try:
                places_written, queue_written = _run_load(
                    dedup_result,
                    artifacts=artifacts,
                    sources=selected,
                )
                report.places_written = places_written
                report.queue_written = queue_written
            except Exception as exc:  # noqa: BLE001
                report.error = f"Load aşamasında hata: {exc.__class__.__name__}: {exc}"
                logger.exception("Load aşaması başarısız")

    except Exception as exc:  # noqa: BLE001
        report.error = f"{exc.__class__.__name__}: {exc}"
        logger.error("Pipeline beklenmeyen hata: %s\n%s", exc, traceback.format_exc())

    report.finished_at = datetime.now(timezone.utc)
    return report


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="run_izmir_pilot",
        description="KültürRota — İzmir pilot ETL pipeline (Extract + Silver + Dedup + Load)",
    )
    parser.add_argument(
        "--only",
        action="append",
        choices=ALL_SOURCES,
        help="Sadece belirtilen kaynak(lar)dan çek (tekrarlanabilir).",
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="DB yazımını atla — sadece Bronze + Silver + Dedup raporu üret.",
    )
    parser.add_argument(
        "--no-bronze",
        action="store_true",
        help="Bronze snapshot'larını diske yazma (hızlı dry-run).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG seviyesi logging.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.verbose:
        logging.getLogger("etl").setLevel(logging.DEBUG)

    report = run_pipeline(
        only=args.only,
        skip_load=args.skip_load,
        persist_bronze=not args.no_bronze,
    )

    print(report.summary())
    if report.error:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
