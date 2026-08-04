"""Resuelve el modelo pedido por el cliente contra el catálogo.

Primero busca en la tabla LlmModels. Si el catálogo aún está vacío, acepta los
modelos listados en ALLOWED_MODELS del .env. Cualquier otro nombre se rechaza:
así nadie puede pedirle a tu servidor que descargue un modelo de 70B.
"""
from __future__ import annotations

from app.domain.entities.model import LLMModel
from app.domain.exceptions import ModelNotFoundError
from app.domain.ports.repositories.model_repository import ModelRepository


class ResolveModel:
    def __init__(self, models: ModelRepository, allowed_models: list[str]) -> None:
        self._models = models
        self._allowed = allowed_models

    async def execute(self, model_id: str) -> LLMModel:
        model = await self._models.get_by_id(model_id)
        if model is not None:
            return model
        if model_id in self._allowed:
            return LLMModel(id=model_id, provider_model=model_id, owned_by="ollama")
        raise ModelNotFoundError(f"El modelo '{model_id}' no está disponible en este gateway")
