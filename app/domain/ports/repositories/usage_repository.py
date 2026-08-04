"""Puerto: repositorio de consumo acumulado."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date

from app.domain.entities.usage import Usage
from app.domain.value_objects.token_usage import TokenUsage


class UsageRepository(ABC):
    @abstractmethod
    async def increment(self, api_key_id: int, day: date, usage: TokenUsage) -> None: ...

    @abstractmethod
    async def get_daily(self, api_key_id: int, day: date) -> Usage | None: ...

    @abstractmethod
    async def get_range(self, api_key_id: int | None, start: date, end: date) -> list[Usage]: ...

    @abstractmethod
    async def tokens_since(self, api_key_id: int, start: date) -> int: ...
