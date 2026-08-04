"""Crear una API key. La clave en claro se devuelve una única vez."""
from __future__ import annotations

from datetime import datetime, timezone

from app.application.dto.api_key_dto import CreateApiKeyInput, CreateApiKeyOutput
from app.domain.entities.api_key import ApiKey
from app.domain.exceptions import DomainError
from app.domain.ports.services.password_hasher import KeyGenerator, KeyHasher
from app.domain.ports.services.unit_of_work import UnitOfWork


class CreateApiKey:
    def __init__(self, uow: UnitOfWork, generator: KeyGenerator, hasher: KeyHasher) -> None:
        self._uow = uow
        self._generator = generator
        self._hasher = hasher

    async def execute(self, data: CreateApiKeyInput) -> CreateApiKeyOutput:
        user = await self._uow.users.get_by_id(data.user_id)
        if user is None:
            raise DomainError(f"No existe el usuario {data.user_id}")

        raw_key = self._generator.generate()
        entity = ApiKey(
            id=0,
            user_id=data.user_id,
            name=data.name,
            key_hash=self._hasher.hash(raw_key),
            key_prefix=raw_key[:12],
            is_active=True,
            expires_at=data.expires_at,
            daily_token_limit=data.daily_token_limit,
            monthly_token_limit=data.monthly_token_limit,
            requests_per_minute=data.requests_per_minute,
        )
        created = await self._uow.api_keys.add(entity)
        await self._uow.commit()

        return CreateApiKeyOutput(
            id=created.id,
            name=created.name,
            raw_key=raw_key,
            created_at=created.created_at or datetime.now(timezone.utc).replace(tzinfo=None),
        )
