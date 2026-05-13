"""
HTTP Hata Modeli (RFC 7807 Problem Details)
===========================================
PRD §12.1 — "Hata Modeli: RFC 7807 Problem Details".

Tüm domain hataları :class:`ProblemDetailsError` üzerinden fırlatılır,
:func:`install_exception_handlers` ile :class:`fastapi.FastAPI` üzerine
bağlanarak istemciye `application/problem+json` döndürür.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

PROBLEM_CONTENT_TYPE = "application/problem+json"


class ProblemDetailsError(Exception):
    """RFC 7807 uyumlu domain hatası.

    Args:
        status: HTTP durum kodu (400-599).
        title: İnsan-okur kısa başlık.
        detail: Daha açıklayıcı metin.
        type_: URI referansı (varsayılan ``about:blank``).
        code: Uygulama içi sabit hata kodu (örn. ``auth.invalid_credentials``).
        extras: İsteğe bağlı ekstra alanlar.
    """

    def __init__(
        self,
        *,
        status: int,
        title: str,
        detail: str | None = None,
        type_: str = "about:blank",
        code: str | None = None,
        extras: dict[str, Any] | None = None,
    ) -> None:
        self.status = status
        self.title = title
        self.detail = detail
        self.type_ = type_
        self.code = code
        self.extras = extras or {}
        super().__init__(detail or title)

    def to_payload(self, *, instance: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "type": self.type_,
            "title": self.title,
            "status": self.status,
        }
        if self.detail is not None:
            payload["detail"] = self.detail
        if self.code is not None:
            payload["code"] = self.code
        if instance is not None:
            payload["instance"] = instance
        payload.update(self.extras)
        return payload


def _problem_response(
    request: Request,
    *,
    status: int,
    title: str,
    detail: str | None = None,
    code: str | None = None,
    extras: dict[str, Any] | None = None,
    type_: str = "about:blank",
) -> JSONResponse:
    payload = {
        "type": type_,
        "title": title,
        "status": status,
        "instance": str(request.url.path),
    }
    if detail is not None:
        payload["detail"] = detail
    if code is not None:
        payload["code"] = code
    if extras:
        payload.update(extras)
    return JSONResponse(
        status_code=status,
        content=payload,
        media_type=PROBLEM_CONTENT_TYPE,
    )


def install_exception_handlers(app: FastAPI) -> None:
    """FastAPI'ye RFC 7807 uyumlu handler'ları bağla."""

    @app.exception_handler(ProblemDetailsError)
    async def _problem_handler(request: Request, exc: ProblemDetailsError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=exc.to_payload(instance=str(request.url.path)),
            media_type=PROBLEM_CONTENT_TYPE,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, str) else None
        extras: dict[str, Any] | None = None
        if not isinstance(exc.detail, str) and exc.detail is not None:
            extras = {"detail_data": exc.detail}
        return _problem_response(
            request,
            status=exc.status_code,
            title=_default_title(exc.status_code),
            detail=detail,
            extras=extras,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # `exc.errors()` içinde JSON serileştirilemeyen tipler (ValueError,
        # bytes vb.) olabilir → jsonable_encoder ile temizle.
        return _problem_response(
            request,
            status=422,
            title="Validation Error",
            detail="Bir veya daha fazla alan doğrulamadan geçemedi.",
            code="validation.failed",
            extras={"errors": jsonable_encoder(exc.errors())},
        )


def _default_title(status_code: int) -> str:
    mapping = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        429: "Too Many Requests",
        500: "Internal Server Error",
    }
    return mapping.get(status_code, "Error")
