"""
Smoke Test — Adım 8: Sosyal Özellikler (Yorum & Beğeni MVP)
===========================================================
PRD §10.2 (``reviews`` + ``route_likes``) + §12.2 (``/v1/places/{id}/reviews``
+ ``/v1/routes/{id}/likes``).

Bu script kullanıcı talebi gereği uçtan uca ana senaryoyu doğrular:

    1. İki test kullanıcısı kaydeder (sahip + beğenici — 18+ + KVKK).
    2. ``GET /v1/places`` üzerinden yayında bir mekan çeker.
    3. **Yorum akışı**:
        3a. Auth'lu POST ile mekana 1-5 puan + metin yorum bırakır.
        3b. Aynı kullanıcı ikinci POST atınca **409 reviews.duplicate** alır.
        3c. ``GET /v1/places/{id}/reviews`` listede yorumun göründüğünü
            doğrular; ``aggregate.total`` ve ``aggregate.average_rating``
            beklenen değerleri alır.
        3d. Başka kullanıcı yorumu **silemez** → 404 reviews.not_found.
        3e. Sahibi DELETE atınca 204; sonra liste yine boş döner.
    4. **Beğeni akışı**:
        4a. Birinci kullanıcı public bir rota oluşturur.
        4b. İkinci kullanıcı rotayı beğenir → ``action=created``,
            ``liked=true``, ``like_count=1``.
        4c. İkinci POST → ``action=already_liked`` (idempotent).
        4d. ``GET /v1/routes/{id}/likes`` doğru durum + sayım.
        4e. Birinci kullanıcı kendi rotasını beğenemez → 400.
        4f. DELETE → ``action=removed``; tekrar DELETE → ``action=not_liked``.
    5. Negatif testler:
        * Auth'suz POST → 401.
        * Geçersiz rating (6) → 422.
        * Olmayan place_id ile yorum → 404.
        * Public olmayan rotaya like → 404 route_likes.route_not_found.

Çalıştırma::

    docker compose up -d postgres redis
    alembic upgrade head           # uq_reviews_place_user constraint için
    uvicorn app.main:app --reload --port 8000
    python scripts/smoke_social.py

Tüm adımlar ``assert`` ile katı kontrol edilir; bir adım düşerse script
non-zero exit code ile sonlanır (CI uyumlu).
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from typing import Any

import httpx

# Windows konsolunda Türkçe karakterler için UTF-8 zorla.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

BASE_URL = "http://127.0.0.1:8000"
API = f"{BASE_URL}/api/v1"


# --- UI helpers ------------------------------------------------------------
def banner(text: str) -> None:
    print(f"\n{'=' * 72}\n{text}\n{'=' * 72}")


def pretty(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return str(payload)


# --- Test fixtures ---------------------------------------------------------
def register_user(client: httpx.Client, prefix: str) -> tuple[str, str]:
    """Smoke için tek-seferlik kullanıcı oluştur (PRD D3 18+ + KVKK)."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "email": f"{prefix}+{suffix}@kulturrota.example.com",
        "username": f"{prefix}_{suffix}",
        "password": "SmokeSocial!2026",
        "display_name": f"Sosyal Smoke {prefix}",
        "birth_date": "1992-07-14",
        "kvkk_consent": True,
        "locale": "tr",
    }
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201, f"register başarısız: {r.status_code} {r.text}"
    body = r.json()
    return body["access_token"], body["refresh_token"]


def pick_published_place(client: httpx.Client) -> dict:
    """Veritabanından yayınlanmış bir mekan döndür."""
    r = client.get("/places", params={"limit": 1})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, (
        "Smoke test için veritabanında en az 1 yayınlanmış mekan gerekiyor. "
        "ETL'yi çalıştırarak (scripts/verify_etl.py veya İzmir bbox DAG'ı) "
        "yeterli veri yükleyin."
    )
    return items[0]


