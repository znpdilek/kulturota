"""
ETL Run Log Yardımcıları
========================
PRD §8.3: "Tüm fetch işlemleri ``etl_run_log`` tablosuna ``idempotency_key`` ile
yazılır." Bu modül her pipeline çalışmasını başlat-bitir audit altına alır.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.etl_run_log import ETLRunLog

logger = logging.getLogger(__name__)


def open_etl_run(
    db: Session,
    *,
    dag_id: str,
    source: str,
    idempotency_key: str,
    metadata: dict[str, Any] | None = None,
) -> ETLRunLog:
    """
    Yeni bir ``etl_run_log`` satırı aç ve commit et.

    Aynı ``idempotency_key`` için zaten bir kayıt varsa onu döner — re-run
    güvenli (PRD §8.3).
    """
    existing = (
        db.query(ETLRunLog).filter(ETLRunLog.idempotency_key == idempotency_key).one_or_none()
    )
    if existing is not None:
        logger.info("etl_run_log idempotent hit: key=%s id=%s", idempotency_key, existing.id)
        return existing

    run = ETLRunLog(
        id=uuid.uuid4(),
        dag_id=dag_id,
        source=source,
        idempotency_key=idempotency_key,
        started_at=datetime.now(timezone.utc),
        status="running",
        run_metadata=metadata,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info("etl_run_log açıldı: id=%s dag=%s source=%s", run.id, dag_id, source)
    return run


def close_etl_run(
    db: Session,
    run: ETLRunLog,
    *,
    status: str = "success",
    records_extracted: int | None = None,
    records_loaded: int | None = None,
    error_message: str | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> ETLRunLog:
    """``etl_run_log`` satırını kapat (``finished_at`` + counters + status)."""
    run.finished_at = datetime.now(timezone.utc)
    run.status = status
    if records_extracted is not None:
        run.records_extracted = records_extracted
    if records_loaded is not None:
        run.records_loaded = records_loaded
    if error_message is not None:
        run.error_message = error_message
    if extra_metadata:
        merged = dict(run.run_metadata or {})
        merged.update(extra_metadata)
        run.run_metadata = merged

    db.add(run)
    db.commit()
    db.refresh(run)
    logger.info(
        "etl_run_log kapandı: id=%s status=%s extracted=%s loaded=%s",
        run.id,
        run.status,
        run.records_extracted,
        run.records_loaded,
    )
    return run


__all__ = ["close_etl_run", "open_etl_run"]
