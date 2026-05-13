"""
Otonom AI Karar Katmanı (PRD §9)
================================
``ai_decision_queue`` tablosunda ``status='pending'`` olan şüpheli kayıtları
ücretsiz (free-tier) LLM API'sine gönderip karar uygulayan modüller burada
toplanır. Mentor direktifi (D6) gereği insan küratör yoktur.

Modüller
--------
* :mod:`etl.ai.exceptions` — Domaine özgü hata türleri.
* :mod:`etl.ai.prompts` — PRD §9.4 prompt tasarımı.
* :mod:`etl.ai.llm_client` — Gemini Flash REST çağrısı + rate-limit.
* :mod:`etl.ai.decision_applier` — ``places`` tablosuna merge/split/reject yazımı.
* :mod:`etl.ai.processor` — Kuyruk tüketici döngüsü.
"""

from etl.ai.processor import ProcessorReport, process_pending_queue

__all__ = ["ProcessorReport", "process_pending_queue"]
