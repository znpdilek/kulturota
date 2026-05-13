"""
User Modeli
===========
PRD Bölüm 10.2 - ``users`` tablosu.
PRD Bölüm 11 - ``USERS ||--o{ ROUTES / PHOTOS / REVIEWS / FAVORITES / FOLLOWS / REPORTS``.

D3 Kararı (PRD Bölüm 2 + 17.3): Sadece 18+ kullanıcı kayıt olabilir.
``birth_date`` kolonu NOT NULL + DB CHECK constraint ile zorlanır.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.db.base_class import Base
from app.db.mixins import TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import pg_enum

if TYPE_CHECKING:
    from app.models.favorite import Favorite
    from app.models.follow import Follow
    from app.models.photo import Photo
    from app.models.report import Report
    from app.models.review import Review
    from app.models.route import Route
    from app.models.route_comment import RouteComment
    from app.models.route_like import RouteLike


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """``users`` tablosu — PRD 10.2."""

    __tablename__ = "users"

    # --- Kimlik ---------------------------------------------------------------
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True, index=True)
    username: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Profil --------------------------------------------------------------
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Yetki ve dil --------------------------------------------------------
    role: Mapped[UserRole] = mapped_column(
        pg_enum(UserRole, name="user_role"),
        nullable=False,
        server_default=UserRole.USER.value,
    )
    locale: Mapped[str] = mapped_column(String(8), nullable=False, server_default="tr")

    # --- KVKK + 18+ (PRD D3) -------------------------------------------------
    birth_date: Mapped[date] = mapped_column(Date, nullable=False)
    kvkk_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Doğrulama / güvenlik ------------------------------------------------
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    # --- Yaşam döngüsü -------------------------------------------------------
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))

    # --- Constraintler -------------------------------------------------------
    __table_args__ = (
        # PRD D3 + 17.3: 18 yaş ve üzeri kayıt zorunluluğu (DB seviyesinde)
        CheckConstraint(
            "birth_date <= (CURRENT_DATE - INTERVAL '18 years')",
            name="adult_birth_date",
        ),
    )

    # --- İlişkiler (PRD Bölüm 11) -------------------------------------------
    routes: Mapped[list["Route"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    favorites: Mapped[list["Favorite"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    # Self-referential M2M (PRD 11): follower & followee
    following: Mapped[list["Follow"]] = relationship(
        back_populates="follower",
        foreign_keys="Follow.follower_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    followers: Mapped[list["Follow"]] = relationship(
        back_populates="followee",
        foreign_keys="Follow.followee_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    reports: Mapped[list["Report"]] = relationship(
        back_populates="reporter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    route_likes: Mapped[list["RouteLike"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    route_comments: Mapped[list["RouteComment"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