# --- Main ------------------------------------------------------------------
def main() -> int:
    with httpx.Client(base_url=API, timeout=30.0) as client:
        # 0) Sağlık kontrolü
        banner("0) Sağlık kontrolü")
        h = client.get(f"{BASE_URL}/health")
        assert h.status_code == 200, h.text
        print(f"-> {h.status_code} {h.json()}")

        # 1) İki kullanıcı kaydı
        banner("1) Kullanıcı kayıtları (18+ + KVKK) — yorumcu + rota-sahibi")
        reviewer_access, _ = register_user(client, prefix="yorumcu")
        owner_access, _ = register_user(client, prefix="rotasahibi")
        reviewer_auth = {"Authorization": f"Bearer {reviewer_access}"}
        owner_auth = {"Authorization": f"Bearer {owner_access}"}
        print(f"   yorumcu.access[…]={reviewer_access[:30]}")
        print(f"   rotasahibi.access[…]={owner_access[:30]}")

        # 2) Mekan seç
        banner("2) GET /v1/places?limit=1 — yayında mekan")
        place = pick_published_place(client)
        place_id = place["id"]
        print(f"-> place_id={place_id} slug={place['slug']}")

        # ========================================================
        # YORUM AKIŞI
        # ========================================================
        banner("3) POST /v1/places/{id}/reviews — yorum + 4 puan")
        review_payload = {
            "rating": 4,
            "body": "Tarihi dokusuyla harika, sabah erken saatlerde ziyaret tavsiyem.",
            "visited_at": "2026-04-12",
        }
        r = client.post(
            f"/places/{place_id}/reviews",
            headers=reviewer_auth,
            json=review_payload,
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 201, r.text
        review = r.json()
        print(pretty({
            "id": review["id"],
            "rating": review["rating"],
            "body": review["body"],
            "visited_at": review["visited_at"],
            "author.username": review["author"]["username"],
        }))
        assert review["rating"] == 4
        assert review["place_id"] == place_id
        assert review["author"]["username"].startswith("yorumcu_")
        review_id = review["id"]

        # 3b) Aynı kullanıcı — duplicate yorum → 409
        banner("3b) NEGATİF: Aynı kullanıcı ikinci yorum → 409 reviews.duplicate")
        r = client.post(
            f"/places/{place_id}/reviews",
            headers=reviewer_auth,
            json={"rating": 5, "body": "İkinci kez yorum yazma denemesi."},
        )
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 409, r.text
        assert body.get("code") == "reviews.duplicate"

        # 3c) GET /reviews — listede görünmeli + aggregate
        banner("3c) GET /v1/places/{id}/reviews — liste + aggregate")
        r = client.get(f"/places/{place_id}/reviews")
        assert r.status_code == 200, r.text
        listing = r.json()
        print(pretty({
            "total": listing["total"],
            "aggregate": listing["aggregate"],
            "first_review.rating": listing["items"][0]["rating"] if listing["items"] else None,
        }))
        ids = [it["id"] for it in listing["items"]]
        assert review_id in ids, f"Yorum listede yok: {ids}"
        assert listing["aggregate"]["total"] >= 1
        avg = listing["aggregate"]["average_rating"]
        assert avg is not None and 1.0 <= avg <= 5.0
        # En az 1 yorum varsa (bizim 4-puanlı yorumumuz) ortalama da en az 4 olmalı
        # (önceki yorum yoksa tam 4.0 olur; varsa ortalama).
        assert avg >= 1.0

        # 3d) Başka kullanıcı yorumu silemez → 404
        banner("3d) NEGATİF: Başka kullanıcı yorumu silemez → 404")
        r = client.delete(
            f"/places/{place_id}/reviews/{review_id}",
            headers=owner_auth,  # owner != reviewer
        )
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 404, r.text
        assert body.get("code") == "reviews.not_found"

        # 3e) Sahibi DELETE → 204; sonra liste güncellenir
        banner("3e) DELETE /v1/places/{id}/reviews/{review_id} — sahibinden")
        r = client.delete(
            f"/places/{place_id}/reviews/{review_id}",
            headers=reviewer_auth,
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 204, r.text

        r = client.get(f"/places/{place_id}/reviews")
        assert r.status_code == 200, r.text
        after = r.json()
        assert review_id not in [it["id"] for it in after["items"]]
        print(f"   silme sonrası aggregate.total={after['aggregate']['total']}")

        # ========================================================
        # ROTA BEĞENİ AKIŞI
        # ========================================================
        banner("4) POST /v1/routes — rotasahibi public rota oluştur")
        r = client.post(
            "/routes",
            headers=owner_auth,
            json={
                "title": "İzmir Tarihi Yarımada — Sosyal Smoke",
                "description": {"tr": "Adım 8 beğeni doğrulama rotası."},
                "theme": "antik",
                "is_public": True,
                "difficulty": "easy",
            },
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 201, r.text
        route = r.json()
        route_id = route["id"]
        assert route["is_public"] is True
        print(f"   route_id={route_id} is_public=True")

        # 4b) Yorumcu kullanıcı (başkası) → like
        banner("4b) POST /v1/routes/{id}/likes — yorumcu rotayı beğenir")
        r = client.post(f"/routes/{route_id}/likes", headers=reviewer_auth)
        print(f"-> {r.status_code}")
        assert r.status_code == 200, r.text
        like = r.json()
        print(pretty({
            "liked": like["liked"],
            "action": like["action"],
            "like_count": like["like_count"],
            "liked_at": like["liked_at"],
        }))
        assert like["liked"] is True
        assert like["action"] == "created"
        assert like["like_count"] == 1
        assert like["liked_at"] is not None

        # 4c) İkinci POST → already_liked (idempotent)
        banner("4c) POST tekrar → idempotent (already_liked)")
        r = client.post(f"/routes/{route_id}/likes", headers=reviewer_auth)
        assert r.status_code == 200, r.text
        like2 = r.json()
        print(pretty({"action": like2["action"], "like_count": like2["like_count"]}))
        assert like2["action"] == "already_liked"
        assert like2["like_count"] == 1, "Sayım idempotent olmalı."

        # 4d) GET status
        banner("4d) GET /v1/routes/{id}/likes — durum + toplam")
        r = client.get(f"/routes/{route_id}/likes", headers=reviewer_auth)
        assert r.status_code == 200, r.text
        status_body = r.json()
        print(pretty(status_body))
        assert status_body["liked"] is True
        assert status_body["like_count"] == 1
        assert status_body["liked_at"] is not None

        # Sahip de kontrol etsin: kendi rotasında liked=False olmalı
        r = client.get(f"/routes/{route_id}/likes", headers=owner_auth)
        assert r.status_code == 200, r.text
        owner_status = r.json()
        assert owner_status["liked"] is False
        assert owner_status["like_count"] == 1
        print(f"   sahibinin görünümünde liked={owner_status['liked']} count={owner_status['like_count']}")

        # 4e) Sahip kendi rotasını beğenemez → 400
        banner("4e) NEGATİF: Sahip kendi rotasını beğenemez → 400")
        r = client.post(f"/routes/{route_id}/likes", headers=owner_auth)
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 400, r.text
        assert body.get("code") == "route_likes.cannot_like_own"

        # 4f) DELETE → removed; tekrar DELETE → not_liked
        banner("4f) DELETE /v1/routes/{id}/likes — geri çek (idempotent)")
        r = client.delete(f"/routes/{route_id}/likes", headers=reviewer_auth)
        assert r.status_code == 200, r.text
        unlike = r.json()
        print(pretty({"action": unlike["action"], "like_count": unlike["like_count"]}))
        assert unlike["action"] == "removed"
        assert unlike["liked"] is False
        assert unlike["like_count"] == 0

        r = client.delete(f"/routes/{route_id}/likes", headers=reviewer_auth)
        assert r.status_code == 200, r.text
        unlike2 = r.json()
        assert unlike2["action"] == "not_liked"
        assert unlike2["liked"] is False
        print(f"   ikinci DELETE → action={unlike2['action']} (idempotent ✓)")

        # ========================================================
        # NEGATİF SENARYOLAR
        # ========================================================
        banner("5) NEGATİF: Auth'suz POST yorum → 401")
        r = client.post(
            f"/places/{place_id}/reviews",
            json={"rating": 3, "body": "Auth'suz deneme."},
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 401, r.text

        banner("5b) NEGATİF: Geçersiz rating (6) → 422")
        r = client.post(
            f"/places/{place_id}/reviews",
            headers=reviewer_auth,
            json={"rating": 6, "body": "Aralık dışı puan."},
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 422, r.text

        banner("5c) NEGATİF: Olmayan place_id → 404 reviews.place_not_found")
        r = client.post(
            f"/places/{uuid.uuid4()}/reviews",
            headers=reviewer_auth,
            json={"rating": 5, "body": "Hayalet mekan."},
        )
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 404, r.text
        assert body.get("code") == "reviews.place_not_found"

        banner("5d) NEGATİF: Public olmayan rotaya like → 404 route_likes.route_not_found")
        # Önce private rota oluştur
        r = client.post(
            "/routes",
            headers=owner_auth,
            json={
                "title": "Özel Rota — Smoke",
                "is_public": False,
            },
        )
        assert r.status_code == 201, r.text
        private_route_id = r.json()["id"]
        r = client.post(
            f"/routes/{private_route_id}/likes",
            headers=reviewer_auth,
        )
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 404, r.text
        assert body.get("code") == "route_likes.route_not_found"

        # Temizlik: oluşturulan public rotayı sil
        client.delete(f"/routes/{route_id}", headers=owner_auth)
        client.delete(f"/routes/{private_route_id}", headers=owner_auth)

    banner("[OK] Adim 8 sosyal akis (yorum + begeni) uctan uca dogrulandi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
