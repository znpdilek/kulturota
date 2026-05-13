"""
User Servisi (Profil + KVKK / GDPR)
====================================
PRD §12.2 + §17.3 — Adım 5 çıktıları.

Sorumluluklar
-------------
* Profil güncelleme (``PUT /v1/users/me``) — değişikliği ``audit_log``
  tablosuna kim/ne zaman/eski→yeni olarak yaz.
* KVKK veri dışa aktarma (``GET /v1/users/me/export-data``) — kullanıcıya
  ait *tüm* kişisel veri ve UGC'yi tek bir JSON paketi olarak derle
  (PRD §17.3 "Hak Talepleri: Veri dışa aktarma → JSON paketi").
* Hesap silme (``DELETE /v1/users/me``) — kullanıcıyı ve tüm kişisel
  izleri kalıcı olarak sil; ``audit_log`` kaydı yasal saklama için
  ``actor_id NULL`` olarak korunur (PRD §10.2).

Tasarım notları
---------------
* Burada *halka açık kültürel miras verileri* (places, opening_hours,
  tags, ETL/AI tabloları) **kişisel veri olarak ele alınmaz** — KVKK m.3
  kapsamı dışındadır ve pakete dahil edilmez (PRD §20: lisans-temiz
  veri mutfağı).
* Refresh token'ların *değeri* JWT olduğu için DB'de tutulmaz; pakete
  yalnızca metadata (jti, ip, ua, expires_at) yazılır.
* Tüm zaman damgaları UTC + ISO-8601 (``timezone=True``).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ProblemDetailsError
from app.models.audit_log import AuditLog
from app.models.favorite import Favorite
from app.models.follow import Follow
from app.models.photo import Photo
from app.models.refresh_token import RefreshToken
from app.models.report import Report
from app.models.review import Review
from app.models.route import Route
from app.models.route_comment import RouteComment
from app.models.route_like import RouteLike
from app.models.route_stop import RouteStop
from app.models.user import User
from app.schemas.user import (
    ExportMetadata,
    UserDataExport,
    UserUpdate,
)

logger = logging.getLogger(__name__)

EXPORT_SCHEMA_VERSION = "1.0"

#: ``users`` tablosunda PRD §17.3 uyarınca **bu uçtan değiştirilemeyen** alanlar.
_IMMUTABLE_USER_FIELDS = frozenset(
    {
        "id",
        "email",
        "username",
        "password_hash",
        "role",
        "birth_date",
        "kvkk_consent_at",
        "email_verified_at",
        "mfa_enabled",
        "is_active",
        "last_login_at",
        "created_at",
        "updated_at",
    }
)


# --- Yardımcılar -----------------------------------------------------------
def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _client_info(ip: str | None, user_agent: str | None) -> tuple[str | None, str | None]:
    """Audit kaydı için IP + UA normalleştirme (max length koruma)."""
    if ip is not None:
        ip = ip[:45] or None
    if user_agent is not None:
        user_agent = user_agent[:255] or None
    return ip, user_agent


# --- Profil güncelleme -----------------------------------------------------
def update_profile(
    db: Session,
    user: User,
    payload: UserUpdate,
    *,
    actor_ip: str | None = None,
    actor_user_agent: str | None = None,
) -> User:
    """``PUT /v1/users/me`` — yalnızca güvenli alanları günceller.

    Pydantic ``extra='forbid'`` + ``_IMMUTABLE_USER_FIELDS`` ikili savunma
    sağlar. Her değişiklik ``audit_log``'a ``profile.update`` olarak yazılır;
    böylece KVKK Md.11/c (kimin, ne zaman, ne değiştirdiği) sorularına
    cevap verilebilir.
    """
    changes: dict[str, tuple[Any, Any]] = {}

    update_fields = payload.model_dump(exclude_unset=True)
    if not update_fields:
        raise ProblemDetailsError(
            status=422,
            title="Unprocessable Entity",
            detail="Güncellenecek alan bulunmuyor.",
            code="profile.no_changes",
        )

    for field, new_value in update_fields.items():
        if field in _IMMUTABLE_USER_FIELDS:
            # extra='forbid' bunu Pydantic'te yakalamalıydı; defansif kontrol.
            raise ProblemDetailsError(
                status=400,
                title="Bad Request",
                detail=(
                    f"'{field}' alanı bu uçtan değiştirilemez. "
                    "Hassas alanlar için ayrılmış akışlar gerekir."
                ),
                code="profile.field_immutable",
            )
        if not hasattr(user, field):
            continue

        # AnyHttpUrl → str (DB Text kolonu).
        normalized = str(new_value) if new_value is not None else None
        if field == "display_name" and isinstance(new_value, str):
            normalized = new_value
        if field == "locale" and isinstance(new_value, str):
            normalized = new_value

        old_value = getattr(user, field)
        if old_value == normalized:
            continue

        setattr(user, field, normalized)
        changes[field] = (old_value, normalized)

    if not changes:
        # Sessiz dönüş yerine 200 + mevcut profil — istemci için idempotent.
        return user

    ip, ua = _client_info(actor_ip, actor_user_agent)

    for field, (old_value, new_value) in changes.items():
        db.add(
            AuditLog(
                actor_id=user.id,
                action="profile.update",
                target_type="user",
                target_id=user.id,
                field=field,
                old_value={"value": old_value},
                new_value={"value": new_value},
                ip=ip,
                user_agent=ua,
            )
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("profil güncellemesi sırasında integrity hatası")
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail="Profil kaydı güncellenemedi.",
            code="profile.update_failed",
        ) from exc

    db.refresh(user)
    return user


# --- KVKK veri dışa aktarma ------------------------------------------------
def export_user_data(db: Session, user: User) -> UserDataExport:
    """``GET /v1/users/me/export-data`` (PRD §17.3).

    Veri kategorileri (her biri JSON dizi/dict olarak paketlenir):

    * ``profile``        — users tablosu (password_hash hariç).
    * ``consents``       — KVKK açık rıza zaman damgası + onaylanan metin sürümü.
    * ``sessions``       — refresh_tokens (jti / ip / ua / expires_at /
                          revoked_at / revoked_reason / created_at).
                          JWT'nin kendisi taşınmaz (güvenlik).
    * ``routes``         — kullanıcının oluşturduğu rotalar + stops.
    * ``photos``         — kullanıcının yüklediği fotoğraflar (EXIF dahil,
                          GPS zaten temizlenmiş — PRD §17.3).
    * ``reviews``        — kullanıcının yazdığı yorumlar.
    * ``favorites``      — favori mekan id'leri.
    * ``follows``        — following + followers id listeleri.
    * ``route_likes``    — beğenilen rota id'leri.
    * ``route_comments`` — rota yorumları.
    * ``reports``        — kullanıcının ilettiği şikayetler.
    * ``audit_log``      — kullanıcının actor olduğu denetim kayıtları.

    Halka açık ``places`` / ``opening_hours`` / ``tags`` tabloları kişisel
    veri kapsamında değildir; dahil edilmez.
    """
    # --- Sessions (refresh tokens — değer DEĞİL, sadece meta) ----------
    sessions_rows = db.scalars(
        select(RefreshToken)
        .where(RefreshToken.user_id == user.id)
        .order_by(RefreshToken.created_at.desc())
    ).all()
    sessions = [
        {
            "id": str(row.id),
            "jti": str(row.jti),
            "parent_jti": str(row.parent_jti) if row.parent_jti else None,
            "ip": row.ip,
            "user_agent": row.user_agent,
            "created_at": _isoformat(row.created_at),
            "expires_at": _isoformat(row.expires_at),
            "used_at": _isoformat(row.used_at),
            "revoked_at": _isoformat(row.revoked_at),
            "revoked_reason": row.revoked_reason,
        }
        for row in sessions_rows
    ]

    # --- Routes + stops (lineage) -------------------------------------
    route_rows = db.scalars(
        select(Route)
        .where(Route.owner_id == user.id)
        .options(selectinload(Route.stops))
        .order_by(Route.created_at.desc())
    ).all()
    routes = [
        {
            "id": str(r.id),
            "title": r.title,
            "description": r.description,
            "theme": r.theme,
            "is_public": r.is_public,
            "cover_image_url": r.cover_image_url,
            "est_duration_min": r.est_duration_min,
            "total_distance_km": (
                float(r.total_distance_km) if r.total_distance_km is not None else None
            ),
            "difficulty": r.difficulty.value if r.difficulty is not None else None,
            "created_at": _isoformat(r.created_at),
            "updated_at": _isoformat(r.updated_at),
        }
        for r in route_rows
    ]
    route_stops = [
        {
            "id": str(stop.id),
            "route_id": str(stop.route_id),
            "place_id": str(stop.place_id),
            "order_index": stop.order_index,
            "planned_arrival": _isoformat(stop.planned_arrival),
            "planned_duration_min": stop.planned_duration_min,
            "notes": stop.notes,
        }
        for r in route_rows
        for stop in r.stops
    ]

    # --- Photos --------------------------------------------------------
    photo_rows = db.scalars(
        select(Photo)
        .where(Photo.user_id == user.id)
        .order_by(Photo.created_at.desc())
    ).all()
    photos = [
        {
            "id": str(p.id),
            "place_id": str(p.place_id),
            "route_id": str(p.route_id) if p.route_id else None,
            "url": p.url,
            "thumb_url": p.thumb_url,
            "width": p.width,
            "height": p.height,
            "taken_at": _isoformat(p.taken_at),
            "exif": p.exif,
            "license": p.license,
            "is_approved": p.is_approved,
            "nsfw_score": float(p.nsfw_score) if p.nsfw_score is not None else None,
            "phash": p.phash,
            "created_at": _isoformat(p.created_at),
        }
        for p in photo_rows
    ]

    # --- Reviews -------------------------------------------------------
    review_rows = db.scalars(
        select(Review)
        .where(Review.user_id == user.id)
        .order_by(Review.created_at.desc())
    ).all()
    reviews = [
        {
            "id": str(rv.id),
            "place_id": str(rv.place_id),
            "rating": rv.rating,
            "body": rv.body,
            "visited_at": rv.visited_at.isoformat() if rv.visited_at else None,
            "helpful_count": rv.helpful_count,
            "is_flagged": rv.is_flagged,
            "language": rv.language,
            "toxicity_score": (
                float(rv.toxicity_score) if rv.toxicity_score is not None else None
            ),
            "created_at": _isoformat(rv.created_at),
        }
        for rv in review_rows
    ]

    # --- Favorites -----------------------------------------------------
    fav_rows = db.scalars(
        select(Favorite)
        .where(Favorite.user_id == user.id)
        .order_by(Favorite.created_at.desc())
    ).all()
    favorites = [
        {
            "place_id": str(f.place_id),
            "created_at": _isoformat(f.created_at),
        }
        for f in fav_rows
    ]

    # --- Follows (self-referential) -----------------------------------
    following_rows = db.scalars(
        select(Follow)
        .where(Follow.follower_id == user.id)
        .order_by(Follow.created_at.desc())
    ).all()
    follower_rows = db.scalars(
        select(Follow)
        .where(Follow.followee_id == user.id)
        .order_by(Follow.created_at.desc())
    ).all()
    follows = {
        "following": [
            {
                "followee_id": str(f.followee_id),
                "created_at": _isoformat(f.created_at),
            }
            for f in following_rows
        ],
        "followers": [
            {
                "follower_id": str(f.follower_id),
                "created_at": _isoformat(f.created_at),
            }
            for f in follower_rows
        ],
    }

    # --- Route likes / comments ---------------------------------------
    like_rows = db.scalars(
        select(RouteLike)
        .where(RouteLike.user_id == user.id)
        .order_by(RouteLike.created_at.desc())
    ).all()
    route_likes = [
        {
            "route_id": str(rl.route_id),
            "created_at": _isoformat(rl.created_at),
        }
        for rl in like_rows
    ]

    comment_rows = db.scalars(
        select(RouteComment)
        .where(RouteComment.user_id == user.id)
        .order_by(RouteComment.created_at.desc())
    ).all()
    route_comments = [
        {
            "id": str(rc.id),
            "route_id": str(rc.route_id),
            "body": rc.body,
            "is_flagged": rc.is_flagged,
            "created_at": _isoformat(rc.created_at),
        }
        for rc in comment_rows
    ]

    # --- Reports (kullanıcının raporladıkları) ------------------------
    report_rows = db.scalars(
        select(Report)
        .where(Report.reporter_id == user.id)
        .order_by(Report.created_at.desc())
    ).all()
    reports = [
        {
            "id": str(rep.id),
            "target_type": rep.target_type.value,
            "target_id": str(rep.target_id),
            "reason": rep.reason,
            "detail": rep.detail,
            "status": rep.status.value,
            "auto_action": rep.auto_action.value,
            "created_at": _isoformat(rep.created_at),
        }
        for rep in report_rows
    ]

    # --- Audit log (kullanıcı actor) -----------------------------------
    audit_rows = db.scalars(
        select(AuditLog)
        .where(AuditLog.actor_id == user.id)
        .order_by(AuditLog.created_at.desc())
    ).all()
    audit_log = [
        {
            "id": str(a.id),
            "action": a.action,
            "target_type": a.target_type,
            "target_id": str(a.target_id) if a.target_id else None,
            "field": a.field,
            "old_value": a.old_value,
            "new_value": a.new_value,
            "ip": a.ip,
            "user_agent": a.user_agent,
            "created_at": _isoformat(a.created_at),
        }
        for a in audit_rows
    ]

    # --- Profil + KVKK rıza --------------------------------------------
    profile = {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role.value,
        "locale": user.locale,
        "birth_date": user.birth_date.isoformat(),
        "email_verified_at": _isoformat(user.email_verified_at),
        "mfa_enabled": user.mfa_enabled,
        "is_active": user.is_active,
        "last_login_at": _isoformat(user.last_login_at),
        "created_at": _isoformat(user.created_at),
        "updated_at": _isoformat(user.updated_at),
    }
    consents = {
        "kvkk_consent_at": _isoformat(user.kvkk_consent_at),
        "min_registration_age_years": 18,
        "policy_reference": "PRD §17.3 KVKK / D3",
    }

    metadata = ExportMetadata(
        schema_version=EXPORT_SCHEMA_VERSION,
        generated_at=datetime.now(tz=timezone.utc),
        user_id=user.id,
    )

    return UserDataExport(
        metadata=metadata,
        profile=profile,
        consents=consents,
        sessions=sessions,
        routes=routes,
        route_stops=route_stops,
        photos=photos,
        reviews=reviews,
        favorites=favorites,
        follows=follows,
        route_likes=route_likes,
        route_comments=route_comments,
        reports=reports,
        audit_log=audit_log,
    )


# --- Hesap silme (GDPR Art.17 / KVKK Md.7) ---------------------------------
def delete_user_account(
    db: Session,
    user: User,
    *,
    reason: str | None,
    actor_ip: str | None = None,
    actor_user_agent: str | None = None,
) -> dict[str, Any]:
    """``DELETE /v1/users/me`` — hesabı ve tüm kişisel izleri kalıcı sil.

    Önce ilişkili kayıt sayılarını topla (audit özeti için), audit log'a
    silme niyetini yaz (``actor_id NULL`` ile kalıcı), ardından
    ``db.delete(user)`` ile cascade'leri tetikle.

    Cascade haritası (PRD §11.1 + alembic):
        * ``routes`` (ON DELETE CASCADE) → ``route_stops`` (CASCADE),
          ``route_likes`` (CASCADE), ``route_comments`` (CASCADE).
        * ``photos`` (ON DELETE CASCADE).
        * ``reviews`` (ON DELETE CASCADE).
        * ``favorites`` (PK CASCADE).
        * ``follows`` (PK CASCADE — hem follower hem followee tarafı).
        * ``route_likes`` (PK CASCADE — user_id boyutu).
        * ``route_comments`` (ON DELETE CASCADE — user_id).
        * ``reports`` (ON DELETE CASCADE — reporter_id).
        * ``refresh_tokens`` (ON DELETE CASCADE).
        * ``audit_log.actor_id`` → ``ON DELETE SET NULL`` (PRD §10.2:
          5 yıl yasal saklama; kayıt anonim olarak korunur).

    Restrict riski: Eğer kullanıcının bir rotasında ``route_stops.place_id``
    bir ``place`` referansı varsa (RESTRICT), bu bir sorun değildir;
    çünkü cascade place'leri silmiyor — sadece kullanıcının route_stops
    kayıtları siliniyor. Place'ler kamu verisi olduğu için korunur.
    """
    user_id = user.id

    counts = {
        "routes": _count_rows(db, Route, Route.owner_id == user_id),
        "photos": _count_rows(db, Photo, Photo.user_id == user_id),
        "reviews": _count_rows(db, Review, Review.user_id == user_id),
        "favorites": _count_rows(db, Favorite, Favorite.user_id == user_id),
        "follows": (
            _count_rows(db, Follow, Follow.follower_id == user_id)
            + _count_rows(db, Follow, Follow.followee_id == user_id)
        ),
        "route_likes": _count_rows(db, RouteLike, RouteLike.user_id == user_id),
        "route_comments": _count_rows(
            db, RouteComment, RouteComment.user_id == user_id
        ),
        "reports": _count_rows(db, Report, Report.reporter_id == user_id),
        "refresh_tokens": _count_rows(
            db, RefreshToken, RefreshToken.user_id == user_id
        ),
    }

    ip, ua = _client_info(actor_ip, actor_user_agent)

    audit_entry = AuditLog(
        actor_id=user_id,  # silinmeden önce; cascade ile SET NULL olacak
        action="user.delete",
        target_type="user",
        target_id=user_id,
        old_value={
            "username": user.username,
            "email_domain": user.email.split("@", 1)[-1] if "@" in user.email else None,
            "deleted_relations": counts,
        },
        new_value={"reason": reason} if reason else None,
        ip=ip,
        user_agent=ua,
    )
    db.add(audit_entry)
    db.flush()
    audit_log_id = audit_entry.id

    try:
        db.delete(user)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("hesap silme sırasında integrity hatası")
        raise ProblemDetailsError(
            status=409,
            title="Conflict",
            detail=(
                "Hesap silinemedi. Aktif bir referans (örn. başkasının "
                "rotasındaki bir mekan kısıtı) silmeyi engelliyor olabilir."
            ),
            code="user.delete_failed",
        ) from exc

    return {
        "user_id": user_id,
        "deleted_at": datetime.now(tz=timezone.utc),
        "deleted_relations": counts,
        "audit_log_id": audit_log_id,
    }


# --- Sayım yardımcıları ----------------------------------------------------
def _count_rows(db: Session, model: Any, *whereclause: Any) -> int:
    """``SELECT COUNT(*) FROM model WHERE ...`` — basit count helper."""
    from sqlalchemy import func

    stmt = select(func.count()).select_from(model)
    for clause in whereclause:
        stmt = stmt.where(clause)
    result = db.scalar(stmt)
    return int(result or 0)
