"""Registrar consumo y log tras atender una petición. Uso interno."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Protocol

from app.domain.entities.request_log import RequestLog
from app.domain.ports.services.unit_of_work import UnitOfWork
from app.domain.value_objects.token_usage import TokenUsage


class UsageRecorder(Protocol):
    """Contrato mínimo que necesitan los casos de uso de chat/embeddings."""

    async def execute(self, log: RequestLog, usage: TokenUsage) -> None: ...


class RecordUsage:
    """Dos fases independientes, deliberadamente separadas.

    El consumo es lo que se cobra; el log es auditoría. Si falla el log, el
    consumo ya quedó guardado y no debe arrastrarse.

    Como cada fase confirma su propia transacción, quien reintente debe hacerlo
    POR FASE: reintentar el conjunto volvería a aplicar un incremento ya
    confirmado y cobraría el doble.
    """

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def increment_usage(self, log: RequestLog, usage: TokenUsage) -> None:
        if log.api_key_id is None or usage.total_tokens <= 0:
            return
        day = datetime.now(timezone.utc).date()   # UTC, igual que SYSUTCDATETIME()
        await self._uow.usage.increment(log.api_key_id, day, usage)
        await self._uow.commit()

    async def add_log(self, log: RequestLog) -> None:
        await self._uow.logs.add(log)
        await self._uow.commit()

    async def execute(self, log: RequestLog, usage: TokenUsage) -> None:
        await self.increment_usage(log, usage)
        await self.add_log(log)
