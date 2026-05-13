"""
Route Servisi (Adım 7 — Core MVP)
=================================
PRD §10.2 (``routes`` + ``route_stops``) + §11.1 (referans bütünlüğü) + §12.2
(``/v1/routes`` ailesi).

Sorumluluklar
-------------
* Rota CRUD: oluşturma, listeleme (kullanıcının kendi + public), detay,
  güncelleme ve silme.
* Stop yönetimi: rotaya mekan ekleme, sıralı listeleme ve çıkarma.
* Sahiplik kontrolü (PRD §17.2 RBAC): sadece sahip mutasyon yapabilir;
  detay görüntüleme ise sahip + ``is_public`` rotalar için herkese açıktır.

Tasarım notları
---------------
* ``route_stops`` tablosunda ``UNIQUE(route_id, order_index)`` (PRD §10.2 +
  §11.1) bütünlüğü sağlar. Eklerken aynı sırayı isteyen kullanıcıya 409
  döneriz; sıralama mutasyonları PRD §15.1 rota motoruna bırakılmıştır.
* Stop ekleme sırasında ``place_id`` mutlaka **yayında** olmalıdır
  (``places.is_published = true``); yayından kaldırılmış kayıt rotaya
  alınamaz.
* Stop silmek serbest gap bırakır (örn. 0, 1, 3); detay GET'i ``order_index``
  ile sıralar — yeniden numaralama ileride rota motoru sorumluluğundadır.
* Algoritmik optimizasyon, otomatik AI rota önerisi ve süre/mesafe hesabı
  bu adımda **kapsam dışıdır** (kullanıcı talebi).
"""

from __future__ import annotations

import logging
import uuid

from geoalchemy2.shape import to_shape
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ProblemDetailsError
from app.models.place import Place
from app.models.route import Route
from app.models.route_stop import RouteStop
from app.models.user import User
from app.schemas.place import Coordinate
from app.schemas.route import (
    PlaceMini,
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

logger = logging.getLogger(__name__)

# Bir rotaya bağlanabilecek maksimum stop sayısı — DoS savunması ve MVP
# kapsamı (PRD §18.3 ölçek hedefleri). 250 oldukça cömert; gerçek günlük
# rotalar 5-20 stop civarıdır.
MAX_STOPS_PER_ROUTE = 250


# ===========================================================================
# Helpers
# ===========================================================================
def _coord_of(place: Place) -> Coordinate:
    """``geography(Point)`` → :class:`Coordinate`."""
    shp = to_shape(place.koordinat)
    return Coordinate(lat=shp.y, lng=shp.x)


def _place_mini(place: Place) -> PlaceMini:
    return PlaceMini(
        id=place.id,
        slug=place.slug,
        isim=place.isim,
        koordinat=_coord_of(place),
        kategori=list(place.kategori or []),
        kapak_foto_url=place.kapak_foto_url,
    )


def _route_summary(route: Route, *, stop_count: int) -> RouteSummary:
    return RouteSummary(
        id=route.id,
        owner_id=route.owner_id,
        title=route.title,
        description=route.description,
        theme=route.theme,
        is_public=route.is_public,
        cover_image_url=route.cover_image_url,
        est_duration_min=route.est_duration_min,
        total_distance_km=(
            float(route.total_distance_km) if route.total_distance_km is not None else None
        ),
        difficulty=route.difficulty,
        stop_count=stop_count,
        created_at=route.created_at,
        updated_at=route.updated_at,
    )


def _stop_with_place(stop: RouteStop, place: Place) -> RouteStopWithPlace:
    return RouteStopWithPlace(
        id=stop.id,
        route_id=stop.route_id,
        place_id=stop.place_id,
        order_index=stop.order_index,
        planned_arrival=stop.planned_arrival,
        planned_duration_min=stop.planned_duration_min,
        notes=stop.notes,
        place=_place_mini(place),
    )


def _load_route_for_owner(db: Session, route_id: uuid.UUID, owner_id: uuid.UUID) -> Route:
    """Sadece sahibin erişebileceği rotayı getir; aksi halde 404 fırlat.

    Not: 403 yerine bilinçli olarak **404** dönüyoruz çünkü "var ama erişim
    yok" bilgisi sızıntı oluşturur (PRD §17 — bilgi açığa çıkarma azaltma).
    """
    route = db.scalar(
        select(Route).where(Route.id == route_id, Route.owner_id == owner_id)
    )
    if route is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Rota bulunamadı.",
            code="routes.not_found",
        )
    return route


