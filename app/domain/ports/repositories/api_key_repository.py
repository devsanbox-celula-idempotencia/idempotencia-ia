"""Puerto: repositorio de API keys."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.api_key import ApiKey


class ApiKeyRepository(ABC):
    @abstractmethod
    async def get_by_hash(self, key_hash: str) -> ApiKey | None: ...

    @abstractmethod
    async def get_by_id(self, api_key_id: int) -> ApiKey | None: ...

    @abstractmethod
    async def list_by_user(self, user_id: int) -> list[ApiKey]: ...

    @abstractmethod
    async def add(self, api_key: ApiKey) -> ApiKey: ...

    @abstractmethod
    async def touch(self, api_key_id: int) -> None: ...

    @abstractmethod
    async def revoke(self, api_key_id: int) -> bool: ...
