"""
Auth Endpoint'leri
==================
PRD §12 — ``/api/v1/auth/*`` ve ``/api/v1/me``.

Rate Limiting (PRD §12.1)::

    auth.register, auth.login, auth.refresh, auth.logout  → 300 req/dk
    me                                                    → 300 req/dk

Auth uçları kullanıcı kimliği henüz oluşmadığında IP bazlı çalışır;
``rate_limit`` dependency otomatik olarak ``X-Forwarded-For`` veya
``request.client.host`` üzerinden anahtarlar.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
)
from app.services import auth_service

AUTH_LIMIT = settings.RATE_LIMIT_AUTH_PER_MIN

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni kullanıcı kaydı (18+ + KVKK)",
    description=(
        "PRD §17.3 / D3: 18 yaş kontrolü hem uygulama (Pydantic) hem de DB "
        "(CHECK constraint) seviyesinde yapılır. KVKK açık rıza zorunludur."
    ),
    dependencies=[Depends(rate_limit("auth.register", limit=AUTH_LIMIT))],
)
def register(
    payload: RegisterRequest,
    db: DbSession,
    request: Request,
) -> TokenPair:
    _, tokens = auth_service.register_user(db, payload, request=request)
    return tokens


@router.post(
    "/login",
    response_model=TokenPair,
    summary="E-posta veya kullanıcı adı ile giriş",
    dependencies=[Depends(rate_limit("auth.login", limit=AUTH_LIMIT))],
)
def login(
    payload: LoginRequest,
    db: DbSession,
    request: Request,
) -> TokenPair:
    _, tokens = auth_service.login_user(db, payload, request=request)
    return tokens


@router.post(
    "/refresh",
    response_model=TokenPair,
    summary="Rotating refresh token (PRD §17.2)",
    description=(
        "Verilen refresh token revoke edilip yeni access+refresh çifti "
        "üretilir. Aynı token ikinci kez gelirse reuse detection devreye "
        "girer ve kullanıcının tüm aktif token'ları kapatılır."
    ),
    dependencies=[Depends(rate_limit("auth.refresh", limit=AUTH_LIMIT))],
)
def refresh(
    payload: RefreshRequest,
    db: DbSession,
    request: Request,
) -> TokenPair:
    return auth_service.refresh_tokens(db, payload.refresh_token, request=request)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Refresh token'ı revoke et",
    dependencies=[Depends(rate_limit("auth.logout", limit=AUTH_LIMIT))],
    response_class=Response,
)
def logout(payload: LogoutRequest, db: DbSession) -> Response:
    auth_service.logout(db, payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
