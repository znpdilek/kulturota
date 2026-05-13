"""
FastAPI Dependency'leri
=======================
PRD §12.1 + §17.2 — DB session, current user, role guard.

Bearer şeması üretim Swagger'da "Authorize" butonunu açar. ``auto_error=False``
seçtik çünkü RFC 7807 uyumlu hata mesajını kendimiz üretmek istiyoruz.
"""

from __future__ import annotations

import uuid
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.enums import TokenType, UserRole
from app.core.exceptions import ProblemDetailsError
from app.core.security import TokenError, decode_token
from app.db.session import SessionLocal
from app.models.user import User

_bearer = HTTPBearer(
    bearerFormat="JWT",
    scheme_name="BearerJWT",
    description="OAuth 2.0 + JWT (RS256). PRD §12.1 / §17.2.",
    auto_error=False,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI Depends için DB session sağlayıcı (commit endpoint sahibinde)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: DbSession,
) -> User:
    """Authorization header'dan access token'ı doğrula ve User döndür."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Bearer token gerekli.",
            code="auth.missing_token",
        )

    try:
        claims = decode_token(credentials.credentials, expected_type=TokenType.ACCESS)
    except TokenError as exc:
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail=str(exc),
            code="auth.invalid_token",
        ) from exc

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Token claim'i geçersiz.",
            code="auth.invalid_token",
        ) from exc

    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Kullanıcı bulunamadı veya aktif değil.",
            code="auth.user_not_found",
        )

    # Rate limiter `user_id` görsün diye state'e yaz.
    request.state.user_id = str(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    """Sadece ``UserRole.ADMIN`` rolüne izin verir."""
    if user.role != UserRole.ADMIN:
        raise ProblemDetailsError(
            status=403,
            title="Forbidden",
            detail="Bu kaynak yalnızca admin rolündeki kullanıcılara açıktır.",
            code="auth.forbidden",
        )
    return user


AdminUser = Annotated[User, Depends(require_admin)]
