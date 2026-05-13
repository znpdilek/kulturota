"""
Güvenlik Yardımcıları
=====================
PRD §17.2 — argon2id şifre hashleme + RS256 JWT.

Bu modül **iş kuralları içermez**; sadece düşük seviyeli kriptografik
işlemleri kapsar. Service katmanı (`app.services.auth_service`) bu
fonksiyonlar üzerinden iş akışını kurar.

Notlar
------
* ``passlib[argon2]`` kullanılır → argon2id varsayılan.
* ``python-jose`` ``jwt`` API'si üzerinden RS256 imzalama/doğrulama yapılır.
* Token claim'leri: ``sub`` (user_id), ``role``, ``typ`` (access|refresh),
  ``jti`` (UUID), ``iat``, ``exp``, ``iss``, ``aud``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.enums import TokenType, UserRole
from app.core.keys import get_private_key, get_public_key


class TokenError(Exception):
    """JWT decode / validation hatası."""


# argon2id (PRD §17.2). passlib uygulamayı otomatik upgrade ile yönetir.
_pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
)


# --- Password ---------------------------------------------------------------
def hash_password(password: str) -> str:
    """Düz şifreyi argon2id ile hash'le."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Şifre + hash karşılaştır. Yanlış durumda ``False`` döner."""
    try:
        return _pwd_context.verify(password, password_hash)
    except Exception:  # noqa: BLE001 — argon2 farklı hash şemasında patlayabilir
        return False


# --- JWT --------------------------------------------------------------------
def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _build_token(
    *,
    subject: uuid.UUID | str,
    role: UserRole,
    token_type: TokenType,
    expires_delta: timedelta,
    jti: uuid.UUID | None = None,
) -> tuple[str, uuid.UUID, datetime]:
    """RS256 ile imzalanmış JWT üret. ``(token, jti, exp)`` döndürür."""
    issued_at = _now()
    expires_at = issued_at + expires_delta
    token_jti = jti or uuid.uuid4()

    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role.value,
        "typ": token_type.value,
        "jti": str(token_jti),
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
    }

    token = jwt.encode(
        payload,
        get_private_key(),
        algorithm=settings.JWT_ALGORITHM,
    )
    return token, token_jti, expires_at


def create_access_token(
    *, subject: uuid.UUID | str, role: UserRole
) -> tuple[str, uuid.UUID, datetime]:
    """Kısa ömürlü access token (PRD §17.2 — 15 dk)."""
    return _build_token(
        subject=subject,
        role=role,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(
    *,
    subject: uuid.UUID | str,
    role: UserRole,
    jti: uuid.UUID | None = None,
) -> tuple[str, uuid.UUID, datetime]:
    """Rotating refresh token (PRD §17.2 — 30 gün)."""
    return _build_token(
        subject=subject,
        role=role,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        jti=jti,
    )


def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """JWT'yi RS256 + audience + issuer doğrulamasıyla parse et.

    Raises:
        TokenError: imza, süre veya ``typ`` uyumsuz olduğunda.
    """
    try:
        payload = jwt.decode(
            token,
            get_public_key(),
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
        )
    except JWTError as exc:
        raise TokenError(f"Geçersiz veya süresi dolmuş token: {exc}") from exc

    typ = payload.get("typ")
    if typ != expected_type.value:
        raise TokenError(
            f"Beklenen token tipi {expected_type.value!r}, gelen {typ!r}."
        )
    return payload
