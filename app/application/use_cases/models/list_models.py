"""Casos de uso de catálogo: GET /v1/models."""
from __future__ import annotations

from app.domain.entities.model import LLMModel
from app.domain.exceptions import ModelNotFoundError
from app.domain.ports.repositories.model_repository import ModelRepository


class ListModels:
    def __init__(self, models: ModelRepository, allowed_models: list[str] | None = None) -> None:
        self._models = models
        self._allowed = allowed_models or []

    async def execute(self) -> list[LLMModel]:
        catalog = await self._models.list_all()
        if catalog:
            return catalog
        # Catálogo vacío: se expone lo declarado en el .env
        return [LLMModel(id=m, provider_model=m, owned_by="ollama") for m in self._allowed]


class RetrieveModel:
    def __init__(self, models: ModelRepository, allowed_models: list[str] | None = None) -> None:
        self._models = models
        self._allowed = allowed_models or []

    async def execute(self, model_id: str) -> LLMModel:
        model = await self._models.get_by_id(model_id)
        if model is not None:
            return model
        if model_id in self._allowed:
            return LLMModel(id=model_id, provider_model=model_id, owned_by="ollama")
        raise ModelNotFoundError(f"El modelo '{model_id}' no existe")
