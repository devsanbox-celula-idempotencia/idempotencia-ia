"""Schemas del panel administrativo: API keys."""
from __future__ import annotations

from datetime import datetime

from datetime import timezone

from pydantic import BaseModel, Field, field_validator


class ApiKeyCreateRequest(BaseModel):
    user_id: int = Field(description="UserId de la tabla Users", examples=[1])
    name: str = Field(max_length=100, examples=["Integración web"])
    expires_at: datetime | None = None
    daily_token_limit: int | None = Field(default=None, ge=1)
    monthly_token_limit: int | None = Field(default=None, ge=1)
    requests_per_minute: int | None = Field(default=None, ge=1)

    @field_validator("expires_at")
    @classmethod
    def _a_utc_naive(cls, value: datetime | None) -> datetime | None:
        """ExpiresAt es DATETIME2 sin zona y se compara contra UTC.
        pyodbc ignora el tzinfo, así que una fecha con offset caducaría
        la clave con horas de diferencia."""
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class ApiKeyCreatedResponse(BaseModel):
    id: int
    name: str
    api_key: str = Field(description="Solo se muestra en esta respuesta. Guárdala.")
    created_at: datetime


class ApiKeyResponse(BaseModel):
    id: int
    user_id: int
    name: str
    key_prefix: str
    is_active: bool
    created_at: datetime | None = None
    last_used_at: datetime | None = None
    expires_at: datetime | None = None
    daily_token_limit: int | None = None
    requests_per_minute: int | None = None
