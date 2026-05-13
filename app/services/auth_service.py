"""
Auth Servisi
============
PRD §12.1 + §17.2 + §17.3.

Sorumluluklar:

    * Kullanıcı kaydı (18+ + KVKK + argon2id hash).
    * Login (e-posta veya kullanıcı adı + şifre).
    * Refresh token rotation + reuse detection.
    * Logout (refresh token revoke).

Tüm DB hataları sarılarak :class:`ProblemDetailsError` üretir; bu sayede
endpoint'ler ekstra try/except yazmak zorunda kalmaz.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import Request
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import TokenType, UserRole
from app.core.exceptions import ProblemDetailsError
from app.core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenPair

logger = logging.getLogger(__name__)

REVOKE_REASON_ROTATED = "rotated"
REVOKE_REASON_LOGOUT = "logout"
REVOKE_REASON_REUSE = "reuse_detected"


# --- Helpers ---------------------------------------------------------------
def _client_info(request: Request | None) -> tuple[str | None, str | None]:
    if request is None:
        return None, None
    ip = None
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip = fwd.split(",", 1)[0].strip()
    elif request.client:
        ip = request.client.host
    return ip, (request.headers.get("user-agent") or None)


def _mint_token_pair(
    db: Session,
    user: User,
    *,
    parent_jti: uuid.UUID | None = None,
    request: Request | None = None,
) -> TokenPair:
    """Access + Refresh çiftini üret ve refresh kaydını DB'ye yaz."""
    access, _access_jti, access_exp = create_access_token(
        subject=user.id, role=user.role
    )
    refresh, refresh_jti, refresh_exp = create_refresh_token(
        subject=user.id, role=user.role
    )

    ip, ua = _client_info(request)
    db.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            parent_jti=parent_jti,
            expires_at=refresh_exp,
            ip=ip,
            user_agent=ua,
        )
    )
    # ``flush`` ile aynı transaction'da görünür kıl; commit endpoint sahip.
    db.flush()

    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        access_token_expires_at=access_exp,
        refresh_token_expires_at=refresh_exp,
    )


# --- Public API ------------------------------------------------------------
def register_user(
    db: Session,
    payload: RegisterRequest,
    *,
    request: Request | None = None,
) -> tuple[User, TokenPair]:
    """Yeni kullanıcı oluştur ve ilk token çiftini ver.

    DB tarafında ``birth_date <= CURRENT_DATE - INTERVAL '18 years'`` CHECK
    constraint'i ikinci savunma hattıdır (PRD §17.3 / D3).
    """
    user = User(
        email=payload.email.lower(),
        username=payload.username,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name,
        birth_date=payload.birth_date,
        kvkk_consent_at=datetime.now(tz=timezone.utc),
        locale=payload.locale,
        role=UserRole.USER,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        msg = str(exc.orig).lower() if exc.orig else str(exc).lower()
        if "users_email" in msg or "ix_users_email" in msg:
            raise ProblemDetailsError(
                status=409,
                title="Conflict",
                detail="Bu e-posta adresi zaten kayıtlı.",
                code="auth.email_taken",
            ) from exc
        if "users_username" in msg or "ix_users_username" in msg:
            raise ProblemDetailsError(
                status=409,
                title="Conflict",
                detail="Bu kullanıcı adı zaten alınmış.",
                code="auth.username_taken",
            ) from exc
        if "adult_birth_date" in msg or "ck_users" in msg:
            raise ProblemDetailsError(
                status=422,
                title="Unprocessable Entity",
                detail="Yalnızca 18 yaş ve üzeri kayıt olabilir (PRD §17.3 / D3).",
                code="auth.underage",
            ) from exc
        logger.exception("kayıt sırasında beklenmeyen integrity hatası")
        raise ProblemDetailsError(
            status=500,
            title="Internal Server Error",
            detail="Kayıt başarısız.",
            code="auth.register_failed",
        ) from exc

    tokens = _mint_token_pair(db, user, request=request)
    user.last_login_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(user)
    return user, tokens


def login_user(
    db: Session,
    payload: LoginRequest,
    *,
    request: Request | None = None,
) -> tuple[User, TokenPair]:
    """E-posta veya username + şifre ile giriş."""
    identifier = payload.identifier.strip().lower()
    stmt = select(User).where(
        or_(User.email == identifier, User.username == identifier)
    )
    user = db.scalar(stmt)

    if user is None or not user.password_hash or not verify_password(
        payload.password, user.password_hash
    ):
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="E-posta/kullanıcı adı veya şifre hatalı.",
            code="auth.invalid_credentials",
        )

    if not user.is_active:
        raise ProblemDetailsError(
            status=403,
            title="Forbidden",
            detail="Hesabınız askıya alınmış.",
            code="auth.inactive",
        )

    tokens = _mint_token_pair(db, user, request=request)
    user.last_login_at = datetime.now(tz=timezone.utc)
    db.commit()
    return user, tokens


