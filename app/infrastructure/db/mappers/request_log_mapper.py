"""Mapper RequestLog."""
from __future__ import annotations

from app.domain.entities.request_log import RequestLog
from app.infrastructure.db.models.request_log_model import RequestLogModel


def to_entity(row: RequestLogModel) -> RequestLog:
    return RequestLog(
        id=row.RequestLogId,
        api_key_id=row.ApiKeyId,
        model=row.Model,
        endpoint=row.Endpoint,
        prompt_tokens=row.PromptTokens,
        completion_tokens=row.CompletionTokens,
        total_tokens=row.TotalTokens,
        duration_ms=row.DurationMs,
        status_code=row.StatusCode,
        client_ip=row.ClientIp,
        error=row.Error,
        created_at=row.CreatedAt,
    )


def to_model(entity: RequestLog) -> RequestLogModel:
    return RequestLogModel(
        ApiKeyId=entity.api_key_id,
        Model=entity.model,
        Endpoint=entity.endpoint,
        PromptTokens=entity.prompt_tokens,
        CompletionTokens=entity.completion_tokens,
        TotalTokens=entity.total_tokens,
        DurationMs=entity.duration_ms,
        StatusCode=entity.status_code,
        ClientIp=entity.client_ip,
        Error=entity.error,
    )
