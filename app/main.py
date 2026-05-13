"""
FastAPI Uygulama Giriş Noktası
==============================
PRD §12 / Adım 4 — Auth + temel Place uçları aktive edildi.

Router'lar :mod:`app.api.v1` altında toplanır ve ``/api/v1/...`` prefix'iyle
bağlanır (PRD §12.1). Tüm hatalar RFC 7807 Problem Details olarak döner
(bkz. :mod:`app.core.exceptions`).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.exceptions import install_exception_handlers


def create_app() -> FastAPI:
    """Uygulama factory'si."""
    application = FastAPI(
        title=settings.PROJECT_NAME,
        version="0.2.0",
        description=(
            "Türkiye Kültürel Miras Keşif ve Sosyal Gezi Platformu — "
            "Backend API (PRD v2.0).\n\n"
            "**Adım 4** — OAuth 2.0 + JWT (RS256) Auth + temel Place uçları.\n\n"
            "Yetkilendirme: `Authorize` butonundan **Bearer JWT** access token "
            "kullanın. Token'ı `/v1/auth/login` veya `/v1/auth/register` "
            "uçlarından alabilirsiniz."
        ),
        debug=settings.DEBUG,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    install_exception_handlers(application)
    application.include_router(api_router, prefix="/api")

    @application.get("/health", tags=["meta"])
    async def health() -> dict[str, str]:
        """Konteyner orchestrator için minimal sağlık kontrolü."""
        return {"status": "ok", "service": settings.PROJECT_NAME}

    return application


app = create_app()
