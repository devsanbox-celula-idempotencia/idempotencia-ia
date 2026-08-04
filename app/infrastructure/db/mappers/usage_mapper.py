"""Mapper Usage."""
from __future__ import annotations

from app.domain.entities.usage import Usage
from app.infrastructure.db.models.usage_model import UsageModel


def to_entity(row: UsageModel) -> Usage:
    return Usage(
        id=row.UsageId,
        api_key_id=row.ApiKeyId,
        day=row.Day,
        prompt_tokens=row.PromptTokens,
        completion_tokens=row.CompletionTokens,
        total_tokens=row.TotalTokens,
        requests=row.Requests,
    )
