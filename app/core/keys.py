"""
RSA Anahtar Yönetimi (JWT RS256)
================================
PRD §17.2 — JWT için **RS256 (asimetrik)** zorunlu.

Anahtar çifti ``secrets/jwt/`` altında PEM olarak tutulur. Dizin yoksa
otomatik olarak oluşturulur ve **2048-bit RSA** anahtar çifti üretilir.

Geliştirme ortamında bu yeterlidir; üretim ortamında anahtar dosyaları
gizli yönetilen bir konuma (Vault / KMS / k8s Secret) bağlanmalıdır.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

logger = logging.getLogger(__name__)

_KEYS_DIR = Path(__file__).resolve().parents[2] / "secrets" / "jwt"
_PRIVATE_KEY_PATH = _KEYS_DIR / "private.pem"
_PUBLIC_KEY_PATH = _KEYS_DIR / "public.pem"

_lock = threading.Lock()
_cache: dict[str, str] = {}


def _generate_keypair() -> None:
    """2048-bit RSA anahtar çifti üret ve PEM olarak diske yaz."""
    _KEYS_DIR.mkdir(parents=True, exist_ok=True)

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    _PRIVATE_KEY_PATH.write_bytes(private_pem)
    _PUBLIC_KEY_PATH.write_bytes(public_pem)
    logger.warning(
        "JWT RS256 anahtar çifti üretildi: %s (geliştirme ortamı). "
        "Üretimde mutlaka KMS / Vault üzerinden sağlayın.",
        _KEYS_DIR,
    )


def _ensure_keys() -> None:
    """Anahtarlar yoksa üret. Thread-safe."""
    if _PRIVATE_KEY_PATH.exists() and _PUBLIC_KEY_PATH.exists():
        return
    with _lock:
        if _PRIVATE_KEY_PATH.exists() and _PUBLIC_KEY_PATH.exists():
            return
        _generate_keypair()


def get_private_key() -> str:
    """JWT imzalamak için kullanılan PEM formatındaki private key."""
    if "private" not in _cache:
        _ensure_keys()
        _cache["private"] = _PRIVATE_KEY_PATH.read_text(encoding="utf-8")
    return _cache["private"]


def get_public_key() -> str:
    """JWT doğrulamak için kullanılan PEM formatındaki public key."""
    if "public" not in _cache:
        _ensure_keys()
        _cache["public"] = _PUBLIC_KEY_PATH.read_text(encoding="utf-8")
    return _cache["public"]
