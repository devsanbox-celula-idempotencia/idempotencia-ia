"""DTOs de administración de API keys."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class CreateApiKeyInput:
    user_id: int
    name: str
    expires_at: datetime | None = None
    daily_token_limit: int | None = None
    monthly_token_limit: int | None = None
    requests_per_minute: int | None = None


@dataclass(slots=True)
class CreateApiKeyOutput:
    id: int
    name: str
    raw_key: str  # se muestra UNA sola vez
    created_at: datetime
