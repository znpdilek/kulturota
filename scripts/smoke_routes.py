"""
Smoke Test — Adım 7: Rota Yönetimi (Core MVP)
=============================================
PRD §10.2 (``routes`` + ``route_stops``) + §12.2 (``/v1/routes`` ailesi).

Bu script ana kullanıcı senaryosunu (kullanıcı talebi gereği) uçtan uca
doğrular:

    1. Yeni bir test kullanıcısı kaydeder (18+ + KVKK — PRD D3).
    2. ``GET /v1/places`` üzerinden **iki farklı** yayınlanmış mekan çeker.
    3. ``POST /v1/routes`` ile yeni bir rota oluşturur.
    4. ``GET /v1/routes`` listesinde rotanın göründüğünü doğrular.
    5. ``POST /v1/routes/{id}/stops`` ile **iki farklı mekanı** sıralı olarak
       rotaya ekler (order_index 0 ve 1 otomatik atanır).
    6. ``GET /v1/routes/{id}`` çağrısının dönüş şemasını kontrol eder:
         * ``stops`` ``order_index`` artan yönde sıralı.
         * Her stop'ta mekanın **isim + koordinat** bilgisi inline.
    7. ``PUT /v1/routes/{id}`` ile başlık/temayı günceller.
    8. Negatif senaryolar:
         * Auth'suz POST → 401.
         * Aynı ``order_index`` çakışması → 409.
         * Olmayan ``place_id`` ile stop ekleme → 404.
         * Başkasının rotasına erişim (ikinci kullanıcı) → 404.
    9. ``DELETE`` ile bir stop ve ardından rotanın tamamını siler.

Çalıştırma::

    docker compose up -d postgres redis
    uvicorn app.main:app --reload --port 8000
    python scripts/smoke_routes.py

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

# Windows konsolunda Türkçe karakterler için UTF-8 zorla (smoke_media örneği).
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
        "password": "SmokeRota!2026",
        "display_name": f"Rota Smoke {prefix}",
        "birth_date": "1995-03-22",
        "kvkk_consent": True,
        "locale": "tr",
    }
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201, f"register başarısız: {r.status_code} {r.text}"
    body = r.json()
    return body["access_token"], body["refresh_token"]


def pick_two_published_places(client: httpx.Client) -> tuple[dict, dict]:
    """Veritabanından iki farklı yayınlanmış mekan döndür."""
    r = client.get("/places", params={"limit": 5})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) >= 2, (
        "Smoke test için veritabanında en az 2 yayınlanmış mekan gerekiyor. "
        "ETL'yi çalıştırarak (scripts/verify_etl.py veya İzmir bbox DAG'ı) "
        "yeterli veri yükleyin."
    )
    return items[0], items[1]


# --- Main ------------------------------------------------------------------
def main() -> int:
    with httpx.Client(base_url=API, timeout=30.0) as client:
        # 0) Sağlık kontrolü
        banner("0) Sağlık kontrolü")
        h = client.get(f"{BASE_URL}/health")
        assert h.status_code == 200, h.text
        print(f"-> {h.status_code} {h.json()}")

        # 1) Birincil kullanıcı kaydı
        banner("1) Kullanıcı kaydı (18+ + KVKK) — birincil")
        access, _refresh = register_user(client, prefix="rotaci")
        auth = {"Authorization": f"Bearer {access}"}
        print(f"-> access[…]={access[:30]}")

        # 2) İki mekan seç
        banner("2) GET /v1/places — iki farklı yayınlanmış mekan")
        place_a, place_b = pick_two_published_places(client)
        place_a_id = place_a["id"]
        place_b_id = place_b["id"]
        print(f"   place_A.id={place_a_id} slug={place_a['slug']}")
        print(f"   place_B.id={place_b_id} slug={place_b['slug']}")
        assert place_a_id != place_b_id, "İki farklı mekan gerekli."

        # 3) Yeni rota oluştur
        banner("3) POST /v1/routes — yeni rota")
        create_body = {
            "title": "İzmir Tarihi Yarımada — Smoke",
            "description": {"tr": "Adım 7 doğrulama rotası."},
            "theme": "antik",
            "is_public": False,
            "difficulty": "easy",
        }
        r = client.post("/routes", headers=auth, json=create_body)
        print(f"-> {r.status_code}")
        assert r.status_code == 201, r.text
        route = r.json()
        route_id = route["id"]
        print(pretty({
            "id": route["id"],
            "title": route["title"],
            "owner_id": route["owner_id"],
            "is_public": route["is_public"],
            "difficulty": route["difficulty"],
            "stop_count": route["stop_count"],
        }))
        assert route["stop_count"] == 0
        assert route["owner_id"] is not None
        assert route["difficulty"] == "easy"

        # 4) Listede görünüyor mu?
        banner("4) GET /v1/routes — kendi rotalarım")
        r = client.get("/routes", headers=auth)
        assert r.status_code == 200, r.text
        listing = r.json()
        ids = [it["id"] for it in listing["items"]]
        assert route_id in ids, f"Yeni rota listede yok: {ids}"
        print(f"-> {r.status_code}, total={listing['total']}, has_more={listing['has_more']}")

        # 5) İki mekanı sıralı şekilde rotaya ekle
        banner("5) POST /v1/routes/{id}/stops — Mekan A (order auto)")
        r = client.post(
            f"/routes/{route_id}/stops",
            headers=auth,
            json={
                "place_id": place_a_id,
                "planned_duration_min": 45,
                "notes": "İlk durak — sabah ziyareti.",
            },
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 201, r.text
        stop_a = r.json()
        print(pretty({
            "id": stop_a["id"],
            "order_index": stop_a["order_index"],
            "place.id": stop_a["place"]["id"],
            "place.isim": stop_a["place"]["isim"],
            "place.koordinat": stop_a["place"]["koordinat"],
        }))
        assert stop_a["order_index"] == 0, f"İlk stop order_index=0 bekleniyordu: {stop_a['order_index']}"
        assert stop_a["place"]["id"] == place_a_id
        assert "lat" in stop_a["place"]["koordinat"] and "lng" in stop_a["place"]["koordinat"]
        assert isinstance(stop_a["place"]["isim"], dict) and len(stop_a["place"]["isim"]) > 0

        banner("5b) POST /v1/routes/{id}/stops — Mekan B (order auto = 1)")
        r = client.post(
            f"/routes/{route_id}/stops",
            headers=auth,
            json={
                "place_id": place_b_id,
                "planned_duration_min": 60,
                "notes": "İkinci durak — öğle sonrası.",
            },
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 201, r.text
        stop_b = r.json()
        print(pretty({
            "id": stop_b["id"],
            "order_index": stop_b["order_index"],
            "place.id": stop_b["place"]["id"],
            "place.isim": stop_b["place"]["isim"],
            "place.koordinat": stop_b["place"]["koordinat"],
        }))
        assert stop_b["order_index"] == 1, f"İkinci stop order_index=1 bekleniyordu: {stop_b['order_index']}"
        assert stop_b["place"]["id"] == place_b_id

        # 6) Rota detayı — sıralı stop listesi
        banner("6) GET /v1/routes/{id} — sıralı stop listesi (isim+koordinat)")
        r = client.get(f"/routes/{route_id}", headers=auth)
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["stop_count"] == 2
        stops = detail["stops"]
        assert len(stops) == 2, f"İki stop bekleniyordu, geldi: {len(stops)}"
        # order_index artan yönde sıralı olmalı
        assert [s["order_index"] for s in stops] == [0, 1]
        # Her stop'ta isim + koordinat dolu
        for idx, s in enumerate(stops):
            assert "place" in s, f"stop[{idx}] içinde place yok"
            place = s["place"]
            assert isinstance(place.get("isim"), dict) and place["isim"]
            assert -90 <= place["koordinat"]["lat"] <= 90
            assert -180 <= place["koordinat"]["lng"] <= 180
            assert place["id"] in (place_a_id, place_b_id)
        print(pretty({
            "title": detail["title"],
            "is_public": detail["is_public"],
            "stop_count": detail["stop_count"],
            "ordered_place_ids": [s["place_id"] for s in stops],
            "ordered_indexes": [s["order_index"] for s in stops],
        }))

        # 6b) Aynı bilgi dedicated /stops endpoint'inden de gelmeli
        banner("6b) GET /v1/routes/{id}/stops — dedicated liste")
        r = client.get(f"/routes/{route_id}/stops", headers=auth)
        assert r.status_code == 200, r.text
        stops_resp = r.json()
        assert stops_resp["total"] == 2
        assert [s["order_index"] for s in stops_resp["items"]] == [0, 1]
        print(f"-> {r.status_code} total={stops_resp['total']}")

        # 7) PUT ile rota güncelle
        banner("7) PUT /v1/routes/{id} — başlık + is_public")
        r = client.put(
            f"/routes/{route_id}",
            headers=auth,
            json={
                "title": "İzmir Tarihi Yarımada — Güncellendi",
                "is_public": True,
            },
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 200, r.text
        updated = r.json()
        assert updated["title"].endswith("Güncellendi")
        assert updated["is_public"] is True
        print(f"   title={updated['title']!r}  is_public={updated['is_public']}")

        # 8) NEGATİF: Auth'suz POST → 401
        banner("8) NEGATİF: Auth'suz POST /v1/routes → 401")
        r = client.post("/routes", json=create_body)
        print(f"-> {r.status_code}")
        assert r.status_code == 401, r.text

        # 8b) NEGATİF: aynı order_index → 409
        banner("8b) NEGATİF: Aynı order_index ile stop ekleme → 409")
        r = client.post(
            f"/routes/{route_id}/stops",
            headers=auth,
            json={"place_id": place_a_id, "order_index": 0},
        )
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 409, r.text
        assert body.get("code") == "routes.stop_order_conflict"

        # 8c) NEGATİF: Olmayan place_id → 404
        banner("8c) NEGATİF: Olmayan place_id ile stop ekleme → 404")
        r = client.post(
            f"/routes/{route_id}/stops",
            headers=auth,
            json={"place_id": str(uuid.uuid4())},
        )
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 404, r.text
        assert body.get("code") == "routes.place_not_found"

        # 8d) NEGATİF: Başka kullanıcı sahip-uçları görmesin (404, bilgi sızıntısı koruması)
        banner("8d) NEGATİF: İkinci kullanıcı — başkasının rotasına PUT → 404")
        other_access, _ = register_user(client, prefix="izleyici")
        other_auth = {"Authorization": f"Bearer {other_access}"}
        # is_public=True olduğu için GET detail erişebilmeli, ama PUT erişemez.
        r = client.get(f"/routes/{route_id}", headers=other_auth)
        assert r.status_code == 200, r.text
        print(f"   public GET → {r.status_code} (is_public=True erişimi OK)")

        r = client.put(
            f"/routes/{route_id}",
            headers=other_auth,
            json={"title": "Yetkisiz değişiklik"},
        )
        print(f"   yetkisiz PUT → {r.status_code}")
        assert r.status_code == 404, r.text
        body = r.json()
        assert body.get("code") == "routes.not_found"

        # 9) Stop silme + rota silme
        banner("9) DELETE /v1/routes/{id}/stops/{stop_id} — Mekan B kaldır")
        r = client.delete(
            f"/routes/{route_id}/stops/{stop_b['id']}",
            headers=auth,
        )
        print(f"-> {r.status_code}")
        assert r.status_code == 204, r.text

        # Detay tekrar — 1 stop kalmalı
        r = client.get(f"/routes/{route_id}", headers=auth)
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["stop_count"] == 1
        assert len(detail["stops"]) == 1
        assert detail["stops"][0]["place_id"] == place_a_id
        print(f"   kalan stop sayısı: {detail['stop_count']}")

        banner("9b) DELETE /v1/routes/{id} — rotanın tamamı")
        r = client.delete(f"/routes/{route_id}", headers=auth)
        print(f"-> {r.status_code}")
        assert r.status_code == 204, r.text

        # Sonrasında detay 404 dönmeli
        r = client.get(f"/routes/{route_id}", headers=auth)
        assert r.status_code == 404, r.text
        print(f"   silme sonrası GET → {r.status_code} (beklenen)")

    banner("[OK] Adim 7 rota yonetimi (CRUD + stops) uctan uca dogrulandi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
