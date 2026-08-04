"""Consultar consumo por API key y rango de fechas."""
from __future__ import annotations

from app.application.dto.usage_dto import DailyUsageDTO, UsageQueryInput, UsageSummaryOutput
from app.domain.ports.services.unit_of_work import UnitOfWork


class GetUsage:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, query: UsageQueryInput) -> UsageSummaryOutput:
        rows = await self._uow.usage.get_range(query.api_key_id, query.start, query.end)
        return UsageSummaryOutput(
            api_key_id=query.api_key_id,
            total_requests=sum(r.requests for r in rows),
            prompt_tokens=sum(r.prompt_tokens for r in rows),
            completion_tokens=sum(r.completion_tokens for r in rows),
            total_tokens=sum(r.total_tokens for r in rows),
            days=[
                DailyUsageDTO(
                    day=r.day,
                    requests=r.requests,
                    prompt_tokens=r.prompt_tokens,
                    completion_tokens=r.completion_tokens,
                    total_tokens=r.total_tokens,
                )
                for r in rows
            ],
        )