def refresh_tokens(
    db: Session,
    refresh_token: str,
    *,
    request: Request | None = None,
) -> TokenPair:
    """Rotating refresh token akışı (PRD §17.2).

    Akış:
        1. JWT'yi RS256 ile decode et + ``typ=refresh`` kontrolü.
        2. DB'deki kayıt durumunu doğrula.
        3. **Reuse detection**: kayıt ``used_at`` veya ``revoked_at``
           ile işaretliyse → kullanıcının tüm refresh token'larını revoke
           et ve hata fırlat.
        4. Eski token'ı ``used_at`` + ``revoked_at`` ile kapat; yeni
           çift üret ve ``parent_jti`` ile zincirle.
    """
    try:
        claims = decode_token(refresh_token, expected_type=TokenType.REFRESH)
    except TokenError as exc:
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail=str(exc),
            code="auth.invalid_refresh",
        ) from exc

    try:
        jti = uuid.UUID(claims["jti"])
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError) as exc:
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Refresh token claim'leri eksik veya geçersiz.",
            code="auth.invalid_refresh",
        ) from exc

    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    user = db.get(User, user_id)

    if record is None or user is None or record.user_id != user.id:
        # Hiç kayıt yoksa muhtemelen sahte → tüm token'ları revoke etme
        # (bilinen user_id varsa savunmacı önlem alalım).
        if user is not None:
            _revoke_all_for_user(db, user.id, reason=REVOKE_REASON_REUSE)
            db.commit()
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Refresh token kaydı bulunamadı.",
            code="auth.invalid_refresh",
        )

    now = datetime.now(tz=timezone.utc)
    if record.revoked_at or record.used_at:
        # Reuse → güvenlik ihlali şüphesi; tüm aktif token'ları kapat.
        logger.warning(
            "refresh token reuse detected user=%s jti=%s", user.id, jti
        )
        _revoke_all_for_user(db, user.id, reason=REVOKE_REASON_REUSE)
        db.commit()
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Refresh token zaten kullanılmış. Tüm oturumlar kapatıldı.",
            code="auth.refresh_reuse",
        )

    if record.expires_at <= now:
        raise ProblemDetailsError(
            status=401,
            title="Unauthorized",
            detail="Refresh token süresi dolmuş.",
            code="auth.expired_refresh",
        )

    if not user.is_active:
        raise ProblemDetailsError(
            status=403,
            title="Forbidden",
            detail="Hesabınız askıya alınmış.",
            code="auth.inactive",
        )

    record.used_at = now
    record.revoked_at = now
    record.revoked_reason = REVOKE_REASON_ROTATED

    tokens = _mint_token_pair(db, user, parent_jti=record.jti, request=request)
    db.commit()
    return tokens


def logout(
    db: Session,
    refresh_token: str,
) -> None:
    """Verilen refresh token'ı revoke et."""
    try:
        claims = decode_token(refresh_token, expected_type=TokenType.REFRESH)
        jti = uuid.UUID(claims["jti"])
    except (TokenError, KeyError, ValueError):
        # Sessizce başarılı dön — istemci böylece "logout" idempotent olur.
        return

    record = db.scalar(select(RefreshToken).where(RefreshToken.jti == jti))
    if record is None or record.revoked_at:
        return

    record.revoked_at = datetime.now(tz=timezone.utc)
    record.revoked_reason = REVOKE_REASON_LOGOUT
    db.commit()


def _revoke_all_for_user(db: Session, user_id: uuid.UUID, *, reason: str) -> None:
    """Kullanıcının tüm aktif refresh token'larını revoke et."""
    now = datetime.now(tz=timezone.utc)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now, revoked_reason=reason)
    )
