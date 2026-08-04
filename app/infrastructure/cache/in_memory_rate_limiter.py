"""Rate limiter en memoria: para desarrollo, tests o un solo proceso."""
from __future__ import annotations

import time

from app.domain.ports.services.rate_limiter import RateLimiter
from app.domain.value_objects.rate_limit import RateLimitPolicy, RateLimitResult


class InMemoryRateLimiter(RateLimiter):
    """Ventana fija por minuto. Suficiente con 1 worker de uvicorn."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[int, int]] = {}  # key -> (ventana, contador)

    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitResult:
        limit = policy.requests_per_minute
        if not limit:
            return RateLimitResult(allowed=True)

        window = int(time.time() // 60)
        current_window, count = self._windows.get(key, (window, 0))
        if current_window != window:
            current_window, count = window, 0

        count += 1
        self._windows[key] = (current_window, count)
        reset_in = 60 - int(time.time() % 60)

        return RateLimitResult(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            reset_in_seconds=reset_in,
        )

    async def consume_tokens(self, key: str, tokens: int) -> None:
        return None
