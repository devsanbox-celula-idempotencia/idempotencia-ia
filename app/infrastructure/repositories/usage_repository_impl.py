"""Repositorio de consumo acumulado."""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.usage import Usage
from app.domain.ports.repositories.usage_repository import UsageRepository
from app.domain.value_objects.token_usage import TokenUsage
from app.infrastructure.db.mappers import usage_mapper
from app.infrastructure.db.models.usage_model import UsageModel

# UPDATE-si-existe / INSERT-si-no, en una sola sentencia.
# HOLDLOCK evita que dos peticiones simultáneas de la misma clave inserten
# la fila del día a la vez y revienten la restricción UQ_ApiKeyUsage_ApiKey_Day.
_MERGE_USAGE = text(
    """
    MERGE dbo.ApiKeyUsage WITH (HOLDLOCK) AS target
    USING (SELECT :api_key_id AS ApiKeyId, :day AS Day) AS source
        ON target.ApiKeyId = source.ApiKeyId AND target.[Day] = source.Day
    WHEN MATCHED THEN
        UPDATE SET PromptTokens     = target.PromptTokens     + :prompt_tokens,
                   CompletionTokens = target.CompletionTokens + :completion_tokens,
                   TotalTokens      = target.TotalTokens      + :total_tokens,
                   Requests         = target.Requests         + 1
    WHEN NOT MATCHED THEN
        INSERT (ApiKeyId, [Day], PromptTokens, CompletionTokens, TotalTokens, Requests)
        VALUES (:api_key_id, :day, :prompt_tokens, :completion_tokens, :total_tokens, 1);
    """
)


class SqlAlchemyUsageRepository(UsageRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def increment(self, api_key_id: int, day: date, usage: TokenUsage) -> None:
        await self._session.execute(
            _MERGE_USAGE,
            {
                "api_key_id": api_key_id,
                "day": day,
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            },
        )

    async def get_daily(self, api_key_id: int, day: date) -> Usage | None:
        stmt = select(UsageModel).where(UsageModel.ApiKeyId == api_key_id, UsageModel.Day == day)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return usage_mapper.to_entity(row) if row else None

    async def get_range(self, api_key_id: int | None, start: date, end: date) -> list[Usage]:
        stmt = select(UsageModel).where(UsageModel.Day >= start, UsageModel.Day <= end)
        if api_key_id is not None:
            stmt = stmt.where(UsageModel.ApiKeyId == api_key_id)
        rows = (await self._session.execute(stmt.order_by(UsageModel.Day))).scalars().all()
        return [usage_mapper.to_entity(r) for r in rows]

    async def tokens_since(self, api_key_id: int, start: date) -> int:
        stmt = select(func.coalesce(func.sum(UsageModel.TotalTokens), 0)).where(
            UsageModel.ApiKeyId == api_key_id, UsageModel.Day >= start
        )
        return int((await self._session.execute(stmt)).scalar_one())
