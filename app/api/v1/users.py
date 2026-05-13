"""
Users Endpoint'leri
===================
PRD §12.2 + §17.3 — Adım 5 (Profil + KVKK / GDPR Uyumu).

Bu modülde toplanan uçlar
-------------------------
* ``GET    /v1/me``                       — geriye dönük uyum için korunur.
* ``GET    /v1/users/me``                 — profil okuma (Adım 4 ile aynı).
* ``PUT    /v1/users/me``                 — profil güncelleme (Adım 5 yeni).
* ``GET    /v1/users/me/export-data``     — KVKK veri dışa aktarma (Adım 5).
* ``DELETE /v1/users/me``                 — GDPR/KVKK uyumlu kalıcı silme (Adım 5).

Tüm uçlar :class:`app.api.deps.CurrentUser` ile ``Authorization: Bearer
<jwt>`` zorunluluğu altındadır. Profil ve KVKK uçları **300 req/dk** auth
rate limit'i altında çalışır (PRD §12.1).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.core.exceptions import PROBLEM_CONTENT_TYPE
from app.schemas.user import (
    UserDataExport,
    UserDeleteRequest,
    UserDeleteResponse,
    UserMe,
    UserUpdate,
)
from app.services import user_service

AUTH_LIMIT = settings.RATE_LIMIT_AUTH_PER_MIN


def _request_meta(request: Request) -> tuple[str | None, str | None]:
    """İstemci IP + UA çıkar (audit log için)."""
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        ip: str | None = fwd.split(",", 1)[0].strip()
    elif request.client is not None:
        ip = request.client.host
    else:
        ip = None
    return ip, request.headers.get("user-agent")


# --- Eski "/me" rotası (Adım 4 — backward compat) --------------------------
legacy_router = APIRouter(tags=["users"])


@legacy_router.get(
    "/me",
    response_model=UserMe,
    summary="Mevcut kullanıcının profili (legacy /me)",
    description=(
        "Geriye dönük uyum için korunur. PRD §12 sözleşmesi gereği yeni "
        "istemciler ``GET /v1/users/me`` ucunu kullanmalıdır."
    ),
    dependencies=[Depends(rate_limit("me", limit=AUTH_LIMIT))],
)
def get_me_legacy(current_user: CurrentUser) -> UserMe:
    return UserMe.model_validate(current_user)


# --- Yeni "/users/me" ailesi (Adım 5) --------------------------------------
router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserMe,
    summary="Mevcut kullanıcının profili",
    dependencies=[Depends(rate_limit("users.me.get", limit=AUTH_LIMIT))],
)
def get_me(current_user: CurrentUser) -> UserMe:
    return UserMe.model_validate(current_user)


@router.put(
    "/me",
    response_model=UserMe,
    summary="Profil bilgilerini güncelle",
    description=(
        "PRD §13.1 → `/ayarlar`. Hassas alanlar (e-posta, şifre, doğum tarihi, "
        "KVKK rıza, rol) bu uçtan **değiştirilemez**; her biri için ayrılmış "
        "akışlar gerekir.\n\n"
        "Her değişiklik **audit_log** tablosuna `profile.update` olarak yazılır "
        "(PRD §10.2 + §17.3 KVKK denetlenebilirlik)."
    ),
    dependencies=[Depends(rate_limit("users.me.put", limit=AUTH_LIMIT))],
)
def update_me(
    payload: UserUpdate,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> UserMe:
    ip, ua = _request_meta(request)
    user = user_service.update_profile(
        db,
        current_user,
        payload,
        actor_ip=ip,
        actor_user_agent=ua,
    )
    return UserMe.model_validate(user)


@router.get(
    "/me/export-data",
    response_model=UserDataExport,
    summary="KVKK / GDPR veri dışa aktarma",
    description=(
        "PRD §17.3 — \"Veri dışa aktarma → JSON paketi\".\n\n"
        "Kullanıcının sistemdeki tüm kişisel verisi tek bir JSON paketi olarak "
        "döner: profil, KVKK rıza zaman damgası, oturum metadata'sı, oluşturduğu "
        "rotalar/rota durakları, yüklediği fotoğraflar, yazdığı yorumlar, "
        "favoriler, takip ilişkileri, rota beğeni/yorumları, ilettiği şikayetler "
        "ve actor olduğu denetim kayıtları.\n\n"
        "Halka açık kültürel miras verileri (`places`, `opening_hours`, `tags`) "
        "kişisel veri kapsamında değildir; pakete dahil edilmez (PRD §20).\n\n"
        "İstemci `attachment; filename=...` content-disposition başlığıyla doğrudan "
        "indirme aksiyonu tetikleyebilir."
    ),
    dependencies=[Depends(rate_limit("users.me.export", limit=AUTH_LIMIT))],
)
def export_data(
    current_user: CurrentUser,
    db: DbSession,
) -> JSONResponse:
    export = user_service.export_user_data(db, current_user)
    filename = f"kulturrota-export-{current_user.username}-{export.metadata.generated_at.strftime('%Y%m%d-%H%M%SZ')}.json"
    return JSONResponse(
        content=export.model_dump(mode="json"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            "X-KVKK-Schema-Version": user_service.EXPORT_SCHEMA_VERSION,
        },
    )


@router.delete(
    "/me",
    response_model=UserDeleteResponse,
    summary="Hesabı ve tüm kişisel izleri kalıcı olarak sil",
    description=(
        "PRD §17.3 — \"Hak Talepleri: silme\". GDPR Art.17 / KVKK Md.7 uyumlu.\n\n"
        "İşlem:\n"
        "1. Onay metni (`HESABIMI KALICI OLARAK SİL`) doğrulanır.\n"
        "2. Silinecek ilişkili kayıt sayıları derlenir (routes, photos, "
        "reviews, favorites, follows, route_likes, route_comments, reports, "
        "refresh_tokens).\n"
        "3. **audit_log**'a `user.delete` olarak işlenir; cascade sonrası "
        "`actor_id NULL` olarak yasal saklamada kalır (5 yıl — PRD §17.3).\n"
        "4. `users` satırı silinir; FK cascade'leri tüm kişisel izleri "
        "temizler.\n\n"
        "**Geri alınamaz.** Silmeden önce `GET /v1/users/me/export-data` ile "
        "verinizi indirmeniz önerilir."
    ),
    dependencies=[Depends(rate_limit("users.me.delete", limit=AUTH_LIMIT))],
    responses={
        400: {"content": {PROBLEM_CONTENT_TYPE: {}}},
        409: {"content": {PROBLEM_CONTENT_TYPE: {}}},
    },
)
def delete_me(
    payload: UserDeleteRequest,
    current_user: CurrentUser,
    db: DbSession,
    request: Request,
) -> UserDeleteResponse:
    ip, ua = _request_meta(request)
    result = user_service.delete_user_account(
        db,
        current_user,
        reason=payload.reason,
        actor_ip=ip,
        actor_user_agent=ua,
    )
    return UserDeleteResponse(**result)


__all__ = ["router", "legacy_router"]
