"""Consultar el historial de peticiones."""
from __future__ import annotations

from datetime import datetime

from app.domain.entities.request_log import RequestLog
from app.domain.ports.services.unit_of_work import UnitOfWork


class ListRequestLogs:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(
        self,
        api_key_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RequestLog]:
        return await self._uow.logs.search(api_key_id, since, until, limit, offset)
