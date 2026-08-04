"""Repositorio de logs de peticiones."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.request_log import RequestLog
from app.domain.ports.repositories.request_log_repository import RequestLogRepository
from app.infrastructure.db.mappers import request_log_mapper
from app.infrastructure.db.models.request_log_model import RequestLogModel


class SqlAlchemyRequestLogRepository(RequestLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, log: RequestLog) -> None:
        self._session.add(request_log_mapper.to_model(log))
        await self._session.flush()

    async def search(
        self,
        api_key_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RequestLog]:
        stmt = select(RequestLogModel)
        if api_key_id is not None:
            stmt = stmt.where(RequestLogModel.ApiKeyId == api_key_id)
        if since is not None:
            stmt = stmt.where(RequestLogModel.CreatedAt >= since)
        if until is not None:
            stmt = stmt.where(RequestLogModel.CreatedAt <= until)
        # Desempate por clave primaria: CreatedAt es DATETIME2(0) y bajo carga
        # hay muchas filas con el mismo segundo; sin esto las páginas repiten
        # y se saltan registros.
        stmt = (
            stmt.order_by(RequestLogModel.CreatedAt.desc(), RequestLogModel.RequestLogId.desc())
            .offset(offset)
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [request_log_mapper.to_entity(r) for r in rows]
