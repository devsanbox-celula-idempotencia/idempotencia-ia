"""Autenticar la API key entrante (Authorization: Bearer sk_live_...)."""
from __future__ import annotations

from datetime import datetime, timezone

from app.domain.entities.api_key import ApiKey
from app.domain.exceptions import InvalidApiKeyError
from app.domain.ports.services.password_hasher import KeyHasher
from app.domain.ports.services.unit_of_work import UnitOfWork


class AuthenticateApiKey:
    def __init__(self, uow: UnitOfWork, hasher: KeyHasher) -> None:
        self._uow = uow
        self._hasher = hasher

    async def execute(self, raw_key: str) -> ApiKey:
        if not raw_key:
            raise InvalidApiKeyError("Falta la API key")

        key_hash = self._hasher.hash(raw_key)
        api_key = await self._uow.api_keys.get_by_hash(key_hash)
        if api_key is None:
            raise InvalidApiKeyError("API key inválida")

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if not api_key.is_usable(now):
            raise InvalidApiKeyError("API key inactiva o expirada")

        await self._uow.api_keys.touch(api_key.id)
        await self._uow.commit()
        api_key.touch(now)
        return api_key
