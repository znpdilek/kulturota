"""
Silver — String Temizleme Yardımcıları
======================================
PRD §8.4: "Unicode normalizasyonu (NFC), Türkçe lower-case (``tr_TR.UTF8``),
HTML entity decode."

Bu modülün tüm fonksiyonları **saf** (pure) — DB veya ağ kullanmaz.
"""

from __future__ import annotations

import html
import re
import unicodedata

# Türkçe upper → lower haritası.  ``str.lower`` C locale'da
# "İ" → "i̇" (i + combining dot) gibi yan etkilere neden olur; bunu engeller.
_TR_LOWER_MAP = str.maketrans(
    {
        "İ": "i",
        "I": "ı",
        "Ş": "ş",
        "Ğ": "ğ",
        "Ü": "ü",
        "Ö": "ö",
        "Ç": "ç",
    }
)

# Birden fazla beyaz boşluğu tek boşluğa indirir.
_WS_RE = re.compile(r"\s+")

# Türkçe karakter setini ASCII'ye eşleyen taksonomi yardımcısı.
_ASCII_FOLD = str.maketrans(
    {
        "ı": "i", "İ": "i", "ş": "s", "Ş": "s",
        "ğ": "g", "Ğ": "g", "ü": "u", "Ü": "u",
        "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    }
)


def normalize_text(value: str | None) -> str | None:
    """
    String'i Silver standardına çek:
        1. ``None`` ya da bare-boş ise ``None``.
        2. HTML entity decode.
        3. NFC unicode normalize.
        4. Çoklu beyaz boşluk → tek boşluk; trim.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if not value:
        return None
    text = html.unescape(value)
    text = unicodedata.normalize("NFC", text)
    text = _WS_RE.sub(" ", text).strip()
    return text or None


def tr_casefold(value: str) -> str:
    """Türkçe-aware lower-case (``İ→i``, ``I→ı``)."""
    return value.translate(_TR_LOWER_MAP).lower()


def ascii_fold(value: str) -> str:
    """Türkçe karakterleri ASCII'ye katla (taksonomi anahtarları için)."""
    return tr_casefold(value).translate(_ASCII_FOLD)


def normalize_for_match(value: str | None) -> str:
    """
    Token-set ratio karşılaştırması öncesi standart hazırlık (PRD §8.5).

    * NFC + Türkçe casefold
    * Noktalama → boşluk
    * Tekrar eden boşlukları sıkıştır
    """
    if not value:
        return ""
    text = normalize_text(value) or ""
    text = tr_casefold(text)
    text = re.sub(r"[^\w\s]", " ", text, flags=re.UNICODE)
    text = _WS_RE.sub(" ", text).strip()
    return text


__all__ = [
    "ascii_fold",
    "normalize_for_match",
    "normalize_text",
    "tr_casefold",
]
