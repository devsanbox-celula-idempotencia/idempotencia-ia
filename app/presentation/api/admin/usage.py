"""Consulta de consumo por API key."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends

from app.application.dto.usage_dto import UsageQueryInput
from app.application.use_cases.admin.get_usage import GetUsage
from app.presentation.dependencies import UowDep, require_admin
from app.presentation.schemas.admin.usage_schemas import DailyUsageResponse, UsageSummaryResponse

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin)])


@router.get("/usage", response_model=UsageSummaryResponse, summary="Consumo por rango de fechas")
async def get_usage(start: date, end: date, uow: UowDep, api_key_id: int | None = None):
    result = await GetUsage(uow).execute(UsageQueryInput(start=start, end=end, api_key_id=api_key_id))
    return UsageSummaryResponse(
        api_key_id=result.api_key_id,
        total_requests=result.total_requests,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        days=[
            DailyUsageResponse(
                day=d.day,
                requests=d.requests,
                prompt_tokens=d.prompt_tokens,
                completion_tokens=d.completion_tokens,
                total_tokens=d.total_tokens,
            )
            for d in result.days
        ],
    )
