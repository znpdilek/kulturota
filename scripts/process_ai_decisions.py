"""
Otonom AI Karar Katmanı — CLI Cron Worker (PRD §9)
==================================================
``ai_decision_queue`` tablosunda ``status='pending'`` olan şüpheli kayıtları
Gemini Flash (free-tier) ile karara bağlar; PRD §9.4 OUTPUT_SCHEMA'sına uygun
JSON yanıtı parse eder; confidence ≥ 0.85 ise ``places`` (Gold) tablosuna
merge/split/reject olarak uygular; her kararı ``ai_decision_log`` tablosuna yazar.

PRD §9.3 — Mentor Direktifi Uyumu
---------------------------------
* Her çağrı sonrası ``time.sleep(AI_RATE_LIMIT_SEC)`` (varsayılan 4.5 sn → 15 RPM).
* Günlük max ``AI_DAILY_QUOTA`` (varsayılan 1400) kayıt işlenir.
* 429 RateLimit'te 60 sn bekleyip tek retry; tükenirse retry_count +1.
* Kota tükenince döngü kırılır — ertesi geceye ertelenir (maliyet = 0).

Kullanım
--------
Tipik gecelik cron (PRD §9.1 02:00 TSI):

    python -m scripts.process_ai_decisions

Geliştirme / smoke test (DB'ye Place yazmaz, sadece audit log):

    python -m scripts.process_ai_decisions --dry-run --batch-size 5 --verbose

Pre-koşullar:
    1. PostgreSQL + PostGIS ayakta (``docker compose up -d postgres redis``).
    2. Alembic migration'ları uygulanmış (``alembic upgrade head``).
    3. ``ai_decision_queue`` tablosunda en az bir ``status='pending'`` kayıt
       (ETL pipeline çalıştırılarak üretilir:
       ``python -m etl.pipelines.run_izmir_pilot``).
    4. ``.env`` dosyasında ``GEMINI_API_KEY=...`` tanımlı
       (https://aistudio.google.com/app/apikey — ücretsiz).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="process_ai_decisions",
        description=(
            "KültürRota — Otonom AI Karar Katmanı cron worker "
            "(PRD §9; Gemini Flash free-tier)."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=(
            "Bu run'da işlenecek maksimum kayıt sayısı "
            "(default: settings.AI_BATCH_SIZE, clamp: AI_DAILY_QUOTA)."
        ),
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=None,
        help=(
            "LLM çağrıları arası bekleme süresi (saniye). "
            "Varsayılan: settings.AI_RATE_LIMIT_SEC (4.5)."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "places tablosuna yazım YAPMA; sadece karar parse + ai_decision_log + "
            "queue status güncellemesi yap. Smoke / preview için."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="DEBUG seviyesi logging.",
    )
    return parser.parse_args(argv)


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 3. parti kütüphanelerin DEBUG spam'ini bastır.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    _setup_logging(args.verbose)

    # Settings'i şimdi import et — argparse hatalarında stack trace temiz olsun.
    from app.core.config import settings
    from etl.ai.processor import process_pending_queue

    if not settings.GEMINI_API_KEY:
        print(
            "[HATA] GEMINI_API_KEY tanımlı değil. .env dosyasına ekleyin:\n"
            "       GEMINI_API_KEY=...\n"
            "Ücretsiz anahtar: https://aistudio.google.com/app/apikey",
            file=sys.stderr,
        )
        return 2

    try:
        report = process_pending_queue(
            batch_size=args.batch_size,
            rate_limit_sec=args.rate_limit,
            dry_run=args.dry_run,
        )
    except KeyboardInterrupt:
        print("\n[BİLGİ] Kullanıcı tarafından kesildi (KeyboardInterrupt).")
        return 130
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception(
            "AI cron beklenmeyen hata: %s", exc
        )
        return 1

    print(report.summary())
    return 0


if __name__ == "__main__":
    sys.exit(main())
