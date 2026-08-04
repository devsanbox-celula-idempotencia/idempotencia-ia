"""Puerto: catálogo de modelos habilitados en el gateway."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.entities.model import LLMModel


class ModelRepository(ABC):
    @abstractmethod
    async def list_all(self) -> list[LLMModel]: ...

    @abstractmethod
    async def get_by_id(self, model_id: str) -> LLMModel | None: ...
