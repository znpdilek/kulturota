"""
Smoke Test — Adım 6: Medya Yönetimi & S3 (Fotoğraf Yükleme)
===========================================================
PRD §13 (Medya Mimarisi) + §12.2 (``POST /v1/photos``) + §14.3 (F3).

Bu script uçtan uca akışı doğrular:

    1.  Yeni bir test kullanıcısı kaydeder (18+ + KVKK).
    2.  ``GET /v1/places`` üzerinden ilk yayınlanan mekanı çeker.
    3.  Pillow ile sahte (in-memory) bir JPEG üretir; içerisine **EXIF GPS
        koordinatları** ekler (KVKK temizliği akışını test edebilmek için).
    4.  ``POST /v1/photos`` multipart isteği gönderir → 201 bekler.
    5.  Yanıttaki ``url`` alanından MinIO'ya yapılan HTTP GET ile dosyanın
        gerçekten yüklendiğini doğrular (uçtan uca S3).
    6.  Yüklenen dosyanın EXIF blob'unun **GPS içermediğini** Pillow ile
        doğrular (PRD §17.3 KVKK).
    7.  Negatif testler:
        * Auth'suz istek → 401.
        * .gif (whitelist dışı) → 415.
        * 6 MB üzeri payload → 413.
        * Olmayan ``place_id`` → 404.

Çalıştırma::

    docker compose up -d postgres redis minio minio-init
    uvicorn app.main:app --reload --port 8000
    python scripts/smoke_media.py

Tüm adımlar ``assert`` ile katı kontrol edilir; bir adım düşerse script
non-zero exit code ile sonlanır.
"""

from __future__ import annotations

import io
import json
import sys
import uuid
from typing import Any

import httpx
from PIL import Image
from PIL.ExifTags import IFD, Base as ExifBase
from PIL.TiffImagePlugin import IFDRational

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


# --- Image fixtures --------------------------------------------------------
def make_jpeg_with_gps(size: tuple[int, int] = (320, 240)) -> bytes:
    """EXIF GPS koordinatları içeren sentetik bir JPEG üretir.

    PRD §17.3 KVKK gereği bu GPS bilgisi *sunucu tarafında* temizlenmeli;
    yüklenmiş dosyada GPS izi kalmamalı (bu kontrolü smoke test doğrular).

    Pillow'un EXIF yazıcısı GPS IFD'sini ``Image.Exif.get_ifd(IFD.GPSInfo)``
    yardımcısı üzerinden besler. DMS değerleri "rational" beklenir.
    """
    img = Image.new("RGB", size, color=(180, 120, 60))
    exif = img.getexif()
    exif[ExifBase.Make.value] = "KulturRotaSmokeCam"
    exif[ExifBase.Model.value] = "Synthetic v1"
    exif[ExifBase.DateTimeOriginal.value] = "2025:08:01 12:30:45"

    # İzmir merkez koordinatları (≈38.42°N, 27.14°E) DMS olarak.
    # Pillow için GPS rational değerlerini IFDRational ile veriyoruz.
    gps_ifd = exif.get_ifd(IFD.GPSInfo)
    gps_ifd[1] = "N"
    gps_ifd[2] = (IFDRational(38, 1), IFDRational(25, 1), IFDRational(12, 1))
    gps_ifd[3] = "E"
    gps_ifd[4] = (IFDRational(27, 1), IFDRational(8, 1), IFDRational(24, 1))
    gps_ifd[5] = b"\x00"
    gps_ifd[6] = IFDRational(100, 1)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, exif=exif)
    return buf.getvalue()


