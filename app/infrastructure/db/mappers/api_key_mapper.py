"""Mapper ApiKey: entidad de dominio <-> modelo ORM."""
from __future__ import annotations

from app.domain.entities.api_key import ApiKey
from app.infrastructure.db.models.api_key_model import ApiKeyModel


def to_entity(row: ApiKeyModel) -> ApiKey:
    return ApiKey(
        id=row.ApiKeyId,
        user_id=row.UserId,
        name=row.Name,
        key_hash=row.KeyHash,
        key_prefix=row.KeyPrefix,
        is_active=bool(row.IsActive),
        created_at=row.CreatedAt,
        expires_at=row.ExpiresAt,
        last_used_at=row.LastUsedAt,
        daily_token_limit=row.DailyTokenLimit,
        monthly_token_limit=row.MonthlyTokenLimit,
        requests_per_minute=row.RequestsPerMinute,
    )


def to_model(entity: ApiKey) -> ApiKeyModel:
    return ApiKeyModel(
        UserId=entity.user_id,
        Name=entity.name,
        KeyHash=entity.key_hash,
        KeyPrefix=entity.key_prefix,
        IsActive=entity.is_active,
        ExpiresAt=entity.expires_at,
        DailyTokenLimit=entity.daily_token_limit,
        MonthlyTokenLimit=entity.monthly_token_limit,
        RequestsPerMinute=entity.requests_per_minute,
    )
