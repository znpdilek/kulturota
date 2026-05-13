"""
Smoke Test — Adım 4 Auth + Places (PRD §12)
==========================================
Bu script:

    1. /v1/auth/register ile **18+ doğrulamalı** bir test kullanıcısı oluşturur.
    2. /v1/auth/login ile JWT alır.
    3. /v1/me ile profili doğrular (access token).
    4. /v1/auth/refresh ile rotating refresh akışını test eder.
    5. Reuse detection: aynı refresh ikinci kez gönderildiğinde tüm token'ların
       revoke edildiğini doğrular.
    6. /v1/places, /v1/places/{id}, /v1/places/nearby uçlarını test eder.
    7. Negatif test: 18 yaş altı kayıt reddedilir (D3).

Çalıştırmak için sunucunun ``http://127.0.0.1:8000`` üzerinde ayakta olması gerekir.
"""

from __future__ import annotations

import io
import sys
import uuid
from datetime import date, timedelta
from typing import Any

import httpx

# Windows konsolunda Türkçe karakterler için UTF-8 zorla.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
API = f"{BASE_URL}/api/v1"


def banner(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def pretty(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        import json
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return str(payload)


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    test_email = f"asya+{suffix}@kulturrota.example.com"
    test_username = f"asya_{suffix}"
    test_password = "GuvenliSifre!2026"

    with httpx.Client(base_url=API, timeout=15.0) as client:
        # 1. REGISTER
        banner("1) POST /v1/auth/register (18+ + KVKK)")
        r = client.post(
            "/auth/register",
            json={
                "email": test_email,
                "username": test_username,
                "password": test_password,
                "display_name": "Asya · Smoke Test",
                "birth_date": "1997-04-15",
                "kvkk_consent": True,
                "locale": "tr",
            },
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 201, f"Beklenen 201, gelen {r.status_code}: {r.text}"
        register_response = r.json()
        print(pretty({
            "email": register_response["email"],
            "verification_url": register_response["verification_url"],
        }))

        # 1b. VERIFY EMAIL — token tüketildiğinde token çifti üretilir.
        banner("1b) POST /v1/auth/verify-email")
        r = client.post(
            "/auth/verify-email",
            json={"token": register_response["verification_token"]},
        )
        assert r.status_code == 200, f"Verify başarısız: {r.text}"
        tokens = r.json()
        access = tokens["access_token"]
        refresh = tokens["refresh_token"]
        print(f"access_token (ilk 40): {access[:40]}…")
        print(f"refresh_token (ilk 40): {refresh[:40]}…")

        # 2. UNDERAGE NEGATIVE
        banner("2) NEGATİF: 17 yaş kayıt reddi (D3)")
        underage = (date.today() - timedelta(days=15 * 365)).isoformat()
        r = client.post(
            "/auth/register",
            json={
                "email": f"reddedilen+{uuid.uuid4().hex[:6]}@example.com",
                "username": f"u{uuid.uuid4().hex[:6]}",
                "password": "Guvenli!Sifre1",
                "birth_date": underage,
                "kvkk_consent": True,
            },
        )
        print(f"-> {r.status_code}")
        assert r.status_code in (400, 422), "Yaş kontrolü çalışmalı"
        print(pretty(r.json()))

        # 3. LOGIN
        banner("3) POST /v1/auth/login")
        r = client.post(
            "/auth/login",
            json={"identifier": test_username, "password": test_password},
        )
        assert r.status_code == 200, r.text
        login_tokens = r.json()
        print(f"-> 200  access[…]={login_tokens['access_token'][:30]}")

        # 4. /me
        banner("4) GET /v1/me  (access token ile)")
        r = client.get("/me", headers={"Authorization": f"Bearer {access}"})
        assert r.status_code == 200, r.text
        me = r.json()
        print(pretty({
            "id": me["id"],
            "email": me["email"],
            "username": me["username"],
            "role": me["role"],
            "birth_date": me["birth_date"],
            "kvkk_consent_at": me["kvkk_consent_at"],
        }))

        # 5. REFRESH (rotation)
        banner("5) POST /v1/auth/refresh (rotation)")
        r = client.post("/auth/refresh", json={"refresh_token": refresh})
        assert r.status_code == 200, r.text
        rotated = r.json()
        new_refresh = rotated["refresh_token"]
        assert new_refresh != refresh, "Refresh rotate edilmedi!"
        print(f"-> 200  yeni refresh[…]={new_refresh[:30]}")

        # 6. REUSE DETECTION: eski refresh tekrar kullanılırsa hata + tüm token'lar revoke
        banner("6) POST /v1/auth/refresh — REUSE DETECTION (eski token tekrar)")
        r = client.post("/auth/refresh", json={"refresh_token": refresh})
        print(f"-> {r.status_code}")
        assert r.status_code == 401, "Reuse detection 401 dönmeli"
        print(pretty(r.json()))

        # Yeni alınan refresh de artık iptal edilmiş olmalı.
        r = client.post("/auth/refresh", json={"refresh_token": new_refresh})
        print(f"  -> (yeni token'la deneme) {r.status_code}")
        assert r.status_code == 401, "Reuse sonrası diğer token da revoke edilmeliydi"

        # 7. RE-LOGIN → temiz token çifti
        banner("7) Yeniden login")
        r = client.post(
            "/auth/login",
            json={"identifier": test_email, "password": test_password},
        )
        assert r.status_code == 200, r.text
        fresh = r.json()
        access2 = fresh["access_token"]
        refresh2 = fresh["refresh_token"]

        # 8. PLACES — list
        banner("8) GET /v1/places?limit=3")
        r = client.get("/places", params={"limit": 3})
        print(f"-> {r.status_code}")
        assert r.status_code == 200, r.text
        body = r.json()
        print(f"toplam: {body['meta']['total']}, dönen: {len(body['items'])}")
        if body["items"]:
            first = body["items"][0]
            print(pretty({
                "id": first["id"],
                "slug": first["slug"],
                "isim": first["isim"],
                "kategori": first["kategori"],
            }))

            # 9. PLACES — detail
            banner("9) GET /v1/places/{id}")
            r = client.get(f"/places/{first['id']}")
            assert r.status_code == 200, r.text
            detail = r.json()
            print(pretty({
                "slug": detail["slug"],
                "isim": detail["isim"],
                "kaynak_atif": detail.get("kaynak_atif"),
                "aciklama_source": detail.get("aciklama_source"),
            }))

            # 10. NEARBY
            banner("10) GET /v1/places/nearby (PostGIS ST_DWithin)")
            coord = first["koordinat"]
            r = client.get(
                "/places/nearby",
                params={
                    "lat": coord["lat"],
                    "lng": coord["lng"],
                    "radius": 2000,
                    "limit": 5,
                },
            )
            assert r.status_code == 200, r.text
            nearby = r.json()
            print(f"origin={nearby['origin']}, radius={nearby['radius_m']}m, sonuç={len(nearby['items'])}")
            for item in nearby["items"][:3]:
                print(f"  • {item['slug']:<40} ({item['distance_m']:.1f} m)")

        # 11. BBOX filtre
        banner("11) GET /v1/places?bbox=İzmir")
        r = client.get(
            "/places",
            params={"bbox": "26.0,38.0,28.5,39.0", "limit": 2},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        print(f"İzmir bbox toplam: {body['meta']['total']}")

        # 12. LOGOUT
        banner("12) POST /v1/auth/logout")
        r = client.post("/auth/logout", json={"refresh_token": refresh2})
        print(f"-> {r.status_code}")
        assert r.status_code == 204, r.text

        # 13. Unauthorized check
        banner("13) GET /v1/me (token'siz)")
        r = client.get("/me")
        print(f"-> {r.status_code}")
        assert r.status_code == 401, r.text
        print(pretty(r.json()))

    banner("[OK] Tum smoke testleri basariyla tamamlandi")
    return 0


if __name__ == "__main__":
    sys.exit(main())
