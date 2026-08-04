"""Repositorio de API keys."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.api_key import ApiKey
from app.domain.ports.repositories.api_key_repository import ApiKeyRepository
from app.infrastructure.db.mappers import api_key_mapper
from app.infrastructure.db.models.api_key_model import ApiKeyModel


class SqlAlchemyApiKeyRepository(ApiKeyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_hash(self, key_hash: str) -> ApiKey | None:
        stmt = select(ApiKeyModel).where(ApiKeyModel.KeyHash == key_hash)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return api_key_mapper.to_entity(row) if row else None

    async def get_by_id(self, api_key_id: int) -> ApiKey | None:
        row = await self._session.get(ApiKeyModel, api_key_id)
        return api_key_mapper.to_entity(row) if row else None

    async def list_by_user(self, user_id: int) -> list[ApiKey]:
        stmt = (
            select(ApiKeyModel)
            .where(ApiKeyModel.UserId == user_id)
            .order_by(ApiKeyModel.CreatedAt.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [api_key_mapper.to_entity(r) for r in rows]

    async def add(self, api_key: ApiKey) -> ApiKey:
        row = api_key_mapper.to_model(api_key)
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return api_key_mapper.to_entity(row)

    async def touch(self, api_key_id: int) -> None:
        stmt = (
            update(ApiKeyModel)
            .where(ApiKeyModel.ApiKeyId == api_key_id)
            .values(LastUsedAt=datetime.now(timezone.utc).replace(tzinfo=None))
        )
        await self._session.execute(stmt)

    async def revoke(self, api_key_id: int) -> bool:
        stmt = update(ApiKeyModel).where(ApiKeyModel.ApiKeyId == api_key_id).values(IsActive=False)
        result = await self._session.execute(stmt)
        return bool(result.rowcount)
