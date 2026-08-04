"""Verificar límites de peticiones y de tokens antes de llamar al modelo."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.domain.entities.api_key import ApiKey
from app.domain.exceptions import QuotaExceededError, RateLimitExceededError
from app.domain.ports.repositories.usage_repository import UsageRepository
from app.domain.ports.services.rate_limiter import RateLimiter
from app.domain.value_objects.rate_limit import RateLimitPolicy, RateLimitResult


class CheckRateLimit:
    def __init__(
        self,
        limiter: RateLimiter,
        usage: UsageRepository,
        default_rpm: int,
        default_tokens_per_day: int,
    ) -> None:
        self._limiter = limiter
        self._usage = usage
        self._default_rpm = default_rpm
        self._default_tokens_per_day = default_tokens_per_day

    async def execute(self, api_key: ApiKey) -> RateLimitResult:
        policy = RateLimitPolicy(
            requests_per_minute=api_key.requests_per_minute or self._default_rpm,
            tokens_per_day=api_key.daily_token_limit or self._default_tokens_per_day,
        )

        result = await self._limiter.check(str(api_key.id), policy)
        if not result.allowed:
            raise RateLimitExceededError(
                f"Límite de {result.limit} peticiones por minuto superado. "
                f"Reintenta en {result.reset_in_seconds} s.",
                retry_after=result.reset_in_seconds,
            )

        if policy.tokens_per_day:
            # UTC: el acumulado se guarda con la fecha UTC (ver RecordUsage)
            today = datetime.now(timezone.utc).date()
            used = await self._usage.tokens_since(api_key.id, today)
            if used >= policy.tokens_per_day:
                # La cuota diaria se reinicia a medianoche UTC: ese es el
                # tiempo real de espera, no unos segundos.
                ahora = datetime.now(timezone.utc)
                manana = datetime.combine(
                    today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
                )
                raise QuotaExceededError(
                    f"Cuota diaria de {policy.tokens_per_day} tokens agotada ({used} usados)",
                    retry_after=int((manana - ahora).total_seconds()),
                )

        return result
