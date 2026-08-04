"""Repositorio de usuarios sobre la tabla Users existente."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.user import User
from app.domain.ports.repositories.user_repository import UserRepository
from app.infrastructure.db.mappers import user_mapper
from app.infrastructure.db.models.user_model import UserModel


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, user_id: int) -> User | None:
        row = await self._session.get(UserModel, user_id)
        return user_mapper.to_entity(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.Email == email)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return user_mapper.to_entity(row) if row else None
