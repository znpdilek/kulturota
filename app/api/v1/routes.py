"""
Routes Endpoint'leri (Adım 7 — Rota Yönetimi / Core MVP)
========================================================
PRD §12.2 — ``/v1/routes`` + ``/v1/routes/{id}/stops``.

Endpoint özeti
--------------
========================  =================================================
``POST   /v1/routes``     Yeni rota oluştur (sahip = current user).
``GET    /v1/routes``     Kullanıcının kendi rotalarını listele.
``GET    /v1/routes/{id}`` Detay + sıralı stop listesi (sahip veya public).
``PUT    /v1/routes/{id}`` Rotayı güncelle (sadece sahip).
``DELETE /v1/routes/{id}`` Rotayı sil (cascade ile stop'lar da gider).

``GET    /v1/routes/{id}/stops``               Sıralı stop listesi.
``POST   /v1/routes/{id}/stops``               Rotaya mekan ekle.
``PATCH  /v1/routes/{id}/stops/{stop_id}``     Stop notunu/saatlerini güncelle.
``DELETE /v1/routes/{id}/stops/{stop_id}``     Stop'u rotadan çıkar.
========================  =================================================

Rate Limiting (PRD §12.1): tüm uçlar **300 req/dk** auth sınırında.

MVP sınırları (kullanıcı talebi)
--------------------------------
* Algoritmik rota optimizasyonu, otomatik AI rota önerisi ve iki mekan
  arası süre hesabı bu adımda **YOKTUR** (PRD §15.1 ileri adım).
* Sosyal etkileşim (beğeni, yorum) bu adımda **dokunulmaz**.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, DbSession
from app.api.rate_limit import rate_limit
from app.core.config import settings
from app.schemas.route import (
    RouteCreate,
    RouteDetail,
    RouteListResponse,
    RouteStopCreate,
    RouteStopListResponse,
    RouteStopUpdate,
    RouteStopWithPlace,
    RouteSummary,
    RouteUpdate,
)
from app.services import route_service

AUTH_LIMIT = settings.RATE_LIMIT_AUTH_PER_MIN

router = APIRouter(prefix="/routes", tags=["routes"])

_LIMIT_DEFAULT = 20
_LIMIT_MAX = 100


# ===========================================================================
# Route CRUD
# ===========================================================================
@router.post(
    "",
    response_model=RouteSummary,
    status_code=status.HTTP_201_CREATED,
    summary="Yeni rota oluştur",
    description=(
        "PRD §10.2 + §12.2. Sahibi otomatik olarak istek sahibi kullanıcıdır. "
        "MVP'de ``est_duration_min`` ve ``total_distance_km`` rota motoru "
        "ileri adımda doldurulacaktır."
    ),
    dependencies=[Depends(rate_limit("routes.create", limit=AUTH_LIMIT))],
)
def create_route(
    payload: RouteCreate,
    user: CurrentUser,
    db: DbSession,
) -> RouteSummary:
    return route_service.create_route(db, user, payload)


@router.get(
    "",
    response_model=RouteListResponse,
    summary="Kullanıcının kendi rotalarını listele",
    description=(
        "Sadece çağrı yapan kullanıcının sahip olduğu rotalar döner. "
        "Public rotaların global listelenmesi (PRD §12.2 trending) sosyal "
        "ekran ile birlikte ileride eklenecektir."
    ),
    dependencies=[Depends(rate_limit("routes.list", limit=AUTH_LIMIT))],
)
def list_my_routes(
    user: CurrentUser,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=_LIMIT_MAX)] = _LIMIT_DEFAULT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RouteListResponse:
    return route_service.list_my_routes(db, user.id, limit=limit, offset=offset)


@router.get(
    "/{route_id}",
    response_model=RouteDetail,
    summary="Rota detayı + sıralı stop listesi",
    description=(
        "Rotanın sahibi her zaman görür; başka bir kullanıcı yalnızca "
        "``is_public=true`` rotaları görebilir. Yanıt ``stops`` alanı "
        "``order_index`` artan yönde sıralanır ve her stop için **mekan adı + "
        "koordinat** inline döner (PRD §12.2 sözleşmesi)."
    ),
    dependencies=[Depends(rate_limit("routes.detail", limit=AUTH_LIMIT))],
)
def get_route(
    route_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RouteDetail:
    return route_service.get_route_detail(db, route_id, viewer_id=user.id)


@router.put(
    "/{route_id}",
    response_model=RouteSummary,
    summary="Rota bilgilerini güncelle",
    description=(
        "PATCH semantiği: sadece gönderilen alanlar değiştirilir. Sahip "
        "değilseniz 404 alırsınız (PRD §17 bilgi sızıntısı önlemi)."
    ),
    dependencies=[Depends(rate_limit("routes.update", limit=AUTH_LIMIT))],
)
def update_route(
    route_id: uuid.UUID,
    payload: RouteUpdate,
    user: CurrentUser,
    db: DbSession,
) -> RouteSummary:
    return route_service.update_route(db, route_id, user, payload)


@router.delete(
    "/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Rotayı sil",
    description=(
        "Cascade ile ``route_stops``, ``route_likes`` ve ``route_comments`` "
        "kayıtları da temizlenir. ``places`` kamu verisidir ve etkilenmez."
    ),
    dependencies=[Depends(rate_limit("routes.delete", limit=AUTH_LIMIT))],
    response_class=Response,
)
def delete_route(
    route_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    route_service.delete_route(db, route_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ===========================================================================
# Route stops
# ===========================================================================
@router.get(
    "/{route_id}/stops",
    response_model=RouteStopListResponse,
    summary="Rotanın sıralı stop listesini getir",
    description=(
        "``order_index`` artan yönde sıralanmış stop'lar; her stop için "
        "mekanın temel bilgisi (isim + koordinat + slug + kategori + kapak) "
        "inline döner. Yetki kuralı detay ile aynıdır (sahip veya public)."
    ),
    dependencies=[Depends(rate_limit("routes.stops.list", limit=AUTH_LIMIT))],
)
def list_stops(
    route_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> RouteStopListResponse:
    return route_service.list_stops(db, route_id, viewer_id=user.id)


@router.post(
    "/{route_id}/stops",
    response_model=RouteStopWithPlace,
    status_code=status.HTTP_201_CREATED,
    summary="Rotaya mekan ekle (stop)",
    description=(
        "``order_index`` gönderilmezse stop listesinin sonuna eklenir "
        "(mevcut max + 1). Açıkça gönderilen sıralama mevcut bir stop ile "
        "çakışırsa 409 döner — farklı bir değer seçin veya alanı boş bırakın.\n\n"
        "**Sınırlar:** Tek rotaya en fazla 250 stop eklenebilir."
    ),
    dependencies=[Depends(rate_limit("routes.stops.add", limit=AUTH_LIMIT))],
)
def add_stop(
    route_id: uuid.UUID,
    payload: RouteStopCreate,
    user: CurrentUser,
    db: DbSession,
) -> RouteStopWithPlace:
    return route_service.add_stop(db, route_id, user, payload)


@router.patch(
    "/{route_id}/stops/{stop_id}",
    response_model=RouteStopWithPlace,
    summary="Stop notunu / planlı zamanını güncelle",
    description=(
        "Yalnızca ``notes``, ``planned_arrival`` ve ``planned_duration_min`` "
        "alanları değiştirilebilir. Sıralama değişikliği bu uçtan "
        "yapılmaz; algoritmik yeniden sıralama PRD §15.1 rota motoruna "
        "bırakılmıştır."
    ),
    dependencies=[Depends(rate_limit("routes.stops.update", limit=AUTH_LIMIT))],
)
def update_stop(
    route_id: uuid.UUID,
    stop_id: uuid.UUID,
    payload: RouteStopUpdate,
    user: CurrentUser,
    db: DbSession,
) -> RouteStopWithPlace:
    return route_service.update_stop(db, route_id, stop_id, user, payload)


@router.delete(
    "/{route_id}/stops/{stop_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Stop'u rotadan çıkar",
    description=(
        "Stop silindiğinde diğer stop'ların ``order_index`` değerleri "
        "**dokunulmaz**; istemci sıralı listeyi yine de ``order_index`` "
        "üzerinden alır. Yeniden numaralama PRD §15.1 rota motoruna "
        "bırakılmıştır."
    ),
    dependencies=[Depends(rate_limit("routes.stops.delete", limit=AUTH_LIMIT))],
    response_class=Response,
)
def remove_stop(
    route_id: uuid.UUID,
    stop_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> Response:
    route_service.remove_stop(db, route_id, stop_id, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
