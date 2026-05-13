"""
Route Like Servisi (Adım 8 — Sosyal Özellikler / Beğeni MVP)
============================================================
PRD §10.2 ``route_likes`` + §12.2 ``/v1/routes/{route_id}/likes``.

Sorumluluklar
-------------
* **Like**: Kullanıcı, halka açık (``is_public=True``) bir rotaya beğeni
  bırakır. PK ``(user_id, route_id)`` bileşik olduğu için işlem doğal
  olarak **idempotent**: ikinci ``POST`` 409 değil, 200 (zaten beğenmiş)
  döner.
* **Unlike**: Beğeniyi geri çeker. Beğeni yoksa 404 değil, 200 (zaten
  beğenmemiş) — idempotent semantik.
* **Status**: Mevcut kullanıcının beğeni durumu + rotanın toplam beğeni
  sayısı.

MVP yaklaşımı (kullanıcı talebi)
--------------------------------
* Yalnızca temel like/unlike akışı vardır. Beğenenler listesi, takip
  ilişkisi (followers/following) ve bildirim altyapısı **kapsam dışıdır**.
* Kullanıcı kendi rotasını beğenemez (PRD §8 talebi: "başkalarının
  oluşturduğu halka açık rotalar"). Self-like denemesi 400 ile reddedilir.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ProblemDetailsError
from app.models.route import Route
from app.models.route_like import RouteLike
from app.models.user import User
from app.schemas.route_like import RouteLikeResponse, RouteLikeStatus

logger = logging.getLogger(__name__)


# ===========================================================================
# Helpers
# ===========================================================================
def _load_likeable_route(db: Session, route_id: uuid.UUID, user_id: uuid.UUID) -> Route:
    """Beğenilebilir rotayı getir; aksi halde uygun hata fırlat.

    Kurallar
        * Rota yoksa → 404.
        * Rota public değilse → 404 (bilgi sızıntısı önlemi: "var ama
          gizli" demek yerine "yok" diyoruz — PRD §17 STRIDE).
        * Rota kullanıcının kendisine aitse → 400 (kendi rotanı
          beğenemezsin; kullanıcı talebi).
    """
    route = db.scalar(select(Route).where(Route.id == route_id))
    if route is None or not route.is_public:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Rota bulunamadı veya halka açık değil.",
            code="route_likes.route_not_found",
        )
    if route.owner_id == user_id:
        raise ProblemDetailsError(
            status=400,
            title="Bad Request",
            detail="Kendi rotanızı beğenemezsiniz.",
            code="route_likes.cannot_like_own",
        )
    return route


def _like_count(db: Session, route_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(RouteLike)
            .where(RouteLike.route_id == route_id)
        )
        or 0
    )


def _fetch_like(
    db: Session, route_id: uuid.UUID, user_id: uuid.UUID
) -> RouteLike | None:
    return db.scalar(
        select(RouteLike).where(
            RouteLike.route_id == route_id, RouteLike.user_id == user_id
        )
    )


# ===========================================================================
# Public service API
# ===========================================================================
def like_route(
    db: Session,
    user: User,
    route_id: uuid.UUID,
) -> RouteLikeResponse:
    """``POST /v1/routes/{route_id}/likes`` — beğeni ekle (idempotent).

    Aynı kullanıcı ikinci kez tetiklerse 409 değil ``action=already_liked``
    ile mevcut state döner; mobilde retry'larda hata baskılaması.
    """
    _load_likeable_route(db, route_id, user.id)

    existing = _fetch_like(db, route_id, user.id)
    if existing is not None:
        # İdempotent: zaten beğenilmiş; mevcut state'i döndür.
        return RouteLikeResponse(
            route_id=route_id,
            liked=True,
            like_count=_like_count(db, route_id),
            liked_at=existing.created_at,
            action="already_liked",
        )

    like = RouteLike(user_id=user.id, route_id=route_id)
    db.add(like)
    try:
        db.commit()
    except IntegrityError as exc:
        # Yarış koşulu: iki paralel POST sebebiyle PK çakışması.
        db.rollback()
        existing = _fetch_like(db, route_id, user.id)
        if existing is not None:
            return RouteLikeResponse(
                route_id=route_id,
                liked=True,
                like_count=_like_count(db, route_id),
                liked_at=existing.created_at,
                action="already_liked",
            )
        logger.exception("beğeni kaydedilemedi: route=%s user=%s", route_id, user.id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Beğeni kaydedilemedi.",
            code="route_likes.create_failed",
        ) from exc

    db.refresh(like)
    return RouteLikeResponse(
        route_id=route_id,
        liked=True,
        like_count=_like_count(db, route_id),
        liked_at=like.created_at,
        action="created",
    )


def unlike_route(
    db: Session,
    user: User,
    route_id: uuid.UUID,
) -> RouteLikeResponse:
    """``DELETE /v1/routes/{route_id}/likes`` — beğeniyi geri çek (idempotent).

    Beğeni yoksa 404 değil ``action=not_liked`` ile mevcut state döner.
    """
    # Rota erişilemese bile (silinmiş/private yapılmış) kullanıcı kendi
    # beğenisini geri çekebilmeli — son durumdan bağımsız olarak satırı
    # temizliyoruz. Bu yüzden ``_load_likeable_route`` çağırmıyoruz; sadece
    # like satırını arıyoruz.
    existing = _fetch_like(db, route_id, user.id)
    if existing is None:
        return RouteLikeResponse(
            route_id=route_id,
            liked=False,
            like_count=_like_count(db, route_id),
            liked_at=None,
            action="not_liked",
        )

    db.delete(existing)
    try:
        db.commit()
    except IntegrityError as exc:  # pragma: no cover — like başka tabloya FK olmaz
        db.rollback()
        logger.exception("beğeni silinemedi: route=%s user=%s", route_id, user.id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Beğeni silinemedi.",
            code="route_likes.delete_failed",
        ) from exc

    return RouteLikeResponse(
        route_id=route_id,
        liked=False,
        like_count=_like_count(db, route_id),
        liked_at=None,
        action="removed",
    )


def get_like_status(
    db: Session,
    user: User,
    route_id: uuid.UUID,
) -> RouteLikeStatus:
    """``GET /v1/routes/{route_id}/likes`` — kullanıcının durumu + sayı.

    Salt-okunur erişim: rota gizli ya da silinmişse 404 değil ``liked=False
    + like_count=0`` döndürmek yerine, tutarlılık için 404 fırlatıyoruz —
    UI bu durumu açıkça "rota yok" olarak göstermeli.
    """
    route = db.scalar(select(Route).where(Route.id == route_id))
    if route is None or not route.is_public:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Rota bulunamadı veya halka açık değil.",
            code="route_likes.route_not_found",
        )

    existing = _fetch_like(db, route_id, user.id)
    liked_at: datetime | None = existing.created_at if existing is not None else None
    return RouteLikeStatus(
        route_id=route_id,
        liked=existing is not None,
        like_count=_like_count(db, route_id),
        liked_at=liked_at,
    )


__all__ = [
    "get_like_status",
    "like_route",
    "unlike_route",
]
