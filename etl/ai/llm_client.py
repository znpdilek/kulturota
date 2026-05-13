"""
Gemini Flash REST İstemcisi
===========================
PRD §9.2 + §9.3 — Google AI Studio (Gemini Flash) free-tier REST entegrasyonu.

Neden ``httpx`` ile düz REST?
    * Resmi ``google-generativeai`` SDK'sı SDK versiyonlarına bağlı; CI/CD
      tarafında bağımlılık karmaşası yaratabilir.
    * REST API yüzeyi sade ve PRD §9.3'teki yavaşlatma/rate-limit semantiğini
      doğrudan kontrol etmeye uygun.
    * ``httpx`` zaten ``requirements.txt``'te.

Free-tier kotaları (PRD §9.2):
    * Gemini 2.0 Flash: 15 RPM, 1.500 req/gün, 1M token/gün.
    * Mentor direktifi (D6): SADECE ücretsiz tier; ücretli plana geçilmez.

Endpoint:
    ``POST {base}/models/{model}:generateContent?key={api_key}``

Yanıt formatı zorlanır:
    ``generationConfig.responseMimeType = "application/json"`` (Gemini 1.5+).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from etl.ai.exceptions import (
    LLMResponseError,
    QuotaExhaustedError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Yanıt tipi
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LLMResponse:
    """LLM çağrısının parse edilmiş çıktısı + audit alanları."""

    parsed: dict[str, Any]  # PRD §9.4 OUTPUT_SCHEMA — Python dict
    raw_response: dict[str, Any]  # API'den dönen ham JSON (audit için)
    model_version: str  # "gemini-2.0-flash" vb.
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    latency_ms: int


# ---------------------------------------------------------------------------
# Gemini Client
# ---------------------------------------------------------------------------
class GeminiFlashClient:
    """
    Free-tier Gemini Flash REST çağrısı yapan basit, retry-aware istemci.

    Sadece ``generate_decision`` metodu kullanılır. Üst katman:
        * Çağrı öncesi cache kontrolü (Redis) yapar.
        * 429 / 5xx hatalarını ``RateLimitError`` veya ``LLMResponseError`` olarak
          yakalayıp PRD §9.3'teki kurallara göre bekler.
        * Her başarılı çağrıdan sonra ``time.sleep(RATE_LIMIT_SEC)`` uygular.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        timeout_sec: float | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        self.base_url = (base_url or settings.GEMINI_API_BASE_URL).rstrip("/")
        self.timeout_sec = timeout_sec or settings.AI_HTTP_TIMEOUT_SEC

        if not self.api_key:
            raise RuntimeError(
                "GEMINI_API_KEY tanımlı değil. .env dosyasına ekleyin "
                "(https://aistudio.google.com/app/apikey)."
            )

        # httpx.Client tekrar kullanım için sınıf ömrü boyunca açık tutulur.
        self._client = httpx.Client(timeout=self.timeout_sec)

    # ------------------------------------------------------------------
    # Bağlantı yönetimi
    # ------------------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GeminiFlashClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Çekirdek çağrı
    # ------------------------------------------------------------------
    def generate_decision(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        max_output_tokens: int = 1024,
    ) -> LLMResponse:
        """
        Verilen prompt çifti için Gemini Flash'a tek çağrı yap; PRD §9.4
        OUTPUT_SCHEMA'sına uygun JSON dict döndür.

        Raises
        ------
        RateLimitError
            HTTP 429 — anlık RPM/TPS sınırı (üst katman bekleyip retry edebilir).
        QuotaExhaustedError
            Günlük kota tükendi (ertesi güne ertelenmelidir).
        LLMResponseError
            Diğer tüm hata türleri (parse hatası, 5xx, geçersiz şema).
        """
        url = f"{self.base_url}/models/{self.model}:generateContent"
        params = {"key": self.api_key}
        body = self._build_request_body(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

        started = time.perf_counter()
        try:
            response = self._client.post(url, params=params, json=body)
        except httpx.HTTPError as exc:
            raise LLMResponseError(f"HTTP transport hatası: {exc}") from exc

        latency_ms = int((time.perf_counter() - started) * 1000)
        self._raise_for_status(response)

        try:
            raw = response.json()
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                f"API yanıtı JSON değil: {exc}; body={response.text[:200]!r}"
            ) from exc

        parsed = self._extract_decision_json(raw)
        usage = raw.get("usageMetadata") or {}

        return LLMResponse(
            parsed=parsed,
            raw_response=raw,
            model_version=self.model,
            prompt_tokens=usage.get("promptTokenCount"),
            completion_tokens=usage.get("candidatesTokenCount"),
            total_tokens=usage.get("totalTokenCount"),
            latency_ms=latency_ms,
        )

    # ------------------------------------------------------------------
    # Yardımcılar
    # ------------------------------------------------------------------
    @staticmethod
    def _build_request_body(
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_output_tokens: int,
    ) -> dict[str, Any]:
        """
        Gemini ``generateContent`` request body'sini kur.

        ``responseMimeType=application/json`` PRD §9.4 — modeli JSON dönüşüne
        zorlar (Gemini 1.5+).
        """
        return {
            "systemInstruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": user_prompt}],
                }
            ],
            "generationConfig": {
                "temperature": temperature,
                "topP": 0.95,
                "maxOutputTokens": max_output_tokens,
                "responseMimeType": "application/json",
            },
            "safetySettings": [
                # PRD §9.4'te kullanılan kayıtlar (kültürel miras adları, koordinatlar)
                # zararsızdır; varsayılan filtreler false-positive üretmesin diye
                # eşik yumuşatılır. Kullanıcı içeriği değil, kaynak veri verisi.
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_ONLY_HIGH"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_ONLY_HIGH"},
            ],
        }

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        """
        HTTP durum koduna göre uygun exception fırlat.

        * 429 → ``RateLimitError`` (kuyruk üst katmanı bekleyip yeniden dener).
        * 403/quota → ``QuotaExhaustedError`` (gün sonu kotası bitti, ertele).
        * Diğer hatalar → ``LLMResponseError``.
        """
        status = response.status_code
        if 200 <= status < 300:
            return

        # Yanıt gövdesinden hata detaylarını oku (Gemini standart formatı).
        body_text = response.text or ""
        error_payload: dict[str, Any] = {}
        try:
            error_payload = response.json()
        except json.JSONDecodeError:
            pass

        err_obj = error_payload.get("error") if isinstance(error_payload, dict) else None
        message = (err_obj or {}).get("message") or body_text[:300]
        reason = (err_obj or {}).get("status") or ""

        if status == 429:
            # Retry-After header'ı geliyorsa onu kullan.
            retry_after = response.headers.get("retry-after")
            try:
                retry_after_sec = float(retry_after) if retry_after else None
            except ValueError:
                retry_after_sec = None
            raise RateLimitError(
                f"Gemini 429: {message}",
                retry_after_sec=retry_after_sec,
            )

        # 403 + RESOURCE_EXHAUSTED veya benzeri günlük kota işareti.
        lowered = (message + " " + reason).lower()
        if status == 403 and "quota" in lowered:
            raise QuotaExhaustedError(f"Gemini kota tükendi: {message}")
        if "resource_exhausted" in lowered or "quota exceeded" in lowered:
            raise QuotaExhaustedError(f"Gemini kota tükendi: {message}")

        raise LLMResponseError(f"Gemini HTTP {status}: {message}")

    @staticmethod
    def _extract_decision_json(raw_response: dict[str, Any]) -> dict[str, Any]:
        """
        ``candidates[0].content.parts[0].text`` → parse → dict.

        PRD §9.4 OUTPUT_SCHEMA üst seviye doğrulaması burada yapılır; alan-bazlı
        validasyon ``decision_applier.parse_decision()`` içinde sürdürülür.
        """
        candidates = raw_response.get("candidates") or []
        if not candidates:
            # Modelin ürettiği "prompt block" hatası — güvenlik filtresi vb.
            block_reason = (raw_response.get("promptFeedback") or {}).get("blockReason")
            raise LLMResponseError(
                f"Gemini boş 'candidates' döndü (blockReason={block_reason!r})"
            )

        parts = ((candidates[0].get("content") or {}).get("parts")) or []
        text_chunks = [p.get("text", "") for p in parts if isinstance(p, dict)]
        text = "".join(text_chunks).strip()

        if not text:
            raise LLMResponseError("Gemini yanıtı boş metin döndürdü")

        # Bazı modeller markdown code fence ekleyebiliyor — temizle.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(
                f"LLM yanıtı geçerli JSON değil: {exc}; text={text[:300]!r}"
            ) from exc

        if not isinstance(parsed, dict):
            raise LLMResponseError(
                f"LLM yanıtı JSON object değil, type={type(parsed).__name__}"
            )
        return parsed


__all__ = ["GeminiFlashClient", "LLMResponse"]
