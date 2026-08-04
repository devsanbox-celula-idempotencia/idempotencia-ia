"""Entidad ApiKey. Nunca guarda la clave en claro, solo su hash SHA-256."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ApiKey:
    id: int
    user_id: int
    name: str
    key_hash: str
    key_prefix: str
    is_active: bool = True
    created_at: datetime | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    daily_token_limit: int | None = None
    monthly_token_limit: int | None = None
    requests_per_minute: int | None = None

    def is_usable(self, now: datetime) -> bool:
        """Activa y no expirada."""
        if not self.is_active:
            return False
        if self.expires_at is not None and self.expires_at <= now:
            return False
        return True

    def touch(self, now: datetime) -> None:
        self.last_used_at = now
