# KültürRota — Backend (Adım 4: Auth + Temel Mekan API'leri)

Türkiye Kültürel Miras Keşif ve Sosyal Gezi Platformu — **Backend API**.

> **Bu adımın çıktıları**: OAuth 2.0 + JWT (RS256) auth sistemi, refresh
> token rotation + reuse detection, 18+ KVKK kontrolü (D3), temel mekan
> uçları (`/v1/places`, `/v1/places/{id}`, `/v1/places/nearby`) ve Redis
> tabanlı rate limiting (Public 60, Auth 300 req/dk).
> Referans: [`PRD-KulturRota.md`](./PRD-KulturRota.md), Bölüm **10**
> (Veritabanı), **11** (ERD), **12** (API), **17** (Güvenlik/KVKK), **18**
> (Caching/Rate Limit).

---

## Klasör Yapısı

```
kultur-rota/
├── app/
│   ├── api/
│   │   ├── deps.py                # DB session, get_current_user, AdminUser
│   │   ├── rate_limit.py          # Redis fixed-window limiter (PRD §12.1)
│   │   └── v1/
│   │       ├── __init__.py        # api_router (tüm v1 uçlarını toplar)
│   │       ├── auth.py            # /auth/register, /login, /refresh, /logout
│   │       ├── users.py           # /me
│   │       └── places.py          # /places, /places/{id}, /places/nearby
│   ├── core/
│   │   ├── config.py              # Pydantic-settings (JWT, rate limit, CORS…)
│   │   ├── enums.py
│   │   ├── exceptions.py          # RFC 7807 Problem Details
│   │   ├── keys.py                # RSA RS256 anahtar üret/oku
│   │   └── security.py            # argon2id + JWT (encode/decode)
│   ├── db/
│   │   ├── base.py, base_class.py, mixins.py, session.py
│   │   └── redis.py               # tek-instance Redis client
│   ├── models/                    # SQLAlchemy ORM (PRD §10)
│   │   ├── user.py                # 18+ CHECK constraint
│   │   ├── refresh_token.py       # rotating JWT kayıtları
│   │   ├── place.py               # PostGIS Geography(Point, 4326)
│   │   └── … (route, photo, review, favorite, follow, tag, …)
│   ├── schemas/                   # Pydantic DTO'ları
│   │   ├── auth.py                # RegisterRequest (18+ validator), LoginRequest…
│   │   ├── user.py                # UserMe, UserPublic
│   │   └── place.py               # PlaceSummary/Detail, Nearby…
│   ├── services/
│   │   ├── auth_service.py        # register, login, refresh, logout
│   │   └── place_service.py       # list, get, nearby (PostGIS)
│   └── main.py                    # FastAPI factory + CORS + Problem Details
├── alembic/
│   ├── env.py
│   └── versions/
│       ├── 2026_05_11_1232-46aad6190614_initial_schema.py
│       └── 2026_05_11_1511-63be629b1bf2_add_refresh_tokens_table.py
├── scripts/
│   ├── db/init/01_extensions.sql
│   ├── smoke_auth.py              # uçtan uca smoke testi (13 adım)
│   ├── create_test_user.py        # "Test Kullanıcısı" senaryosu
│   └── verify_rate_limit.py       # 60 req/dk dayatma testi
├── secrets/jwt/                   # RS256 PEM çiftleri (gitignore'da)
├── alembic.ini
├── docker-compose.yml             # PostgreSQL 16 + PostGIS, Redis 7
├── requirements.txt
├── .env
└── README.md
```

---

## Hızlı Başlangıç

### 1. Servisleri ayağa kaldırın

```bash
cp .env.example .env
docker compose up -d postgres redis
```

Servis kontrolü:

```bash
docker compose ps
```

### 2. Python ortamı

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Linux/Mac
# source .venv/bin/activate

pip install -r requirements.txt
```

### 3. Migration uygulama

```bash
alembic upgrade head
# 46aad6190614  initial schema
# 63be629b1bf2  add refresh_tokens table  (Adım 4)
```

### 4. Geliştirme sunucusu

```bash
uvicorn app.main:app --reload --port 8000
# http://localhost:8000/health
# http://localhost:8000/docs      (Swagger UI — Authorize: BearerJWT)
# http://localhost:8000/openapi.json
```

İlk başlatmada `secrets/jwt/private.pem` + `public.pem` otomatik üretilir
(PRD §17.2 RS256). Üretim ortamında bu dosyalar KMS/Vault üzerinden
sağlanmalıdır.

### 5. Smoke testler

```bash
# Tüm akış (register → login → /me → refresh rotation → reuse detection
#         → places list/detail/nearby/bbox → logout → 401)
python scripts/smoke_auth.py