def _load_route_for_read(
    db: Session, route_id: uuid.UUID, viewer_id: uuid.UUID | None
) -> Route:
    """Detay okuma için yetkilendirilmiş rota: sahip VEYA public.

    ``viewer_id`` None ise yalnızca public rotalara izin verilir.
    """
    visibility_clauses = [Route.is_public.is_(True)]
    if viewer_id is not None:
        visibility_clauses.append(Route.owner_id == viewer_id)

    route = db.scalar(
        select(Route).where(Route.id == route_id, or_(*visibility_clauses))
    )
    if route is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Rota bulunamadı.",
            code="routes.not_found",
        )
    return route


def _next_order_index(db: Session, route_id: uuid.UUID) -> int:
    """Yeni stop için bir sonraki ``order_index`` (mevcut max + 1).

    Hiç stop yoksa 0 ile başlar (0-tabanlı). PRD §10.2'de tip ``int``
    olduğu için negatif olmayan tüm değerler geçerlidir.
    """
    current_max = db.scalar(
        select(func.max(RouteStop.order_index)).where(RouteStop.route_id == route_id)
    )
    return 0 if current_max is None else int(current_max) + 1


def _count_stops(db: Session, route_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count()).select_from(RouteStop).where(RouteStop.route_id == route_id)
        )
        or 0
    )


# ===========================================================================
# Routes — CRUD
# ===========================================================================
def create_route(db: Session, owner: User, payload: RouteCreate) -> RouteSummary:
    """``POST /v1/routes`` — yeni rota oluştur (PRD §10.2 + §12.2)."""
    route = Route(
        owner_id=owner.id,
        title=payload.title,
        description=payload.description,
        theme=payload.theme,
        is_public=payload.is_public,
        cover_image_url=str(payload.cover_image_url) if payload.cover_image_url else None,
        difficulty=payload.difficulty,
    )
    db.add(route)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("rota oluşturulamadı: owner=%s", owner.id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Rota kaydedilemedi.",
            code="routes.create_failed",
        ) from exc
    db.refresh(route)
    return _route_summary(route, stop_count=0)


