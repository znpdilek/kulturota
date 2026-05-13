"""
Review Servisi (Adım 8 — Sosyal Özellikler / Yorum MVP)
=======================================================
PRD §10.2 ``reviews`` + §12.2 ``/v1/places/{place_id}/reviews``.

Sorumluluklar
-------------
* **Create**: Auth'lu kullanıcı, yayında bir mekana 1-5 arası puan + opsiyonel
  metin yorum bırakır. Bir kullanıcı bir mekana **yalnızca bir** yorum yazabilir
  (servis seviyesinde önceden kontrol + DB ``UNIQUE(place_id, user_id)``
  constraint son savunma hattı).
* **List**: Paged, anonim erişime açık (PRD §12.2 public). Her item ``author``
  alanında yorum sahibinin minimal public profilini taşır.
* **Delete**: Yalnızca yorumun **sahibi** silebilir. Sahip değilseniz 404
  döner — "var ama yetkin yok" bilgi sızıntısını engelliyoruz (PRD §17).

MVP sınırları (kullanıcı talebi)
--------------------------------
* Takip ilişkisi (followers/following), yorumlara yanıt verme (nested/threaded
  comments) ve bildirim altyapısı **kapsam dışıdır**.
* AI toksisite filtresi sunucu içinde geç eklenecektir; bu serviste sadece
  veri yazma/okuma sözleşmesi vardır.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ProblemDetailsError
from app.models.place import Place
from app.models.review import Review
from app.models.user import User
from app.schemas.review import (
    ReviewAggregate,
    ReviewCreate,
    ReviewListResponse,
    ReviewResponse,
)
from app.schemas.user import UserPublic

logger = logging.getLogger(__name__)


# ===========================================================================
# Helpers
# ===========================================================================
def _ensure_place_published(db: Session, place_id: uuid.UUID) -> Place:
    """Mekanı getir; yoksa veya yayında değilse 404 fırlat."""
    place = db.scalar(
        select(Place).where(Place.id == place_id, Place.is_published.is_(True))
    )
    if place is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Mekan bulunamadı veya yayında değil.",
            code="reviews.place_not_found",
        )
    return place


def _to_response(review: Review, author: User) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        place_id=review.place_id,
        rating=int(review.rating),
        body=review.body,
        visited_at=review.visited_at,
        helpful_count=int(review.helpful_count or 0),
        language=review.language,
        created_at=review.created_at,
        author=UserPublic.model_validate(author),
    )


def _aggregate_for(db: Session, place_id: uuid.UUID) -> ReviewAggregate:
    """Mekan için yorum sayısı + ortalama puan hesapla.

    SQL tarafında AVG(rating) + COUNT(*) tek sorguda; PRD §18.2 N+1 önleme
    ve materialize edilebilirlik için tek bir aggregate sorgusu kullanırız.
    """
    row = db.execute(
        select(
            func.count(Review.id).label("total"),
            func.avg(Review.rating).label("avg_rating"),
        ).where(Review.place_id == place_id)
    ).one()
    total = int(row.total or 0)
    avg: float | None = float(row.avg_rating) if row.avg_rating is not None else None
    return ReviewAggregate(total=total, average_rating=avg)


# ===========================================================================
# Public service API
# ===========================================================================
def create_review(
    db: Session,
    user: User,
    place_id: uuid.UUID,
    payload: ReviewCreate,
) -> ReviewResponse:
    """``POST /v1/places/{place_id}/reviews`` — yeni yorum + puan oluştur.

    İş kuralları
        * Mekan yayında olmalıdır (``is_published=True``); değilse 404.
        * Bir kullanıcı aynı mekana ikinci kez yorum yazamaz; **409** döner
          (servis önce kontrol eder, DB ``UNIQUE(place_id, user_id)``
          constraint son savunma hattıdır — yarış koşulu).
    """
    _ensure_place_published(db, place_id)

    existing = db.scalar(
        select(Review.id).where(
            Review.place_id == place_id, Review.user_id == user.id
        )
    )
    if existing is not None:
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail=(
                "Bu mekana zaten bir yorumunuz var. Yeniden yazmak için önce "
                "mevcut yorumu silin."
            ),
            code="reviews.duplicate",
            extras={"existing_review_id": str(existing)},
        )

    review = Review(
        place_id=place_id,
        user_id=user.id,
        rating=payload.rating,
        body=payload.body,
        visited_at=payload.visited_at,
    )
    db.add(review)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # Yarış koşulu: aynı kullanıcı iki paralel POST gönderdiyse DB
        # UNIQUE constraint patladı. Kullanıcıya 409 olarak yansıt.
        logger.warning(
            "review unique race: user=%s place=%s err=%s",
            user.id,
            place_id,
            exc,
        )
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Bu mekana zaten bir yorumunuz var.",
            code="reviews.duplicate",
        ) from exc
    db.refresh(review)
    return _to_response(review, user)


def list_reviews(
    db: Session,
    place_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> ReviewListResponse:
    """``GET /v1/places/{place_id}/reviews`` — sayfalı yorum listesi.

    En yeni yorumlar üstte (``created_at DESC``). Halka açık bir uçtur
    (PRD §12.2 ``public``); auth gerektirmez.
    """
    # Mekan yoksa boş liste yerine 404 dönüyoruz; istemci hatalı slug/UUID
    # kullandığında sessizce boş döndürmek yanıltıcıdır.
    _ensure_place_published(db, place_id)

    aggregate = _aggregate_for(db, place_id)

    rows = db.execute(
        select(Review, User)
        .join(User, User.id == Review.user_id)
        .where(Review.place_id == place_id)
        .order_by(Review.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = [_to_response(review, author) for review, author in rows]
    return ReviewListResponse(
        items=items,
        total=aggregate.total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(items)) < aggregate.total,
        aggregate=aggregate,
    )


def delete_review(
    db: Session,
    user: User,
    place_id: uuid.UUID,
    review_id: uuid.UUID,
) -> None:
    """``DELETE /v1/places/{place_id}/reviews/{review_id}``.

    Yalnızca yorumun sahibi silebilir; aksi halde 404 (bilgi sızıntısı
    önlemi — PRD §17 STRIDE / Information Disclosure).
    """
    review = db.scalar(
        select(Review).where(
            Review.id == review_id,
            Review.place_id == place_id,
            Review.user_id == user.id,
        )
    )
    if review is None:
        raise ProblemDetailsError(
            status=404,
            title="Not Found",
            detail="Yorum bulunamadı.",
            code="reviews.not_found",
        )

    db.delete(review)
    try:
        db.commit()
    except IntegrityError as exc:  # pragma: no cover — review hiçbir FK üretmiyor
        db.rollback()
        logger.exception("review silinemedi: id=%s", review_id)
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Yorum silinemedi.",
            code="reviews.delete_failed",
        ) from exc


__all__ = [
    "create_review",
    "delete_review",
    "list_reviews",
]
