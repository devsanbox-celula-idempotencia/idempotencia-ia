"""Puerto: repositorio de logs de peticiones."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.domain.entities.request_log import RequestLog


class RequestLogRepository(ABC):
    @abstractmethod
    async def add(self, log: RequestLog) -> None: ...

    @abstractmethod
    async def search(
        self,
        api_key_id: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[RequestLog]: ...