def list_my_routes(
    db: Session,
    owner_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> RouteListResponse:
    """``GET /v1/routes`` — yalnızca sahibin kendi rotaları (PRD §12.2).

    Public/global ``/v1/routes`` listelemesi sosyal trending hesabıyla
    birlikte gelecek adımda eklenecektir; MVP'de sahip-merkezli listeleme.
    """
    where = Route.owner_id == owner_id

    total = (
        db.scalar(select(func.count()).select_from(Route).where(where)) or 0
    )

    stmt = (
        select(
            Route,
            func.count(RouteStop.id).label("stop_count"),
        )
        .outerjoin(RouteStop, RouteStop.route_id == Route.id)
        .where(where)
        .group_by(Route.id)
        .order_by(Route.updated_at.desc())
        .limit(limit)
        .offset(offset)
    )

    items = [
        _route_summary(route, stop_count=int(stop_count or 0))
        for route, stop_count in db.execute(stmt).all()
    ]

    return RouteListResponse(
        items=items,
        total=int(total),
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < int(total),
    )


def get_route_detail(
    db: Session,
    route_id: uuid.UUID,
    viewer_id: uuid.UUID | None,
) -> RouteDetail:
    """``GET /v1/routes/{id}`` — sıralı stop listesiyle birlikte detay.

    Sahip her zaman görür; başkaları yalnızca ``is_public`` rotaları görür.
    """
    route = _load_route_for_read(db, route_id, viewer_id)

    # Stop'ları place'leriyle birlikte tek sorguda çek (N+1 önleme: PRD §18.2).
    stop_rows = db.execute(
        select(RouteStop, Place)
        .join(Place, Place.id == RouteStop.place_id)
        .where(RouteStop.route_id == route.id)
        .order_by(RouteStop.order_index.asc())
    ).all()

    stops = [_stop_with_place(stop, place) for stop, place in stop_rows]

    summary = _route_summary(route, stop_count=len(stops))
    return RouteDetail(
        **summary.model_dump(),
        stops=stops,
    )


def update_route(
    db: Session,
    route_id: uuid.UUID,
    owner: User,
    payload: RouteUpdate,
) -> RouteSummary:
    """``PUT /v1/routes/{id}`` — sahibin alanlarını günceller."""
    route = _load_route_for_owner(db, route_id, owner.id)

    updates = payload.model_dump(exclude_unset=True)
    changed = False
    for field, new_value in updates.items():
        # AnyHttpUrl → str (model Text/varchar bekler)
        if field == "cover_image_url" and new_value is not None:
            new_value = str(new_value)
        if getattr(route, field) == new_value:
            continue
        setattr(route, field, new_value)
        changed = True

    if not changed:
        # Idempotent davranış: hiçbir şey değişmediyse mevcut durumu döndür.
        return _route_summary(route, stop_count=_count_stops(db, route.id))

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("rota güncellenemedi: id=%s", route.id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Rota güncellenemedi.",
            code="routes.update_failed",
        ) from exc
    db.refresh(route)
    return _route_summary(route, stop_count=_count_stops(db, route.id))


def delete_route(db: Session, route_id: uuid.UUID, owner: User) -> None:
    """``DELETE /v1/routes/{id}`` — rotayı ve bağlı stop'ları sil.

    ``Route.stops`` ilişkisinde ``cascade='all, delete-orphan'`` +
    ``ON DELETE CASCADE`` (PRD §11.1) sayesinde stop'lar otomatik silinir.
    ``places`` kayıtları kamu verisidir; etkilenmez (RESTRICT yerine
    cascade `routes`'tan akar, `places`'a değil).
    """
    route = _load_route_for_owner(db, route_id, owner.id)
    db.delete(route)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("rota silinemedi: id=%s", route_id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Rota silinemedi.",
            code="routes.delete_failed",
        ) from exc


# ===========================================================================
# Route stops — ekle / listele / çıkar
# ===========================================================================
def list_stops(
    db: Session,
    route_id: uuid.UUID,
    viewer_id: uuid.UUID | None,
) -> RouteStopListResponse:
    """``GET /v1/routes/{id}/stops`` — sıralı stop listesi."""
    route = _load_route_for_read(db, route_id, viewer_id)
    rows = db.execute(
        select(RouteStop, Place)
        .join(Place, Place.id == RouteStop.place_id)
        .where(RouteStop.route_id == route.id)
        .order_by(RouteStop.order_index.asc())
    ).all()
    items = [_stop_with_place(stop, place) for stop, place in rows]
    return RouteStopListResponse(items=items, total=len(items))


def add_stop(
    db: Session,
    route_id: uuid.UUID,
    owner: User,
    payload: RouteStopCreate,
) -> RouteStopWithPlace:
    """``POST /v1/routes/{id}/stops`` — rotaya yeni stop ekle.

    Sıralama
        * ``order_index`` payload'da yoksa → mevcut max + 1 (listenin sonu).
        * Açıkça gönderildiğinde aynı sırada başka stop varsa 409.

    Mekan
        ``place_id`` yayında değilse 404; rotaya yayından kaldırılmış mekan
        eklenmez (PRD §11.1 referans bütünlüğü).

    Limit
        Tek rotaya en fazla :data:`MAX_STOPS_PER_ROUTE` stop eklenebilir;
        aşılırsa 409 (DoS savunması).
    """
    route = _load_route_for_owner(db, route_id, owner.id)

    current_count = _count_stops(db, route.id)
    if current_count >= MAX_STOPS_PER_ROUTE:
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail=f"Tek rotaya en fazla {MAX_STOPS_PER_ROUTE} stop eklenebilir.",
            code="routes.stops_limit_exceeded",
            extras={"limit": MAX_STOPS_PER_ROUTE},
        )

    place = db.scalar(
        select(Place).where(Place.id == payload.place_id, Place.is_published.is_(True))
    )
    if place is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Mekan bulunamadı veya yayında değil.",
            code="routes.place_not_found",
        )

    order_index = (
        payload.order_index
        if payload.order_index is not None
        else _next_order_index(db, route.id)
    )

    stop = RouteStop(
        route_id=route.id,
        place_id=place.id,
        order_index=order_index,
        planned_arrival=payload.planned_arrival,
        planned_duration_min=payload.planned_duration_min,
        notes=payload.notes,
    )
    db.add(stop)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # PRD §10.2: UNIQUE(route_id, order_index) çakışması en yaygın sebep.
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail=(
                f"Aynı sırada ({order_index}) zaten bir stop var. "
                "Farklı bir order_index gönderin veya alanı boş bırakın."
            ),
            code="routes.stop_order_conflict",
            extras={"order_index": order_index},
        ) from exc
    db.refresh(stop)
    return _stop_with_place(stop, place)


