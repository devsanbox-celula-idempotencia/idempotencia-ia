"""Puerto Unit of Work: agrupa repositorios en una sola transacción."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.ports.repositories.api_key_repository import ApiKeyRepository
from app.domain.ports.repositories.model_repository import ModelRepository
from app.domain.ports.repositories.request_log_repository import RequestLogRepository
from app.domain.ports.repositories.usage_repository import UsageRepository
from app.domain.ports.repositories.user_repository import UserRepository


class UnitOfWork(ABC):
    users: UserRepository
    api_keys: ApiKeyRepository
    usage: UsageRepository
    logs: RequestLogRepository
    models: ModelRepository

    @abstractmethod
    async def __aenter__(self) -> "UnitOfWork": ...

    @abstractmethod
    async def __aexit__(self, *args: object) -> None: ...

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...

    @abstractmethod
    async def close(self) -> None:
        """Devuelve la conexión al pool.

        Importante antes de una operación lenta (la llamada al modelo puede
        tardar decenas de segundos): si no se suelta, el servidor de base de
        datos cierra la conexión por inactividad y el siguiente INSERT falla.
        """
