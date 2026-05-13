"""
Swagger /docs üzerinden test kullanıcısı senaryosu
==================================================
PRD §12 + §17.3 — "Test Kullanıcısı" oluştur + giriş + /me doğrulaması.

Bu betik, Swagger UI'de "Authorize" akışıyla yapılacak adımların aynısını
HTTP üzerinden işletip kanıt çıktısı üretir.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from datetime import datetime

import httpx

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8000/api/v1"

suffix = uuid.uuid4().hex[:6]
USER = {
    "email": f"test+{suffix}@kulturrota.example.com",
    "username": f"test_kullanici_{suffix}",
    "password": "TestSifre!2026",
    "display_name": "Test Kullanıcısı",
    "birth_date": "2000-01-15",
    "kvkk_consent": True,
    "locale": "tr",
}


def step(title: str) -> None:
    print(f"\n────────────────────────────────────────────────────────────────────────")
    print(f" {title}")
    print(f"────────────────────────────────────────────────────────────────────────")


def show(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


with httpx.Client(base_url=BASE, timeout=15.0) as cli:
    # ── 1. REGISTER (Swagger > POST /v1/auth/register) ──────────────────
    step("1) POST /v1/auth/register — Test Kullanıcısı oluşturuluyor")
    print("Request:")
    show({**USER, "password": "********"})
    r = cli.post("/auth/register", json=USER)
    print(f"\n→ HTTP {r.status_code}")
    if r.status_code != 201:
        sys.exit(f"Beklenmeyen yanıt: {r.text}")
    register_payload = r.json()
    print("Response: doğrulama bağlantısı üretildi (kayıt pending durumda)")
    print(f"  email             : {register_payload['email']}")
    print(f"  verification_url  : {register_payload['verification_url']}")

    # ── 1b. VERIFY EMAIL ───────────────────────────────────────────────
    step("1b) POST /v1/auth/verify-email — e-postayı doğrula")
    r = cli.post(
        "/auth/verify-email",
        json={"token": register_payload["verification_token"]},
    )
    print(f"→ HTTP {r.status_code}")
    if r.status_code != 200:
        sys.exit(f"Doğrulama başarısız: {r.text}")
    tokens = r.json()
    print(
        f"  access_token_expires_at  : {tokens['access_token_expires_at']}"
    )
    print(
        f"  refresh_token_expires_at : {tokens['refresh_token_expires_at']}"
    )

    # ── 2. LOGIN (Swagger > POST /v1/auth/login) ────────────────────────
    step("2) POST /v1/auth/login — aynı kullanıcı ile giriş")
    r = cli.post(
        "/auth/login",
        json={"identifier": USER["email"], "password": USER["password"]},
    )
    print(f"→ HTTP {r.status_code}")
    if r.status_code != 200:
        sys.exit(f"Login başarısız: {r.text}")
    login_tokens = r.json()
    access = login_tokens["access_token"]
    print(f"access_token (kısa)   : {access[:48]}…")
    print(f"Bu token, Swagger 'Authorize' düğmesine 'Bearer {access[:8]}…' olarak girilir.")

    # ── 3. /me ──────────────────────────────────────────────────────────
    step("3) GET /v1/me — Bearer token ile profili oku")
    r = cli.get("/me", headers={"Authorization": f"Bearer {access}"})
    print(f"→ HTTP {r.status_code}")
    if r.status_code != 200:
        sys.exit(f"/me başarısız: {r.text}")
    show(r.json())

    # ── 4. Refresh rotation ─────────────────────────────────────────────
    step("4) POST /v1/auth/refresh — rotating refresh token")
    r = cli.post("/auth/refresh", json={"refresh_token": login_tokens["refresh_token"]})
    print(f"→ HTTP {r.status_code}")
    rotated = r.json()
    same = rotated["refresh_token"] == login_tokens["refresh_token"]
    print(f"refresh_token rotate edildi mi? {'EVET' if not same else 'HAYIR (HATA)'}")
    print(f"yeni access_token (kısa): {rotated['access_token'][:48]}…")

print("\n────────────────────────────────────────────────────────────────────────")
print(" [OK] Swagger üzerinden 'Test Kullanıcısı' akışı uçtan uca dogrulandı.")
print(f" Kullanıcı : {USER['username']}")
print(f" E-posta   : {USER['email']}")
print(f" Şifre     : {USER['password']}  (sadece bu çıktıda gözükür)")
print("────────────────────────────────────────────────────────────────────────")
