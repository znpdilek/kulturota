"""
Smoke Test — Adım 5 Profil + KVKK / GDPR Uyumu (PRD §17.3)
==========================================================

Bu script, Adım 5 ile gelen üç ucu uçtan uca test eder:

    1.  Register → token al
    2.  GET /v1/users/me                  → profil okuma
    3.  PUT /v1/users/me                  → display_name + locale + avatar güncelle
    4.  PUT /v1/users/me                  → bilinmeyen alan (extra='forbid') → 422
    5.  PUT /v1/users/me                  → boş payload → 422
    6.  GET /v1/users/me/export-data      → şema + Content-Disposition + KVKK alanları
    7.  DELETE /v1/users/me               → hatalı onay metni → 422
    8.  DELETE /v1/users/me               → doğru onay → 200 + audit özeti
    9.  Login (silinen e-posta)           → 401
    10. GET /v1/users/me (eski access)    → 401 (auth.user_not_found)

Çalıştırma::

    uvicorn app.main:app --reload --port 8000
    python scripts/smoke_kvkk.py

Çıktı, JSON paketinin minimum sözleşmesinin (PRD §17.3) tutturulduğunu
gösterir; eksik kalan herhangi bir veri kategorisi varsa ``assert`` ile
düşer.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from datetime import date, datetime
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
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return str(payload)


# --- Beklenen JSON paket sözleşmesi (PRD §17.3) ----------------------------
EXPECTED_TOP_LEVEL_KEYS = {
    "metadata",
    "profile",
    "consents",
    "sessions",
    "routes",
    "route_stops",
    "photos",
    "reviews",
    "favorites",
    "follows",
    "route_likes",
    "route_comments",
    "reports",
    "audit_log",
}
EXPECTED_METADATA_KEYS = {
    "schema_version",
    "generated_at",
    "user_id",
    "legal_basis",
    "format",
    "notes",
}
EXPECTED_PROFILE_KEYS = {
    "id",
    "email",
    "username",
    "display_name",
    "avatar_url",
    "role",
    "locale",
    "birth_date",
    "email_verified_at",
    "mfa_enabled",
    "is_active",
    "last_login_at",
    "created_at",
    "updated_at",
}
EXPECTED_CONSENT_KEYS = {
    "kvkk_consent_at",
    "min_registration_age_years",
    "policy_reference",
}


def main() -> int:
    suffix = uuid.uuid4().hex[:8]
    email = f"kvkk+{suffix}@kulturrota.example.com"
    username = f"kvkk_{suffix}"
    password = "GuvenliSifre!2026"

    with httpx.Client(base_url=API, timeout=15.0) as client:
        # ----------------------------------------------------------------
        # 1. REGISTER
        # ----------------------------------------------------------------
        banner("1) POST /v1/auth/register (PRD §17.3 18+ + KVKK)")
        r = client.post(
            "/auth/register",
            json={
                "email": email,
                "username": username,
                "password": password,
                "display_name": "KVKK Smoke",
                "birth_date": "1995-06-20",
                "kvkk_consent": True,
                "locale": "tr",
            },
        )
        assert r.status_code == 201, f"register: {r.status_code} {r.text}"
        register_body = r.json()
        # PRD §17.3 — e-posta doğrulama akışı zorunlu.
        r = client.post(
            "/auth/verify-email",
            json={"token": register_body["verification_token"]},
        )
        assert r.status_code == 200, f"verify-email: {r.status_code} {r.text}"
        tokens = r.json()
        access = tokens["access_token"]
        print(f"-> 201 + verify  access[…]={access[:30]}")

        auth = {"Authorization": f"Bearer {access}"}

        # ----------------------------------------------------------------
        # 2. GET /v1/users/me
        # ----------------------------------------------------------------
        banner("2) GET /v1/users/me  (yeni rota)")
        r = client.get("/users/me", headers=auth)
        assert r.status_code == 200, r.text
        me = r.json()
        assert me["email"].lower() == email.lower()
        assert me["username"] == username
        assert me["display_name"] == "KVKK Smoke"
        assert me["locale"] == "tr"
        assert me["kvkk_consent_at"] is not None
        print(pretty({k: me[k] for k in ("email", "username", "display_name", "locale")}))

        # ----------------------------------------------------------------
        # 3. PUT /v1/users/me — birden çok alan güncelle
        # ----------------------------------------------------------------
        banner("3) PUT /v1/users/me  (display_name + locale + avatar_url)")
        r = client.put(
            "/users/me",
            headers=auth,
            json={
                "display_name": "Asya Araştırmacı",
                "locale": "tr-TR",
                "avatar_url": "https://cdn.example.com/avatars/asya.png",
            },
        )
        assert r.status_code == 200, f"put me: {r.status_code} {r.text}"
        updated = r.json()
        assert updated["display_name"] == "Asya Araştırmacı"
        assert updated["locale"] == "tr-tr"  # normalize edilmiş olmalı
        assert updated["avatar_url"] == "https://cdn.example.com/avatars/asya.png"
        print(pretty({
            "display_name": updated["display_name"],
            "locale": updated["locale"],
            "avatar_url": updated["avatar_url"],
        }))

        # ----------------------------------------------------------------
        # 4. PUT /v1/users/me — yasak alan (extra='forbid')
        # ----------------------------------------------------------------
        banner("4) NEGATİF: PUT /v1/users/me  (yasak alan: email)")
        r = client.put(
            "/users/me",
            headers=auth,
            json={"email": "yeni@adres.com"},
        )
        assert r.status_code == 422, f"422 bekleniyordu, geldi: {r.status_code}"
        body = r.json()
        assert body["status"] == 422 and body["code"] == "validation.failed"
        print(f"-> {r.status_code}  code={body['code']}")

        # ----------------------------------------------------------------
        # 5. PUT /v1/users/me — boş payload
        # ----------------------------------------------------------------
        banner("5) NEGATİF: PUT /v1/users/me  (boş gövde)")
        r = client.put("/users/me", headers=auth, json={})
        assert r.status_code == 422, r.text
        body = r.json()
        assert body["status"] == 422
        print(f"-> {r.status_code}  validation.failed")

        # ----------------------------------------------------------------
        # 6. GET /v1/users/me/export-data
        # ----------------------------------------------------------------
        banner("6) GET /v1/users/me/export-data  (KVKK paket sözleşmesi)")
        r = client.get("/users/me/export-data", headers=auth)
        assert r.status_code == 200, r.text

        cd = r.headers.get("content-disposition", "")
        assert cd.startswith("attachment;"), f"Content-Disposition: {cd!r}"
        assert username in cd
        assert ".json" in cd
        assert r.headers.get("x-kvkk-schema-version") == "1.0"
        assert r.headers.get("cache-control") == "no-store"

        export = r.json()
        missing_top = EXPECTED_TOP_LEVEL_KEYS - set(export.keys())
        assert not missing_top, f"Eksik üst düzey alanlar: {missing_top}"

        meta = export["metadata"]
        missing_meta = EXPECTED_METADATA_KEYS - set(meta.keys())
        assert not missing_meta, f"Eksik metadata alanları: {missing_meta}"
        assert meta["schema_version"] == "1.0"
        assert meta["format"] == "application/json"
        # generated_at ISO-8601 olmalı
        generated_at = datetime.fromisoformat(meta["generated_at"])
        assert generated_at.tzinfo is not None, "generated_at tz-aware olmalı"
        assert "KVKK" in meta["legal_basis"] and "GDPR" in meta["legal_basis"]

        prof = export["profile"]
        missing_profile = EXPECTED_PROFILE_KEYS - set(prof.keys())
        assert not missing_profile, f"Eksik profile alanları: {missing_profile}"
        assert prof["email"].lower() == email.lower()
        assert prof["username"] == username
        assert prof["display_name"] == "Asya Araştırmacı"
        assert prof["locale"] == "tr-tr"
        assert "password" not in prof and "password_hash" not in prof, (
            "Şifre hash'i export paketinde olmamalı"
        )
        # birth_date ISO-8601 (date)
        date.fromisoformat(prof["birth_date"])

        consents = export["consents"]
        missing_consent = EXPECTED_CONSENT_KEYS - set(consents.keys())
        assert not missing_consent, f"Eksik consent alanları: {missing_consent}"
        assert consents["kvkk_consent_at"] is not None
        assert consents["min_registration_age_years"] == 18

        # Sessions: en az 1 (kayıt anında üretilen refresh) ve TOKEN DEĞERİ
        # paketin hiçbir yerinde olmamalı (güvenlik).
        sessions = export["sessions"]
        assert isinstance(sessions, list) and len(sessions) >= 1, (
            "En az bir refresh token meta'sı beklenir"
        )
        first_session = sessions[0]
        for required in ("jti", "ip", "user_agent", "created_at", "expires_at"):
            assert required in first_session, f"sessions[].{required} eksik"
        # JWT format heuristic: header.payload.signature ⇒ 2 nokta içerir,
        # eyJ… ile başlar. Hiçbir session alanında bunun görünmediğini
        # doğrula (jti UUID olduğu için saymıyor).
        full_dump = json.dumps(sessions, ensure_ascii=False)
        assert "eyJ" not in full_dump, (
            "Refresh token JWT değeri export paketinde olmamalı (güvenlik ihlali)"
        )

        # UGC kategorileri: yeni kullanıcıda boş, ama anahtarlar olmalı
        for empty_key in (
            "routes",
            "route_stops",
            "photos",
            "reviews",
            "favorites",
            "route_likes",
            "route_comments",
            "reports",
        ):
            assert isinstance(export[empty_key], list), (
                f"{empty_key} liste olmalı"
            )

        # Audit log: PUT /me sonrası en az 3 kayıt
        # (display_name, locale, avatar_url için ayrı satırlar).
        audit_log = export["audit_log"]
        assert isinstance(audit_log, list)
        update_entries = [a for a in audit_log if a["action"] == "profile.update"]
        assert len(update_entries) >= 3, (
            f"profile.update audit kayıtları yetersiz: {len(update_entries)}"
        )
        changed_fields = {a["field"] for a in update_entries}
        for expected_field in ("display_name", "locale", "avatar_url"):
            assert expected_field in changed_fields, (
                f"audit_log içinde {expected_field} değişimi yok"
            )

        follows = export["follows"]
        assert "following" in follows and "followers" in follows

        print(
            "OK  schema_version={sv}  sessions={s}  audit_log={a}  "
            "(profile.update={pu})".format(
                sv=meta["schema_version"],
                s=len(sessions),
                a=len(audit_log),
                pu=len(update_entries),
            )
        )
        print(
            "[KVKK] paket Türkçe karakterleri koruyor:",
            prof["display_name"],
        )

        # ----------------------------------------------------------------
        # 7. DELETE /v1/users/me — hatalı onay
        # ----------------------------------------------------------------
        banner("7) NEGATİF: DELETE /v1/users/me  (yanlış onay metni)")
        r = client.request(
            "DELETE",
            "/users/me",
            headers=auth,
            json={"confirm": "evet sil"},
        )
        assert r.status_code == 422, r.text
        print(f"-> {r.status_code}  validation.failed")

        # ----------------------------------------------------------------
        # 8. DELETE /v1/users/me — doğru onay
        # ----------------------------------------------------------------
        banner("8) DELETE /v1/users/me  (doğru onay)")
        r = client.request(
            "DELETE",
            "/users/me",
            headers=auth,
            json={
                "confirm": "HESABIMI KALICI OLARAK SİL",
                "reason": "Smoke test temizliği",
            },
        )
        assert r.status_code == 200, f"delete: {r.status_code} {r.text}"
        result = r.json()
        assert "user_id" in result
        assert "deleted_at" in result
        deleted_relations = result["deleted_relations"]
        assert "refresh_tokens" in deleted_relations
        assert deleted_relations["refresh_tokens"] >= 1, (
            "En az 1 refresh token kaydı silinmeliydi"
        )
        assert result["audit_log_id"] is not None
        print(pretty({
            "user_id": result["user_id"],
            "deleted_at": result["deleted_at"],
            "deleted_relations": deleted_relations,
            "audit_log_id": result["audit_log_id"],
        }))

        # ----------------------------------------------------------------
        # 9. Login dene — kullanıcı yok
        # ----------------------------------------------------------------
        banner("9) Silinen kullanıcı ile login dene")
        r = client.post(
            "/auth/login",
            json={"identifier": email, "password": password},
        )
        assert r.status_code == 401, r.text
        body = r.json()
        assert body["code"] == "auth.invalid_credentials"
        print(f"-> {r.status_code}  {body['code']}")

        # ----------------------------------------------------------------
        # 10. Eski access token artık çalışmamalı
        # ----------------------------------------------------------------
        banner("10) Silinen kullanıcının access token'ı")
        r = client.get("/users/me", headers=auth)
        assert r.status_code == 401, r.text
        body = r.json()
        assert body["code"] in ("auth.user_not_found", "auth.invalid_token")
        print(f"-> {r.status_code}  {body['code']}")

    banner("[OK] Adim 5 (Profil + KVKK / GDPR) smoke testleri tamam.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