def update_stop(
    db: Session,
    route_id: uuid.UUID,
    stop_id: uuid.UUID,
    owner: User,
    payload: RouteStopUpdate,
) -> RouteStopWithPlace:
    """``PATCH /v1/routes/{id}/stops/{stop_id}`` — kısmi güncelleme.

    Sıralama burada değiştirilemez; PRD §15.1 rota motoru sıralamayı
    algoritmik olarak optimize edecektir.
    """
    route = _load_route_for_owner(db, route_id, owner.id)
    stop = db.scalar(
        select(RouteStop).where(RouteStop.id == stop_id, RouteStop.route_id == route.id)
    )
    if stop is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Stop bulunamadı.",
            code="routes.stop_not_found",
        )

    updates = payload.model_dump(exclude_unset=True)
    for field, new_value in updates.items():
        setattr(stop, field, new_value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Stop güncellenemedi.",
            code="routes.stop_update_failed",
        ) from exc

    db.refresh(stop)
    place = db.get(Place, stop.place_id)
    if place is None:  # tutarlılık koruması (RESTRICT FK ile olmamalı)
        raise ProblemDetailsError(
            status=500,
            title="Internal Server Error",
            detail="Stop'a bağlı mekan kaybolmuş — tutarlılık ihlali.",
            code="routes.stop_place_missing",
        )
    return _stop_with_place(stop, place)


def remove_stop(
    db: Session,
    route_id: uuid.UUID,
    stop_id: uuid.UUID,
    owner: User,
) -> None:
    """``DELETE /v1/routes/{id}/stops/{stop_id}`` — stop'u rotadan çıkar."""
    route = _load_route_for_owner(db, route_id, owner.id)
    stop = db.scalar(
        select(RouteStop).where(RouteStop.id == stop_id, RouteStop.route_id == route.id)
    )
    if stop is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Stop bulunamadı.",
            code="routes.stop_not_found",
        )
    db.delete(stop)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("stop silinemedi: id=%s", stop_id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Stop silinemedi.",
            code="routes.stop_delete_failed",
        ) from exc


__all__ = [
    "MAX_STOPS_PER_ROUTE",
    "add_stop",
    "create_route",
    "delete_route",
    "get_route_detail",
    "list_my_routes",
    "list_stops",
    "remove_stop",
    "update_route",
    "update_stop",
]
