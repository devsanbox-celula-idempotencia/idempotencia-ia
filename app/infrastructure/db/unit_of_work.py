"""UnitOfWork con SQLAlchemy async: una sesión, todos los repositorios."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.ports.services.unit_of_work import UnitOfWork
from app.infrastructure.repositories.api_key_repository_impl import SqlAlchemyApiKeyRepository
from app.infrastructure.repositories.model_repository_impl import SqlAlchemyModelRepository
from app.infrastructure.repositories.request_log_repository_impl import SqlAlchemyRequestLogRepository
from app.infrastructure.repositories.usage_repository_impl import SqlAlchemyUsageRepository
from app.infrastructure.repositories.user_repository_impl import SqlAlchemyUserRepository


class SqlAlchemyUnitOfWork(UnitOfWork):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.users = SqlAlchemyUserRepository(session)
        self.api_keys = SqlAlchemyApiKeyRepository(session)
        self.usage = SqlAlchemyUsageRepository(session)
        self.logs = SqlAlchemyRequestLogRepository(session)
        self.models = SqlAlchemyModelRepository(session)

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if exc_type is not None:
            await self.rollback()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def close(self) -> None:
        """Suelta la conexión. La sesión sigue usable: si se vuelve a
        consultar, SQLAlchemy pide otra conexión al pool."""
        await self._session.close()
