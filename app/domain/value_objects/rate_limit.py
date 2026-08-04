"""Value objects para límites de uso."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RateLimitPolicy:
    requests_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_day: int | None = None
    tokens_per_month: int | None = None


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    limit: int | None = None
    remaining: int | None = None
    reset_in_seconds: int | None = None
