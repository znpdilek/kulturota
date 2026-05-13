"""Step 3 — Otonom AI Karar Katmanı smoke test (no network, no DB writes).

Bu script SADECE şunları doğrular:
    * etl.ai paketinin tüm modülleri import edilebiliyor mu?
    * PRD §9.4 prompt builder + hash deterministik çalışıyor mu?
    * LLM yanıtı parse'ı (mock JSON) PRD §9.4 OUTPUT_SCHEMA'sına uygun mu?

Gemini API çağrısı YAPMAZ; DB erişimi YAPMAZ.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    out: list[str] = []
    log_path = PROJECT_ROOT / "ai_smoke.log"

    def step(label: str) -> None:
        out.append(f"[ok] {label}")

    try:
        from etl.ai import process_pending_queue, ProcessorReport  # noqa: F401
        from etl.ai.exceptions import (  # noqa: F401
            AIDecisionError,
            LLMResponseError,
            QuotaExhaustedError,
            RateLimitError,
        )
        from etl.ai.prompts import (
            MAX_FIELD_LENGTH,
            SYSTEM_PROMPT,
            build_user_prompt,
            hash_prompt,
        )
        from etl.ai.llm_client import GeminiFlashClient, LLMResponse  # noqa: F401
        from etl.ai.decision_applier import (
            ParsedDecision,
            apply_decision,  # noqa: F401
            parse_decision,
        )
        from etl.ai.processor import _fetch_pending  # noqa: F401
        step("etl.ai paketi tüm modüller import edildi")

        # PRD §9.4 — system prompt + JSON output guarantee
        assert "SADECE JSON" in SYSTEM_PROMPT
        assert "merge" in SYSTEM_PROMPT and "split" in SYSTEM_PROMPT and "reject" in SYSTEM_PROMPT
        assert "primary_source_per_field" in SYSTEM_PROMPT
        step("PRD §9.4 system prompt 'SADECE JSON' + decision domain'i içeriyor")

        # PRD §9.4 örnek payload üzerinden user prompt
        payload = {
            "candidate_a": {
                "source": "osm",
                "source_id": "node/9001",
                "name_tr": "Efes Antik Kenti",
                "name_en": "Ephesus",
                "lat": 37.94,
                "lng": 27.34,
                "canonical_categories": ["archaeological_site"],
            },
            "candidate_b": {
                "source": "wikidata",
                "source_id": "Q43332",
                "name_tr": "Efes",
                "name_en": "Ephesus",
                "lat": 37.939,
                "lng": 27.342,
                "canonical_categories": ["archaeological_site", "ancient_city"],
                "wikidata_id": "Q43332",
            },
            "scores": {
                "total": 0.637,
                "geo": 0.194,
                "name": 1.0,
                "category": 1.0,
                "distance_m": 207.8,
            },
            "blocking": {"geohash": "swg69d4", "precision": 7},
        }
        user_prompt = build_user_prompt(payload)
        parsed_user = json.loads(user_prompt)  # JSON validity
        assert "candidate_A" in parsed_user and "candidate_B" in parsed_user
        assert parsed_user["candidate_A"]["source"] == "osm"
        assert parsed_user["candidate_B"]["wikidata_id"] == "Q43332"
        assert parsed_user["dedup_signals"]["score_total"] == 0.637
        step(f"user prompt PRD §9.4 formatında (len={len(user_prompt)})")

        # hash_prompt deterministic
        h1 = hash_prompt(SYSTEM_PROMPT, user_prompt)
        h2 = hash_prompt(SYSTEM_PROMPT, user_prompt)
        assert h1 == h2 and len(h1) == 64
        step(f"hash_prompt deterministik (sha256={h1[:12]}…)")

        # MAX_FIELD_LENGTH truncation
        long_payload = {
            "candidate_a": {"source": "osm", "name_tr": "x" * (MAX_FIELD_LENGTH + 500), "lat": 38.0, "lng": 27.0},
            "candidate_b": {"source": "wikidata", "name_tr": "Efes", "lat": 38.0, "lng": 27.0},
        }
        truncated = build_user_prompt(long_payload)
        assert len(truncated) < len(user_prompt) + MAX_FIELD_LENGTH * 2  # sınırlı şişti
        step(f"prompt-injection koruması: uzun alan {MAX_FIELD_LENGTH} karaktere kesildi")

        # parse_decision — PRD §9.4 schema validation
        merge_resp = {
            "decision": "merge",
            "confidence": 0.92,
            "canonical": {
                "name_tr": "Efes",
                "name_en": "Ephesus",
                "lat": 37.9395,
                "lng": 27.341,
                "primary_source_per_field": {
                    "isim": "wikidata",
                    "koordinat": "osm",
                    "kategori": "osm",
                },
            },
            "reasoning": "Aynı UNESCO sit alanı; isim ve koordinat uyumlu.",
        }
        pd: ParsedDecision = parse_decision(merge_resp)
        assert pd.decision.value == "merge"
        assert abs(pd.confidence - 0.92) < 1e-9
        assert pd.canonical["name_tr"] == "Efes"
        assert pd.primary_source_per_field["isim"] == "wikidata"
        step(f"parse_decision merge OK (c={pd.confidence}, decision={pd.decision.value})")

        # parse_decision split
        split_resp = {
            "decision": "split",
            "confidence": 0.88,
            "canonical": None,
            "reasoning": "Farklı kapı / yapı; ayrı yayınlanmalı.",
        }
        pd2 = parse_decision(split_resp)
        assert pd2.decision.value == "split" and pd2.canonical is None
        step("parse_decision split OK")

        # parse_decision reject
        reject_resp = {"decision": "reject", "confidence": 0.7, "canonical": None, "reasoning": "Eksik veri."}
        pd3 = parse_decision(reject_resp)
        assert pd3.decision.value == "reject"
        step("parse_decision reject OK")

        # parse_decision invalid → ValueError
        try:
            parse_decision({"decision": "foo", "confidence": 0.9})
        except ValueError:
            step("parse_decision PRD §9.4 şema ihlali → ValueError (beklenen)")
        else:
            raise AssertionError("Geçersiz decision için ValueError beklenir")

        try:
            parse_decision({"decision": "merge", "confidence": 1.5, "canonical": {}})
        except ValueError:
            step("parse_decision confidence > 1.0 → ValueError (beklenen)")
        else:
            raise AssertionError("Aralık dışı confidence için ValueError beklenir")

        try:
            parse_decision({"decision": "merge", "confidence": 0.9, "canonical": None})
        except ValueError:
            step("parse_decision merge'de canonical None → ValueError (beklenen)")
        else:
            raise AssertionError("merge'de canonical zorunlu, ValueError beklenir")

        # Settings — AI ayarları default'larını sağladığını doğrula
        from app.core.config import settings
        assert settings.AI_RATE_LIMIT_SEC == 4.5
        assert settings.AI_DAILY_QUOTA == 1400
        assert settings.AI_RATE_LIMIT_BACKOFF_SEC == 60.0
        assert settings.AI_CONFIDENCE_THRESHOLD == 0.85
        assert settings.AI_MAX_RETRY_COUNT == 3
        assert settings.GEMINI_MODEL == "gemini-2.0-flash"
        step(
            f"settings AI ayarları PRD §9.3 ile uyumlu "
            f"(rate={settings.AI_RATE_LIMIT_SEC}s, conf={settings.AI_CONFIDENCE_THRESHOLD}, "
            f"max_retry={settings.AI_MAX_RETRY_COUNT})"
        )

        out.append("")
        out.append("=" * 60)
        out.append("AI KARAR KATMANI SMOKE OK")
        out.append("=" * 60)
        log_path.write_text("\n".join(out), encoding="utf-8")
        print("\n".join(out))
        return 0

    except Exception as exc:  # noqa: BLE001
        out.append("")
        out.append("[FAIL] " + str(exc))
        out.append(traceback.format_exc())
        log_path.write_text("\n".join(out), encoding="utf-8")
        print("\n".join(out))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
