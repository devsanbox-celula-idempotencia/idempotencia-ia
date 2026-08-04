"""Consulta del historial de peticiones."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from app.application.use_cases.admin.list_request_logs import ListRequestLogs
from app.presentation.dependencies import UowDep, require_admin
from app.presentation.schemas.admin.usage_schemas import RequestLogResponse

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin)])


def _naive_utc(value: datetime | None) -> datetime | None:
    """CreatedAt es DATETIME2 sin zona (UTC). pyodbc ignora el tzinfo de los
    parámetros, así que una fecha con offset desplazaría la ventana."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.get("/logs", response_model=list[RequestLogResponse], summary="Historial de peticiones")
async def list_logs(
    uow: UowDep,
    api_key_id: int | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    # SQL Server rechaza FETCH con 0 filas y OFFSET negativo: sin las cotas de
    # arriba, ?limit=0 devolvería un 500 en vez de un 422.
    logs = await ListRequestLogs(uow).execute(
        api_key_id, _naive_utc(since), _naive_utc(until), limit, offset
    )
    return [
        RequestLogResponse(
            id=log.id or 0,
            api_key_id=log.api_key_id,
            model=log.model,
            endpoint=log.endpoint,
            prompt_tokens=log.prompt_tokens,
            completion_tokens=log.completion_tokens,
            total_tokens=log.total_tokens,
            duration_ms=log.duration_ms,
            status_code=log.status_code,
            error=log.error,
            created_at=log.created_at,
        )
        for log in logs
    ]
