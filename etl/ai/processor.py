"""
Otonom AI Karar Kuyruğu Tüketicisi (PRD §9)
===========================================
PRD §9.1 mimari akışını birebir uygular:

    fetch(pending) → prompt → LLM → parse → karar uygula → log →
    time.sleep(RATE_LIMIT_SEC)

PRD §9.3 (mentor direktifi) garantilerinin bu modülde sağlandığı yerler:

    * Rate-limit       : ``time.sleep(settings.AI_RATE_LIMIT_SEC)`` her çağrı
                         sonrası (varsayılan 4.5 sn → 15 RPM).
    * Daily quota      : ``batch_size <= settings.AI_DAILY_QUOTA`` (varsayılan
                         1400 / 1500 günlük limit).
    * Quota tükenmesi  : :class:`QuotaExhaustedError` → döngü kırılır, ertesi
                         güne ertelenir (maliyet = 0).
    * 429 RateLimit    : ``time.sleep(60)`` bekleyip aynı kayıt için tek bir
                         retry; başarısız olursa ``retry_count +1`` ve PENDING'de
                         kal.
    * Audit izi        : Her LLM çağrısı (başarılı veya başarısız) için
                         :class:`AIDecisionLog` satırı (PRD §9.6).
    * Idempotency      : ``prompt_hash`` → aynı (system, user) çifti her zaman
                         aynı karar → re-run güvenli.

Confidence eşik kuralı (PRD §9.3 + §9.6):
    * ``confidence >= AI_CONFIDENCE_THRESHOLD`` (0.85) →
        - ``merge``  → ``places`` INSERT + queue.status=MERGED
        - ``split``  → 2× ``places`` INSERT + queue.status=APPROVED
        - ``reject`` → yazım yok + queue.status=REJECTED
    * ``confidence <  AI_CONFIDENCE_THRESHOLD`` →
        - retry_count +1, status RETRY (PENDING gibi davranır)
        - retry_count >= AI_MAX_RETRY_COUNT (3) → REJECTED + log notu
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.enums import (
    AIDecisionStatus,
    AIDecisionType,
    AIModelProvider,
)
from app.db.session import SessionLocal
from app.models.ai_decision_log import AIDecisionLog
from app.models.ai_decision_queue import AIDecisionQueue
from etl.ai.decision_applier import (
    ApplyResult,
    ParsedDecision,
    apply_decision,
    parse_decision,
)
from etl.ai.exceptions import (
    LLMResponseError,
    QuotaExhaustedError,
    RateLimitError,
)
from etl.ai.llm_client import GeminiFlashClient, LLMResponse
from etl.ai.prompts import SYSTEM_PROMPT, build_user_prompt, hash_prompt

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rapor
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ProcessorReport:
    """Cron run sonu özet rapor (operasyonel görünürlük PRD §9.7)."""

    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None

    fetched: int = 0
    processed_ok: int = 0  # confidence ≥ eşik + uygulanmış karar
    queued_for_retry: int = 0  # düşük güven, retry_count +1
    rejected: int = 0  # max retry aşıldı veya AI reject
    merged: int = 0
    split: int = 0
    api_errors: int = 0
    quota_aborted: bool = False
    places_written: int = 0
    dry_run: bool = False

    def summary(self) -> str:
        dur = (
            (self.finished_at - self.started_at).total_seconds()
            if self.finished_at
            else 0.0
        )
        lines = [
            "=" * 70,
            "Otonom AI Karar Katmanı — Run Raporu (PRD §9)",
            "=" * 70,
            f"Başlangıç         : {self.started_at.isoformat()}",
            f"Bitiş             : "
            f"{self.finished_at.isoformat() if self.finished_at else '-'}",
            f"Süre              : {dur:.1f} sn",
            f"Mod               : {'DRY-RUN' if self.dry_run else 'CANLI'}",
            "",
            "Kuyruk istatistikleri",
            "---------------------",
            f"Fetch edilen      : {self.fetched}",
            f"Uygulanmış karar  : {self.processed_ok}",
            f"  - merge         : {self.merged}",
            f"  - split         : {self.split}",
            f"  - reject        : {self.rejected}",
            f"Retry'a alındı    : {self.queued_for_retry}",
            f"API hata          : {self.api_errors}",
            f"Places insert     : {self.places_written}",
            f"Quota tükendi mi  : {'EVET (ertesi güne ertelendi)' if self.quota_aborted else 'hayır'}",
            "=" * 70,
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Kayıt fetch
# ---------------------------------------------------------------------------
def _fetch_pending(db: Session, limit: int) -> list[AIDecisionQueue]:
    """
    ``status='pending'`` veya ``status='retry'`` olan, ``retry_count <
    AI_MAX_RETRY_COUNT`` kayıtları FIFO sırasıyla çek.
    """
    return (
        db.query(AIDecisionQueue)
        .filter(
            AIDecisionQueue.status.in_(
                [AIDecisionStatus.PENDING, AIDecisionStatus.RETRY]
            ),
            AIDecisionQueue.retry_count < settings.AI_MAX_RETRY_COUNT,
        )
        .order_by(AIDecisionQueue.created_at.asc())
        .limit(limit)
        .all()
    )


# ---------------------------------------------------------------------------
# Audit log yazımı
# ---------------------------------------------------------------------------
def _persist_log(
    db: Session,
    *,
    queue: AIDecisionQueue,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    decision_type: AIDecisionType,
    confidence: float,
    prompt_hash: str,
    model_version: str,
    latency_ms: int | None,
    tokens_used: int | None,
    extra_note: str | None = None,
) -> AIDecisionLog:
    """
    PRD §9.6 — Her AI çağrısı için tam audit izi.

    Hata durumlarında bile çağrılır (response_payload hata mesajı içerir).
    """
    if extra_note:
        annotated = dict(response_payload or {})
        annotated.setdefault("_processor_note", extra_note)
        response_payload = annotated

    log = AIDecisionLog(
        id=uuid.uuid4(),
        queue_id=queue.id,
        model_provider=AIModelProvider.GEMINI,
        model_version=model_version,
        prompt_hash=prompt_hash,
        request_payload=request_payload,
        response_payload=response_payload,
        decision=decision_type,
        confidence=confidence,
        latency_ms=latency_ms,
        tokens_used=tokens_used,
    )
    db.add(log)
    return log


# ---------------------------------------------------------------------------
# Tek kayıt işleme
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class _SingleRunOutcome:
    """Tek bir queue kaydı için çağrı çıktısı (processor istatistikleri için)."""

    applied: bool = False
    decision: AIDecisionType | None = None
    places_written: int = 0
    retry_incremented: bool = False
    rejected: bool = False
    api_error: bool = False


def _process_one(
    db: Session,
    queue: AIDecisionQueue,
    *,
    client: GeminiFlashClient,
    dry_run: bool,
) -> _SingleRunOutcome:
    """
    Tek bir kuyruk satırını işle. Exception fırlatmaz — tüm hata durumları
    audit log + queue.status güncellemesi ile içselleştirilir.

    QuotaExhaustedError ÜST KATMANA kaçar (döngüyü kırar — PRD §9.3).
    """
    outcome = _SingleRunOutcome()
    payload = queue.payload or {}

    # --- 1. Prompt kur ----------------------------------------------------
    user_prompt = build_user_prompt(payload)
    prompt_hash = hash_prompt(SYSTEM_PROMPT, user_prompt)
    request_payload: dict[str, Any] = {
        "system": SYSTEM_PROMPT,
        "user": user_prompt,
        "prompt_hash": prompt_hash,
        "model": client.model,
    }

    # --- 2. LLM çağrısı ---------------------------------------------------
    llm_response: LLMResponse | None = None
    api_error_msg: str | None = None
    try:
        llm_response = client.generate_decision(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )
    except RateLimitError as exc:
        # PRD §9.3: 60 sn bekle ve TEK bir retry yap (aynı kayıt için).
        backoff = exc.retry_after_sec or settings.AI_RATE_LIMIT_BACKOFF_SEC
        logger.warning(
            "Rate limit (queue_id=%s). %.0f sn bekleniyor sonra tek retry…",
            queue.id,
            backoff,
        )
        time.sleep(backoff)
        try:
            llm_response = client.generate_decision(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=user_prompt,
            )
        except RateLimitError as exc2:
            api_error_msg = f"RateLimit tekrar: {exc2}"
        except LLMResponseError as exc2:
            api_error_msg = f"LLMResponseError (rate-limit retry sonrası): {exc2}"
    except LLMResponseError as exc:
        api_error_msg = f"LLMResponseError: {exc}"
    # QuotaExhaustedError BURADA YAKALANMAZ — döngüyü kırar.

    # --- 2b. API hata sonrası: retry_count +1, audit log, sonraki kayda geç
    if llm_response is None:
        outcome.api_error = True
        queue.retry_count = (queue.retry_count or 0) + 1
        if queue.retry_count >= settings.AI_MAX_RETRY_COUNT:
            queue.status = AIDecisionStatus.REJECTED
            queue.processed_at = datetime.now(timezone.utc)
            outcome.rejected = True
            note = (
                f"api_error_max_retry: {api_error_msg} "
                f"(retry_count={queue.retry_count})"
            )
        else:
            queue.status = AIDecisionStatus.RETRY
            outcome.retry_incremented = True
            note = (
                f"api_error_retry: {api_error_msg} "
                f"(retry_count={queue.retry_count})"
            )

        _persist_log(
            db,
            queue=queue,
            request_payload=request_payload,
            response_payload={"error": api_error_msg or "unknown"},
            decision_type=AIDecisionType.REJECT,
            confidence=0.0,
            prompt_hash=prompt_hash,
            model_version=client.model,
            latency_ms=None,
            tokens_used=None,
            extra_note=note,
        )
        return outcome

    # --- 3. Yanıtı parse et (PRD §9.4) ------------------------------------
    try:
        parsed: ParsedDecision = parse_decision(llm_response.parsed)
    except ValueError as exc:
        # Şema ihlali → audit'e yaz, retry_count +1.
        outcome.api_error = True
        queue.retry_count = (queue.retry_count or 0) + 1
        if queue.retry_count >= settings.AI_MAX_RETRY_COUNT:
            queue.status = AIDecisionStatus.REJECTED
            queue.processed_at = datetime.now(timezone.utc)
            outcome.rejected = True
            note = (
                f"schema_error_max_retry: {exc} "
                f"(retry_count={queue.retry_count})"
            )
        else:
            queue.status = AIDecisionStatus.RETRY
            outcome.retry_incremented = True
            note = (
                f"schema_error_retry: {exc} (retry_count={queue.retry_count})"
            )
        _persist_log(
            db,
            queue=queue,
            request_payload=request_payload,
            response_payload=llm_response.raw_response,
            decision_type=AIDecisionType.REJECT,
            confidence=0.0,
            prompt_hash=prompt_hash,
            model_version=llm_response.model_version,
            latency_ms=llm_response.latency_ms,
            tokens_used=llm_response.total_tokens,
            extra_note=note,
        )
        return outcome

    # --- 4. Confidence eşik kontrolü (PRD §9.3) ---------------------------
    threshold = settings.AI_CONFIDENCE_THRESHOLD
    if parsed.confidence < threshold:
        queue.retry_count = (queue.retry_count or 0) + 1
        if queue.retry_count >= settings.AI_MAX_RETRY_COUNT:
            queue.status = AIDecisionStatus.REJECTED
            queue.processed_at = datetime.now(timezone.utc)
            outcome.rejected = True
            note = (
                f"low_confidence_max_retry: c={parsed.confidence:.2f} "
                f"< {threshold:.2f} (retry_count={queue.retry_count})"
            )
        else:
            queue.status = AIDecisionStatus.RETRY
            outcome.retry_incremented = True
            note = (
                f"low_confidence_retry: c={parsed.confidence:.2f} "
                f"< {threshold:.2f} (retry_count={queue.retry_count})"
            )

        _persist_log(
            db,
            queue=queue,
            request_payload=request_payload,
            response_payload=llm_response.raw_response,
            decision_type=parsed.decision,
            confidence=parsed.confidence,
            prompt_hash=prompt_hash,
            model_version=llm_response.model_version,
            latency_ms=llm_response.latency_ms,
            tokens_used=llm_response.total_tokens,
            extra_note=note,
        )
        return outcome

    # --- 5. Confidence yeterli → kararı uygula ----------------------------
    apply_result: ApplyResult
    if dry_run:
        apply_result = ApplyResult(
            written_place_ids=[],
            canonical_used=parsed.canonical,
            note=f"dry_run: decision={parsed.decision.value} c={parsed.confidence:.2f}",
        )
    else:
        try:
            apply_result = apply_decision(
                db,
                queue_id=queue.id,
                queue_payload=payload,
                decision=parsed,
            )
        except Exception as exc:  # noqa: BLE001
            # DB yazım hatası: rollback DEĞIL (üst katman processor commit yönetir).
            # Sadece bu kaydı işaretle ve audit'e yaz.
            logger.exception(
                "apply_decision DB hatası queue_id=%s",
                queue.id,
            )
            outcome.api_error = True
            queue.retry_count = (queue.retry_count or 0) + 1
            queue.status = AIDecisionStatus.RETRY
            outcome.retry_incremented = True
            _persist_log(
                db,
                queue=queue,
                request_payload=request_payload,
                response_payload=llm_response.raw_response,
                decision_type=parsed.decision,
                confidence=parsed.confidence,
                prompt_hash=prompt_hash,
                model_version=llm_response.model_version,
                latency_ms=llm_response.latency_ms,
                tokens_used=llm_response.total_tokens,
                extra_note=f"apply_error: {exc.__class__.__name__}: {exc}",
            )
            return outcome

    # --- 6. Queue durum güncellemesi --------------------------------------
    queue.processed_at = datetime.now(timezone.utc)
    if parsed.decision == AIDecisionType.MERGE:
        queue.status = AIDecisionStatus.MERGED
        queue.candidate_place_ids = apply_result.written_place_ids or None
    elif parsed.decision == AIDecisionType.SPLIT:
        queue.status = AIDecisionStatus.APPROVED
        queue.candidate_place_ids = apply_result.written_place_ids or None
    else:  # REJECT
        queue.status = AIDecisionStatus.REJECTED

    outcome.applied = True
    outcome.decision = parsed.decision
    outcome.places_written = len(apply_result.written_place_ids)

    # --- 7. Audit log -----------------------------------------------------
    _persist_log(
        db,
        queue=queue,
        request_payload=request_payload,
        response_payload=llm_response.raw_response,
        decision_type=parsed.decision,
        confidence=parsed.confidence,
        prompt_hash=prompt_hash,
        model_version=llm_response.model_version,
        latency_ms=llm_response.latency_ms,
        tokens_used=llm_response.total_tokens,
        extra_note=apply_result.note,
    )

    logger.info(
        "AI karar uygulandı queue_id=%s decision=%s c=%.2f writes=%d",
        queue.id,
        parsed.decision.value,
        parsed.confidence,
        outcome.places_written,
    )
    return outcome


# ---------------------------------------------------------------------------
# Ana döngü
# ---------------------------------------------------------------------------
def process_pending_queue(
    *,
    batch_size: int | None = None,
    rate_limit_sec: float | None = None,
    dry_run: bool = False,
    db_factory=SessionLocal,
    client: GeminiFlashClient | None = None,
) -> ProcessorReport:
    """
    PRD §9.1 ana döngüsünü çalıştır.

    Parameters
    ----------
    batch_size : int | None
        Bu run'da işlenecek maks kayıt sayısı. ``None`` → settings.AI_BATCH_SIZE.
        Daily quota'yı aşacak değerler ``AI_DAILY_QUOTA``'ya clamp edilir.
    rate_limit_sec : float | None
        Her LLM çağrısı sonrası bekleme süresi. ``None`` → settings.AI_RATE_LIMIT_SEC.
    dry_run : bool
        True ise ``places`` tablosuna yazım yapılmaz; karar parse + audit log
        + queue status güncellemesi yine yapılır (test/preview için).
    db_factory : callable
        Test injection için DB session factory. Üretimde ``SessionLocal``.
    client : GeminiFlashClient | None
        Önceden hazırlanmış istemci (test injection). ``None`` → yeni instance.

    Returns
    -------
    ProcessorReport
        Tek satırlık özet rapor.
    """
    report = ProcessorReport(dry_run=dry_run)

    effective_batch = batch_size or settings.AI_BATCH_SIZE
    effective_batch = min(effective_batch, settings.AI_DAILY_QUOTA)
    rate_sec = (
        rate_limit_sec if rate_limit_sec is not None else settings.AI_RATE_LIMIT_SEC
    )

    logger.info(
        "AI Karar Cron başlıyor: batch_size=%d rate_limit=%.2fs dry_run=%s "
        "model=%s confidence_threshold=%.2f",
        effective_batch,
        rate_sec,
        dry_run,
        settings.GEMINI_MODEL,
        settings.AI_CONFIDENCE_THRESHOLD,
    )

    own_client = False
    if client is None:
        client = GeminiFlashClient()
        own_client = True

    try:
        with db_factory() as db:
            pending = _fetch_pending(db, limit=effective_batch)
            report.fetched = len(pending)
            logger.info(
                "Fetch edilen pending kayıt: %d",
                report.fetched,
            )

            if not pending:
                logger.info("İşlenecek kayıt yok. Çıkılıyor.")
                report.finished_at = datetime.now(timezone.utc)
                return report

            for idx, queue in enumerate(pending, start=1):
                try:
                    outcome = _process_one(
                        db,
                        queue,
                        client=client,
                        dry_run=dry_run,
                    )
                except QuotaExhaustedError as exc:
                    # PRD §9.3: kota tükenince DUR (maliyet=0 garantisi).
                    logger.warning(
                        "Günlük kota tükendi (queue_id=%s): %s. "
                        "Döngü kırılıyor — ertesi geceye ertelendi.",
                        queue.id,
                        exc,
                    )
                    report.quota_aborted = True
                    db.commit()
                    break

                # Sayaçları güncelle
                if outcome.api_error:
                    report.api_errors += 1
                if outcome.retry_incremented:
                    report.queued_for_retry += 1
                if outcome.applied:
                    report.processed_ok += 1
                    if outcome.decision == AIDecisionType.MERGE:
                        report.merged += 1
                    elif outcome.decision == AIDecisionType.SPLIT:
                        report.split += 1
                    elif outcome.decision == AIDecisionType.REJECT:
                        report.rejected += 1
                if outcome.rejected and not outcome.applied:
                    # Max retry'a takılıp rejected'a düşen kayıtlar.
                    report.rejected += 1
                report.places_written += outcome.places_written

                # Her N kayıtta bir commit — uzun run'larda lock süresini kıs.
                if idx % 10 == 0:
                    db.commit()

                # PRD §9.3: ana yavaşlatma — her çağrı sonrası.
                if idx < len(pending) and rate_sec > 0:
                    time.sleep(rate_sec)

            db.commit()
    finally:
        if own_client:
            client.close()

    report.finished_at = datetime.now(timezone.utc)
    return report


__all__ = ["ProcessorReport", "process_pending_queue"]
