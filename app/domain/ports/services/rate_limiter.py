"""Puerto del limitador de peticiones (implementado con Redis)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.value_objects.rate_limit import RateLimitPolicy, RateLimitResult


class RateLimiter(ABC):
    @abstractmethod
    async def check(self, key: str, policy: RateLimitPolicy) -> RateLimitResult: ...

    @abstractmethod
    async def consume_tokens(self, key: str, tokens: int) -> None: ...
