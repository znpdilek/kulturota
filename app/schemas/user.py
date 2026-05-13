"""
User Şemaları
=============
PRD §10.2 + §12.1 — kullanıcı response DTO'ları.

Adım 5 (Profil + KVKK):
    * :class:`UserUpdate` — ``PUT /v1/users/me`` payload'ı (PRD §13.1 /ayarlar).
    * :class:`UserDataExport` — ``GET /v1/users/me/export-data`` cevap zarfı
      (PRD §17.3 "Veri dışa aktarma → JSON paketi").
    * :class:`UserDeleteResponse` — ``DELETE /v1/users/me`` audit/onay zarfı.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, ClassVar

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.enums import UserRole

USERNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_]{1,28}[a-z0-9])$")


class UserPublic(BaseModel):
    """Profil sayfasında, takip listelerinde gösterilecek minimal kullanıcı."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    display_name: str | None
    avatar_url: str | None


class UserMe(BaseModel):
    """``GET /v1/me`` cevabı — sadece sahip görür."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    username: str
    display_name: str | None
    avatar_url: str | None
    role: UserRole
    locale: str
    birth_date: date
    kvkk_consent_at: datetime | None
    email_verified_at: datetime | None
    mfa_enabled: bool
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


# --- PUT /v1/users/me ------------------------------------------------------
class UserUpdate(BaseModel):
    """Profil güncelleme payload'ı (PRD §13.1 → ``/ayarlar``).

    PATCH semantiği: Yalnızca açıkça gönderilen alanlar güncellenir. KVKK
    açısından hassas alanlar (``email``, ``password``, ``birth_date``,
    ``role``, ``kvkk_consent_at``) **bu uçtan değiştirilemez**; her biri
    ayrı doğrulama akışı gerektirir (e-posta için re-verification, şifre
    için eski şifre, doğum tarihi için kimlik kanıtı vb.).

    ``username`` değişikliği, eski kullanıcı adıyla paylaşılmış public
    URL'leri kıracağı için MVP'de scope dışında tutulmuştur (Faz 6
    redirect mekanizmasıyla açılır).
    """

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    display_name: Annotated[str | None, Field(default=None, max_length=120)] = None
    avatar_url: Annotated[AnyHttpUrl | None, Field(default=None)] = None
    locale: Annotated[str | None, Field(default=None, min_length=2, max_length=8)] = None

    @field_validator("display_name")
    @classmethod
    def _normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        return stripped

    @field_validator("locale")
    @classmethod
    def _normalize_locale(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]{2,4})?", normalized):
            raise ValueError("Locale BCP-47 biçiminde olmalı (örn: tr, en, tr-tr).")
        return normalized

    @model_validator(mode="after")
    def _require_at_least_one(self) -> "UserUpdate":
        if (
            self.display_name is None
            and self.avatar_url is None
            and self.locale is None
        ):
            raise ValueError("Güncellenecek en az bir alan göndermelisiniz.")
        return self


# --- DELETE /v1/users/me ---------------------------------------------------
#: KVKK silme onayı için beklenen sabit metin. ``ClassVar`` yerine modül
#: düzeyinde tutuyoruz; Pydantic v2'de "tip = değer" bildirimi otomatik
#: olarak model field'ına dönüşüyor (cls.EXPECTED_CONFIRM → AttributeError).
DELETE_CONFIRM_PHRASE = "HESABIMI KALICI OLARAK SİL"


class UserDeleteRequest(BaseModel):
    """KVKK gereği "sil" eylemi için açık onay (PRD §17.3 "Hak Talepleri").

    ``confirm`` alanı tipo / kazara silmeye karşı emniyet kapısıdır; istemci
    :data:`DELETE_CONFIRM_PHRASE` ile birebir aynı metni göndermelidir.
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    confirm: Annotated[str, Field(min_length=3, max_length=120)]
    reason: Annotated[str | None, Field(default=None, max_length=500)] = None

    #: Geriye dönük uyum için sınıf üzerinden de okunabilir (read-only).
    EXPECTED_CONFIRM: ClassVar[str] = DELETE_CONFIRM_PHRASE

    @field_validator("confirm")
    @classmethod
    def _validate_confirm(cls, value: str) -> str:
        if value.strip() != DELETE_CONFIRM_PHRASE:
            raise ValueError(
                f"Onay metni tam olarak şu olmalı: '{DELETE_CONFIRM_PHRASE}'."
            )
        return value.strip()


class UserDeleteResponse(BaseModel):
    """Silme işleminin audit özeti — yasal saklama ve istemci için tutanak."""

    user_id: uuid.UUID
    deleted_at: datetime
    deleted_relations: dict[str, int] = Field(
        description=(
            "İlişkili kayıt türü → silinen kayıt sayısı (routes, photos, reviews, "
            "favorites, follows, route_likes, route_comments, reports, "
            "refresh_tokens)."
        )
    )
    audit_log_id: uuid.UUID | None = None


# --- GET /v1/users/me/export-data ------------------------------------------
class ExportMetadata(BaseModel):
    """Veri paketinin denetim ve sürüm bilgileri (PRD §17.3 + §20.2)."""

    schema_version: str
    generated_at: datetime
    user_id: uuid.UUID
    legal_basis: str = Field(
        default=(
            "KVKK Md. 11 (kişisel veriye erişim hakkı) ve GDPR Art. 15 "
            "(right of access) / Art. 20 (right to data portability)."
        )
    )
    format: str = "application/json"
    notes: str = Field(
        default=(
            "Bu paket, sistemdeki tüm kişisel verilerinizi içerir. Halka açık "
            "ve lisanslı kültürel miras verileri (places, opening_hours vb.) "
            "kişisel veri değildir; pakete dahil edilmez."
        )
    )


class UserDataExport(BaseModel):
    """``GET /v1/users/me/export-data`` JSON paketi (PRD §17.3).

    Halka açık kültürel miras verisi (``places``) KVKK kapsamında kişisel
    veri değildir; bu pakette **yer almaz**. Yalnızca kullanıcıya ait
    veriler ve kullanıcının ürettiği UGC içeriği bulunur.
    """

    metadata: ExportMetadata
    profile: dict[str, Any]
    consents: dict[str, Any]
    sessions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Refresh token meta (jti, ip, ua, expires_at) — token değeri DEĞİL.",
    )
    routes: list[dict[str, Any]] = Field(default_factory=list)
    route_stops: list[dict[str, Any]] = Field(default_factory=list)
    photos: list[dict[str, Any]] = Field(default_factory=list)
    reviews: list[dict[str, Any]] = Field(default_factory=list)
    favorites: list[dict[str, Any]] = Field(default_factory=list)
    follows: dict[str, list[dict[str, Any]]] = Field(
        default_factory=lambda: {"following": [], "followers": []}
    )
    route_likes: list[dict[str, Any]] = Field(default_factory=list)
    route_comments: list[dict[str, Any]] = Field(default_factory=list)
    reports: list[dict[str, Any]] = Field(default_factory=list)
    audit_log: list[dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Kullanıcının actor veya target olduğu denetim kayıtları "
            "(PRD §10.2 audit_log)."
        ),
    )
