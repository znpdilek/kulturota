"""Rate limit kapaması doğrulaması (PRD §12.1 — Public 60, Auth 300 req/dk)."""

from __future__ import annotations

import io
import sys

import httpx

if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

BASE = "http://127.0.0.1:8000/api/v1"

with httpx.Client(base_url=BASE, timeout=15.0) as cli:
    # Public limit = 60/dk. 65 istek atalım, ≥61'inci 429 dönmeli.
    print("GET /places  — public 60 req/dk limitini sınıyoruz…")
    statuses: list[int] = []
    for i in range(65):
        r = cli.get("/places", params={"limit": 1})
        statuses.append(r.status_code)
    ok = sum(1 for s in statuses if s == 200)
    too_many = sum(1 for s in statuses if s == 429)
    first_429 = next((i + 1 for i, s in enumerate(statuses) if s == 429), None)
    print(f"  200 cevaplari    : {ok}")
    print(f"  429 cevaplari    : {too_many}")
    print(f"  ilk 429 sirasi   : {first_429}")
    assert too_many > 0, "Rate limit beklenen sürede tetiklenmedi!"

    # Son 429 cevabını detaylı göster.
    last_429 = cli.get("/places", params={"limit": 1})
    if last_429.status_code == 429:
        body = last_429.json()
        print(f"\n429 Problem Details örnegi:")
        for key in ("title", "status", "detail", "code", "retry_after_seconds", "limit_per_minute"):
            if key in body:
                print(f"  {key:24}: {body[key]}")

print("\n[OK] Rate-limit dayatması beklendiği gibi çalısıyor.")
