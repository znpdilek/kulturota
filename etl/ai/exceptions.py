"""
AI Karar Katmanı Hata Türleri
=============================
PRD §9.3 + §9.6 — rate-limit ve kota tükenmesi durumlarını davranışsal olarak
ayırt etmek için ayrı exception tipleri tutulur.
"""

from __future__ import annotations


class AIDecisionError(Exception):
    """AI karar katmanı için genel temel hata."""


class LLMResponseError(AIDecisionError):
    """LLM çağrısı başarısız veya yanıt parse edilemedi (HTTP 4xx/5xx, JSON hatası)."""


class RateLimitError(AIDecisionError):
    """HTTP 429 — anlık RPM/TPS sınırı; bir süre beklenip tekrar denenmelidir."""

    def __init__(
        self,
        message: str = "Rate limit aşıldı",
        *,
        retry_after_sec: float | None = None,
    ) -> None:
        super().__init__(message)
        self.retry_after_sec = retry_after_sec


class QuotaExhaustedError(AIDecisionError):
    """Günlük kota tükendi — sonraki güne ertelenmelidir (PRD §9.3 maliyet=0)."""


__all__ = [
    "AIDecisionError",
    "LLMResponseError",
    "QuotaExhaustedError",
    "RateLimitError",
]
