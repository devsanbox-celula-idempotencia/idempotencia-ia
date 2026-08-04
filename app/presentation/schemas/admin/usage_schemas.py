"""Schemas del panel administrativo: consumo y logs."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel


class DailyUsageResponse(BaseModel):
    day: date
    requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class UsageSummaryResponse(BaseModel):
    api_key_id: int | None
    total_requests: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    days: list[DailyUsageResponse] = []


class RequestLogResponse(BaseModel):
    id: int
    api_key_id: int | None
    model: str
    endpoint: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: int
    status_code: int
    error: str | None = None
    created_at: datetime | None = None
