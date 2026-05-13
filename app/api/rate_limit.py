"""
Redis Tabanlı Rate Limiter
==========================
PRD §12.1 + §18.1 — Public 60 req/dk, Auth 300 req/dk.

Algoritma: **Fixed-window counter**. Anahtarlar 60 saniyelik pencerelere
hizalanır:

    rl:{scope}:{ip|user_id}:{minute_window}

Token bucket yerine fixed-window seçildi çünkü:

    * MVP için yeterli (kesin TTL ile).
    * Tek `INCR` + `EXPIRE` (tek RTT) — basit, hızlı.
    * Lua script gerekmez → bağımlılık yok.

Üretimde "sliding window log" / "token bucket" gerekirse Redis-Cell veya
Lua tabanlı bir varianta geçiş kolaydır.
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import redis
from fastapi import Request

from app.core.exceptions import ProblemDetailsError
from app.db.redis import get_redis_client

logger = logging.getLogger(__name__)


def _client_key(request: Request) -> str:
    """İstek sahibini tek bir kimlikle eşle.

    Öncelik:
        1. ``request.state.user_id``     → kimliği doğrulanmış kullanıcı
        2. ``X-Forwarded-For`` ilk hop   → proxy arkasındaysa
        3. ``request.client.host``       → fallback
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"u:{user_id}"

    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return f"ip:{fwd.split(',', 1)[0].strip()}"

    client = request.client
    return f"ip:{client.host if client else 'unknown'}"


def _enforce(
    request: Request,
    *,
    scope: str,
    limit: int,
) -> None:
    """Tek bir scope için fixed-window limit dayatması.

    Limit aşılırsa :class:`ProblemDetailsError` (HTTP 429) fırlatır ve
    ``Retry-After`` saniye değeri ``extras`` içinde döner.
    """
    if limit <= 0:
        return

    client = _client_key(request)
    now = int(time.time())
    window = now // 60
    key = f"rl:{scope}:{client}:{window}"

    try:
        redis_client: redis.Redis = get_redis_client()
        pipe = redis_client.pipeline()
        pipe.incr(key)
        pipe.expire(key, 65)  # küçük buffer
        count, _ = pipe.execute()
    except redis.RedisError as exc:
        # Redis erişilemezse rate-limit zorlamayı bypass etmek yerine
        # uyarı logla ve geçişe izin ver (fail-open). PRD §19'a göre
        # Redis dışsallaştırılmış kritik servistir; alert tetiklenir.
        logger.warning("rate-limit redis hatası, fail-open: %s", exc)
        return

    if count > limit:
        retry_after = 60 - (now % 60)
        raise ProblemDetailsError(
            status=429,
            title="Too Many Requests",
            detail=(
                f"Bu uç için {limit} req/dk sınırına ulaşıldı. "
                f"{retry_after} saniye sonra tekrar deneyin."
            ),
            code=f"rate_limit.{scope}",
            extras={"retry_after_seconds": retry_after, "limit_per_minute": limit},
        )


def rate_limit(scope: str, *, limit: int) -> Callable[[Request], None]:
    """FastAPI dependency factory.

    Kullanım::

        from app.api.rate_limit import rate_limit

        @router.get(
            "/places",
            dependencies=[Depends(rate_limit("places.list", limit=60))],
        )
        async def list_places(...): ...

    Args:
        scope: Metric/log için anlamlı isim (örn. ``"auth.login"``).
        limit: Dakika başına izin verilen maksimum istek.
    """

    def _dep(request: Request) -> None:
        _enforce(request, scope=scope, limit=limit)

    _dep.__name__ = f"rate_limit_{scope.replace('.', '_')}"
    return _dep
