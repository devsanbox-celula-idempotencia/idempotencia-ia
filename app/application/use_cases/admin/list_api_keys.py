"""Listar las API keys de un usuario."""
from __future__ import annotations

from app.domain.entities.api_key import ApiKey
from app.domain.ports.services.unit_of_work import UnitOfWork


class ListApiKeys:
    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, user_id: int) -> list[ApiKey]:
        return await self._uow.api_keys.list_by_user(user_id)
