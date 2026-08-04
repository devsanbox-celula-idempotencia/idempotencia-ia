"""Adaptador que implementa LLMProvider usando Ollama."""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from app.domain.entities.model import LLMModel
from app.domain.exceptions import ProviderError
from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.value_objects.token_usage import TokenUsage
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.openai_mapper import finish_reason_from_ollama, usage_from_ollama


class OllamaProvider(LLMProvider):
    def __init__(self, client: OllamaClient) -> None:
        self._client = client

    async def list_models(self) -> list[LLMModel]:
        data = await self._client.tags()
        return [
            LLMModel(id=m["name"], provider_model=m["name"], owned_by="ollama")
            for m in data.get("models", [])
        ]

    async def chat(
        self, model: str, messages: list[dict[str, Any]], **options: Any
    ) -> tuple[str, TokenUsage, str]:
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if options:
            payload["options"] = options
        response = await self._client.chat(payload)
        content = (response.get("message") or {}).get("content", "")
        prompt_tokens, completion_tokens = usage_from_ollama(response)
        return (
            content,
            TokenUsage(prompt_tokens, completion_tokens),
            finish_reason_from_ollama(response),
        )

    async def chat_stream(
        self, model: str, messages: list[dict[str, Any]], **options: Any
    ) -> AsyncIterator[dict[str, Any]]:
        payload: dict[str, Any] = {"model": model, "messages": messages}
        if options:
            payload["options"] = options
        async for chunk in self._client.chat_stream(payload):
            yield chunk

    async def embeddings(self, model: str, inputs: list[str]) -> tuple[list[list[float]], TokenUsage]:
        response = await self._client.embeddings({"model": model, "input": inputs})
        vectors = response.get("embeddings") or []
        if not vectors:
            raise ProviderError("Ollama no devolvió embeddings; ¿el modelo los soporta?")
        prompt_tokens = int(response.get("prompt_eval_count") or 0)
        return vectors, TokenUsage(prompt_tokens, 0)

    async def health(self) -> bool:
        return await self._client.health()