def make_plain_png(size: tuple[int, int] = (100, 100)) -> bytes:
    img = Image.new("RGB", size, color=(20, 80, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_oversized_jpeg() -> bytes:
    """5 MB sınırını aşan görsel — rastgele gürültülü 8 MB dolayında."""
    # 3000x3000 RGB JPEG quality=100 ~ 6-8 MB.
    img = Image.effect_noise((3000, 3000), 64).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=100, optimize=False)
    data = buf.getvalue()
    # Garanti olsun diye 6 MB altındaysa daha agresif üret.
    while len(data) <= 5 * 1024 * 1024:
        size = int((len(buf.getvalue())) * 1.5)
        img = Image.effect_noise((size // 2, size // 2), 64).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=100, optimize=False)
        data = buf.getvalue()
        if len(data) > 12 * 1024 * 1024:
            break
    return data


def make_fake_gif() -> bytes:
    """Whitelist dışı format (magic byte ``GIF87a``)."""
    return b"GIF87a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02L\x01\x00;"


# --- Auth ------------------------------------------------------------------
def register_user(client: httpx.Client) -> tuple[str, str]:
    """Smoke için tek-seferlik kullanıcı oluştur."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "email": f"foto+{suffix}@kulturrota.example.com",
        "username": f"foto_{suffix}",
        "password": "SmokeFoto!2026",
        "display_name": "Foto Smoke",
        "birth_date": "1997-04-15",
        "kvkk_consent": True,
        "locale": "tr",
    }
    r = client.post("/auth/register", json=payload)
    assert r.status_code == 201, f"register başarısız: {r.status_code} {r.text}"
    body = r.json()
    return body["access_token"], body["refresh_token"]


def pick_published_place_id(client: httpx.Client) -> str:
    r = client.get("/places", params={"limit": 1})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert items, "Veritabanında yayınlanmış mekan yok; ETL'i çalıştırın."
    return items[0]["id"]


# --- Main ------------------------------------------------------------------
def main() -> int:
    with httpx.Client(base_url=API, timeout=30.0) as client:
        # 0) Sağlık kontrolü
        banner("0) Sağlık kontrolü")
        h = client.get(f"{BASE_URL}/health")
        assert h.status_code == 200, h.text
        print(f"-> {h.status_code} {h.json()}")

        # 1) Kayıt
        banner("1) Kullanıcı kaydı (18+ + KVKK)")
        access, _refresh = register_user(client)
        auth_headers = {"Authorization": f"Bearer {access}"}
        print(f"-> access[…]={access[:30]}")

        # 2) Hedef mekan
        banner("2) GET /v1/places?limit=1 (yayınlanmış mekan)")
        place_id = pick_published_place_id(client)
        print(f"-> place_id={place_id}")

        # 3) Sentetik JPEG (EXIF GPS dahil)
        banner("3) EXIF GPS içeren sahte JPEG üret")
        jpeg_bytes = make_jpeg_with_gps()
        print(f"-> JPEG boyutu: {len(jpeg_bytes)} byte")
        # Sanity: gerçekten GPS var mı? (Pillow GPS'i ayrı bir IFD'de tutar)
        probe = Image.open(io.BytesIO(jpeg_bytes))
        probe_gps_ifd = probe.getexif().get_ifd(IFD.GPSInfo)
        assert probe_gps_ifd, "Test fixture GPS içermiyor!"
        print(f"   ✓ Fixture EXIF GPS içeriyor: {len(probe_gps_ifd)} alan.")

        # 4) Multipart yükleme
        banner("4) POST /v1/photos (multipart)")
        files = {
            "file": ("izmir-agora.jpg", jpeg_bytes, "image/jpeg"),
        }
        data = {"place_id": place_id}
        r = client.post("/photos", headers=auth_headers, files=files, data=data)
        print(f"-> {r.status_code}")
        assert r.status_code == 201, f"Beklenen 201, gelen: {r.status_code} {r.text}"
        body = r.json()
        print(pretty({
            "id": body["id"],
            "place_id": body["place_id"],
            "user_id": body["user_id"],
            "url": body["url"],
            "width": body["width"],
            "height": body["height"],
            "license": body["license"],
            "is_approved": body["is_approved"],
            "taken_at": body.get("taken_at"),
            "exif_had_gps": body["exif_had_gps"],
        }))
        assert body["license"] == "CC BY-NC 4.0"  # PRD §20.4
        assert body["is_approved"] is False        # PRD F3 default
        assert body["exif_had_gps"] is True, "EXIF GPS sinyali kaybolmamalı."
        photo_url = body["url"]

        # 5) S3 doğrulaması — public URL'den indir
        banner("5) MinIO/S3 public URL'den indirme (uçtan uca)")
        async_safe = httpx.Client(timeout=15.0)
        try:
            dl = async_safe.get(photo_url)
            assert dl.status_code == 200, f"S3 GET {dl.status_code}: {dl.text[:200]}"
            print(f"-> {dl.status_code}, indirilen boyut: {len(dl.content)} byte")

            # 6) İndirilen dosyada GPS YOK mu? (KVKK — PRD §17.3)
            banner("6) KVKK doğrulaması: EXIF GPS temizlenmiş mi?")
            stored = Image.open(io.BytesIO(dl.content))
            stored.load()
            stored_exif = stored.getexif() or {}
            stored_gps = stored_exif.get_ifd(IFD.GPSInfo) if stored_exif else {}
            assert not stored_gps, (
                f"GPS verisi temizlenmemiş — KVKK ihlali! gps={dict(stored_gps)}"
            )
            print("   ✓ S3'teki dosyada GPS bilgisi YOK (temizlik başarılı).")
            print(f"   ✓ Stored EXIF tags: {len(stored_exif)} (GPS hariç)")
        finally:
            async_safe.close()

        # 7) Auth'suz → 401
        banner("7) NEGATİF: Auth'suz POST → 401")
        files = {"file": ("foo.jpg", jpeg_bytes, "image/jpeg")}
        data = {"place_id": place_id}
        r = client.post("/photos", files=files, data=data)
        print(f"-> {r.status_code}")
        assert r.status_code == 401, r.text

        # 8) Yanlış format → 415
        banner("8) NEGATİF: .gif dosyası → 415 (whitelist dışı)")
        gif_bytes = make_fake_gif()
        files = {"file": ("anim.gif", gif_bytes, "image/gif")}
        data = {"place_id": place_id}
        r = client.post("/photos", headers=auth_headers, files=files, data=data)
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 415, r.text
        assert body.get("code") == "media.unsupported_format"

        # 9) Aşırı boyut → 413
        banner("9) NEGATİF: 5 MB üzeri dosya → 413")
        big = make_oversized_jpeg()
        print(f"   üretilen boyut: {len(big) / (1024*1024):.2f} MB")
        files = {"file": ("huge.jpg", big, "image/jpeg")}
        data = {"place_id": place_id}
        r = client.post("/photos", headers=auth_headers, files=files, data=data)
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "limit": body.get("limit_bytes")}))
        assert r.status_code == 413, r.text
        assert body.get("code") == "media.file_too_large"

        # 10) Olmayan mekan → 404
        banner("10) NEGATİF: Olmayan place_id → 404")
        files = {"file": ("ok.png", make_plain_png(), "image/png")}
        data = {"place_id": str(uuid.uuid4())}
        r = client.post("/photos", headers=auth_headers, files=files, data=data)
        print(f"-> {r.status_code}")
        body = r.json()
        print(pretty({"code": body.get("code"), "title": body.get("title")}))
        assert r.status_code == 404, r.text
        assert body.get("code") == "media.place_not_found"

        # 11) PNG da çalışıyor mu?
        banner("11) Pozitif: temiz PNG yükle → 201")
        files = {"file": ("simple.png", make_plain_png(), "image/png")}
        data = {"place_id": place_id}
        r = client.post("/photos", headers=auth_headers, files=files, data=data)
        assert r.status_code == 201, r.text
        b = r.json()
        print(f"-> 201 url={b['url']}  ({b['width']}x{b['height']})")
        assert b["url"].endswith(".png")

    banner("[OK] Adim 6 medya akisi uctan uca dogrulandi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
