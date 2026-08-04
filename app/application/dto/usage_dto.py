"""DTOs de consumo."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(slots=True)
class UsageQueryInput:
    start: date
    end: date
    api_key_id: int | None = None


@dataclass(slots=True)
class DailyUsageDTO:
    day: date
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(slots=True)
class UsageSummaryOutput:
    api_key_id: int | None
    total_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    days: list[DailyUsageDTO] = field(default_factory=list)
