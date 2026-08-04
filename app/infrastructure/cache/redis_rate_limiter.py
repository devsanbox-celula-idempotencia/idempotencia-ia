"""Rate limiter con Redis: ventana fija por minuto (INCR + EXPIRE)."""
from __future__ import annotations

import time

from app.domain.ports.services.rate_limiter import RateLimiter
from app.domain.value_objects.rate_limit import RateLimitPolicy, RateLimitResult


class RedisRateLimiter(RateLimiter):
    def __init__(self, redis) -> None:  # redis.asyncio.Redis
        self._redis = redis

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitResult:
        limit = policy.requests_per_minute
        if not limit:
            return RateLimitResult(allowed=True)

        window = int(time.time() // 60)
        redis_key = f"rl:{key}:{window}"

        pipe = self._redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, 120)
        count, _ = await pipe.execute()

        return RateLimitResult(
            allowed=int(count) <= limit,
            limit=limit,
            remaining=max(0, limit - int(count)),
            reset_in_seconds=60 - int(time.time() % 60),
        )

    async def consume_tokens(self, key: str, tokens: int) -> None:
        day_key = f"tok:{key}:{time.strftime('%Y-%m-%d')}"
        pipe = self._redis.pipeline()
        pipe.incrby(day_key, tokens)
        pipe.expire(day_key, 172800)
        await pipe.execute()
