"""
Auth Şemaları
=============
PRD §12.1 + §17.2 + §17.3.

Register akışı **D3 — 18 yaş kontrolü** (`birth_date` zorunlu) ve
**KVKK açık rıza** alanını barındırır. Çift seviyeli koruma için:

    1. Pydantic validator burada uygulama katmanında reddeder.
    2. ``users.birth_date`` üzerindeki CHECK constraint DB katmanında reddeder.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.config import settings

USERNAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_]{1,28}[a-z0-9])$")


class RegisterRequest(BaseModel):
    """Yeni kullanıcı kaydı (PRD F2 akışı).

    * `birth_date` zorunlu + 18+ kontrolü (D3).
    * `kvkk_consent` true olmadan kayıt reddedilir (PRD §17.3).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    email: EmailStr
    username: Annotated[str, Field(min_length=3, max_length=30)]
    password: Annotated[str, Field(min_length=10, max_length=128)]
    display_name: Annotated[str | None, Field(default=None, max_length=120)] = None
    birth_date: date
    kvkk_consent: bool = Field(
        ...,
        description="KVKK aydınlatma metnine açık rıza (PRD §17.3).",
    )
    locale: Annotated[str, Field(default="tr", min_length=2, max_length=8)] = "tr"

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        value_lower = value.lower()
        if not USERNAME_PATTERN.fullmatch(value_lower):
            raise ValueError(
                "Kullanıcı adı 3-30 karakter olmalı; küçük harf, rakam ve alt çizgi "
                "içerebilir; baş/son karakter harf veya rakam olmalı."
            )
        return value_lower

    @field_validator("birth_date")
    @classmethod
    def _validate_age(cls, value: date) -> date:
        today = date.today()
        years = today.year - value.year - (
            (today.month, today.day) < (value.month, value.day)
        )
        if years < settings.MIN_REGISTRATION_AGE_YEARS:
            raise ValueError(
                f"Sisteme yalnızca {settings.MIN_REGISTRATION_AGE_YEARS} yaş ve üzeri "
                "kayıt olabilir (KVKK / PRD D3)."
            )
        return value

    @model_validator(mode="after")
    def _require_consent(self) -> "RegisterRequest":
        if not self.kvkk_consent:
            raise ValueError("Kayıt için KVKK açık rıza zorunludur.")
        return self


class LoginRequest(BaseModel):
    """E-posta veya kullanıcı adı + şifre ile giriş."""

    model_config = ConfigDict(str_strip_whitespace=True)

    identifier: Annotated[
        str,
        Field(min_length=3, max_length=254, description="E-posta veya kullanıcı adı."),
    ]
    password: Annotated[str, Field(min_length=1, max_length=128)]


class RefreshRequest(BaseModel):
    """Rotating refresh token kullanımı."""

    refresh_token: Annotated[str, Field(min_length=20)]


class LogoutRequest(BaseModel):
    """Aktif refresh token'ı revoke etmek için."""

    refresh_token: Annotated[str, Field(min_length=20)]


class TokenPair(BaseModel):
    """OAuth 2.0 token cevabı (PRD §12.1 — JWT RS256)."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    access_token_expires_at: datetime
    refresh_token_expires_at: datetime