# Yalnızca "Test Kullanıcısı" senaryosu (Swagger akışının HTTP karşılığı)
python scripts/create_test_user.py

# Redis tabanlı rate-limit testi
python scripts/verify_rate_limit.py
```

---

## API Uçları (PRD §12)

| Method | Path                            | Auth | Rate (req/dk) | Açıklama |
|--------|---------------------------------|------|---------------|----------|
| POST   | `/api/v1/auth/register`         | —    | 300 | 18+ + KVKK doğrulamalı kayıt; ilk token çifti |
| POST   | `/api/v1/auth/login`            | —    | 300 | E-posta veya kullanıcı adı + şifre |
| POST   | `/api/v1/auth/refresh`          | —    | 300 | Rotating refresh + reuse detection |
| POST   | `/api/v1/auth/logout`           | —    | 300 | Refresh token'ı revoke et |
| GET    | `/api/v1/me`                    | JWT  | 300 | Aktif kullanıcının profili |
| GET    | `/api/v1/places`                | —    | 60  | `?bbox=`, `?category=`, `?q=`, `?unesco=`, `?limit/offset` |
| GET    | `/api/v1/places/{id}`           | —    | 60  | Detay + `kaynak_atif` (atıf bloğu) |
| GET    | `/api/v1/places/nearby`         | —    | 60  | `?lat&lng&radius=` PostGIS `ST_DWithin` |

### Auth Akışı (PRD §17.2)

* **JWT**: RS256 (asimetrik). Anahtar `secrets/jwt/private.pem` + `public.pem`.
* **Access token**: 15 dk. Claim'ler: `sub, role, typ=access, jti, iat, exp, iss, aud`.
* **Refresh token**: 30 gün. `refresh_tokens` tablosunda kayıt + `jti` üzerinden takip.
* **Rotation**: Her başarılı `refresh`te eski token `used_at` + `revoked_at` ile kapanır, yeni çift `parent_jti` ile zincirlenir.
* **Reuse detection**: Aynı refresh ikinci kez sunulursa o kullanıcının **tüm** aktif refresh token'ları revoke edilir (`reason=reuse_detected`) ve 401 döner.
* **Şifre**: argon2id (`passlib`), minimum 10 karakter.

### D3 — 18 Yaş Kontrolü (PRD §17.3)

| Katman | Mekanizma |
|--------|-----------|
| Pydantic (`RegisterRequest.birth_date`) | `_validate_age` → 422 |
| PostgreSQL CHECK constraint (`adult_birth_date`) | `birth_date <= CURRENT_DATE - INTERVAL '18 years'` |

İki kat savunma: uygulama atlatılsa bile DB kayda izin vermez.

### Rate Limiting (PRD §12.1 + §18.1)

* Algoritma: Redis fixed-window (`INCR` + `EXPIRE 65s`). Anahtar `rl:{scope}:{ip|user_id}:{window}`.
* Sınırlar: **Public 60 req/dk**, **Auth 300 req/dk**.
* Limit aşımında **HTTP 429** + RFC 7807 + `Retry-After` (sn).
* Redis düşerse fail-open (uyarı log + alert).

### Hata Modeli (PRD §12.1)

Tüm hatalar **RFC 7807 Problem Details** (`application/problem+json`):

```json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Refresh token zaten kullanılmış. Tüm oturumlar kapatıldı.",
  "code": "auth.refresh_reuse",
  "instance": "/api/v1/auth/refresh"
}
```

---

## PRD Eşleştirme — Veritabanı Modelleri

| PRD Tablosu (Bölüm 10) | Modül | Notlar |
|---|---|---|
| `places` | `app/models/place.py` | PostGIS `Geography(Point, 4326)` + `Polygon`; GIST + GIN indeksleri |
| `users` | `app/models/user.py` | **18+ CHECK constraint** (D3) |
| `routes` | `app/models/route.py` | owner_id → users |
| `route_stops` | `app/models/route_stop.py` | `UNIQUE(route_id, order_index)`, place_id ON DELETE **RESTRICT** |
| `photos` | `app/models/photo.py` | EXIF jsonb, license default `CC BY-NC 4.0` |
| `reviews` | `app/models/review.py` | place_id ON DELETE **CASCADE**; rating CHECK 1-5 |
| `favorites` | `app/models/favorite.py` | M2M, bileşik PK |
| `follows` | `app/models/follow.py` | Self-referential M2M; `no_self_follow` CHECK |
| `route_likes` | `app/models/route_like.py` | M2M, bileşik PK |
| `route_comments` | `app/models/route_comment.py` | 1:N |
| `tags` | `app/models/tag.py` | controlled vocabulary |
| `place_tags` | `app/models/place_tag.py` | M2M weight + source |
| `opening_hours` | `app/models/opening_hours.py` | day_of_week 0-6 CHECK |
| `ai_decision_queue` | `app/models/ai_decision_queue.py` | candidate_place_ids array (lineage) |
| `ai_decision_log` | `app/models/ai_decision_log.py` | Tam audit izi |
| `etl_run_log` | `app/models/etl_run_log.py` | idempotency_key UNIQUE |
| `merge_decision_log` | `app/models/merge_decision_log.py` | Dedup lineage |
| `audit_log` | `app/models/audit_log.py` | KVKK genel audit |
| `reports` | `app/models/report.py` | **Polimorfik** (target_type + target_id, FK yok) |

---

## PRD Eşleştirme — İlişkiler (Bölüm 11.1)

* **One-to-Many**: `users → routes/photos/reviews/favorites/reports/route_likes/route_comments`,
  `places → photos/reviews/favorites/opening_hours/route_stops`,
  `routes → route_stops/route_likes/route_comments`,
  `ai_decision_queue → ai_decision_log`,
  `etl_run_log → merge_decision_log`,
  `tags → place_tags`.
* **Many-to-Many**: `favorites (user↔place)`, `follows (user↔user self-ref)`,
  `place_tags (place↔tag)`, `route_likes (user↔route)`.
* **Polimorfik**: `reports.target_type + target_id` — FK yok, enum CHECK ile sınırlı.
* **Cascade kuralları**:
  * `route_stops.place_id` → `places` **ON DELETE RESTRICT** (PRD 11.1).
  * `reviews.place_id` → `places` **ON DELETE CASCADE** (PRD 11.1).
* **Soft-delete**: `places.is_published`, `users.is_active`, `photos.is_approved`.

---

## D3 — 18 Yaş Kontrolü (KVKK)

`users.birth_date` zorunlu (`NOT NULL`) ve aşağıdaki DB-level CHECK ile zorlanır
(bkz. `app/models/user.py`):

```python
CheckConstraint(
    "birth_date <= (CURRENT_DATE - INTERVAL '18 years')",
    name="adult_birth_date",
)
```

Bu kontrol, uygulama bypass edilse bile kayda izin vermez.

---

## Adım 4 Smoke Test Çıktısı (özet)

`scripts/smoke_auth.py` 13 adımı sırayla çalıştırır; özet sonuç:

```
1)  POST /v1/auth/register          → 201 (access + refresh)
2)  17 yaş kayıt reddi (D3)         → 422 validation.failed
3)  POST /v1/auth/login             → 200
4)  GET  /v1/me  (Bearer JWT)       → 200, profile döner
5)  POST /v1/auth/refresh (rotate)  → 200, refresh değişti
6)  Eski refresh tekrar gönder      → 401 auth.refresh_reuse  (tüm token revoke)
7)  Yeni refresh de artık geçersiz  → 401
8)  GET  /v1/places?limit=3         → 200, toplam 2 650 İzmir kaydı
9)  GET  /v1/places/{id}            → 200, kaynak_atif bloğu mevcut
10) GET  /v1/places/nearby          → 200, ST_DWithin metre sıralı
11) GET  /v1/places?bbox=İzmir      → 200, İzmir bbox toplam
12) POST /v1/auth/logout            → 204
13) GET  /v1/me   (token'siz)       → 401 auth.missing_token
```

`scripts/verify_rate_limit.py` 65 ardışık istek gönderir; 61. istekten
itibaren `HTTP 429 rate_limit.places.list` cevabı döner.

---

## Sonraki Adım

* **Adım 5**: Profil güncelleme + KVKK veri-indirme/silme + e-posta doğrulama.
* **Adım 6**: Fotoğraf yükleme (S3 pre-signed URL + EXIF GPS temizleme + NSFW skoru).
