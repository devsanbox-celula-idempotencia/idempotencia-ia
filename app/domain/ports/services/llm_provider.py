"""Puerto del proveedor de LLM.

Esta es la abstracción clave del proyecto: hoy la implementa Ollama, mañana
puede implementarla vLLM, OpenAI o Anthropic sin tocar los casos de uso.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.domain.entities.model import LLMModel
from app.domain.value_objects.token_usage import TokenUsage


class LLMProvider(ABC):
    @abstractmethod
    async def list_models(self) -> list[LLMModel]: ...

    @abstractmethod
    async def chat(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **options: Any,
    ) -> tuple[str, TokenUsage, str]:
        """Respuesta completa (no streaming).

        Devuelve (texto, consumo, finish_reason). El finish_reason distingue
        una respuesta completa de una cortada por límite de tokens.
        """

    @abstractmethod
    def chat_stream(
        self,
        model: str,
        messages: list[dict[str, Any]],
        **options: Any,
    ) -> AsyncIterator[dict[str, Any]]:
        """Chunks del backend; la capa presentation los traduce a SSE de OpenAI."""

    @abstractmethod
    async def embeddings(self, model: str, inputs: list[str]) -> tuple[list[list[float]], TokenUsage]: ...

    @abstractmethod
    async def health(self) -> bool: ...
