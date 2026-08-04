"""Revocar una API key."""
from __future__ import annotations

from app.domain.exceptions import DomainError
from app.domain.ports.services.unit_of_work import UnitOfWork


class RevokeApiKey:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, api_key_id: int) -> None:
        revoked = await self._uow.api_keys.revoke(api_key_id)
        if not revoked:
            raise DomainError(f"No existe la API key {api_key_id}")
        await self._uow.commit()
