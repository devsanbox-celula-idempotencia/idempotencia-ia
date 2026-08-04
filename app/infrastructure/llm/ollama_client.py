"""Cliente HTTP asíncrono contra la API de Ollama."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.domain.exceptions import ProviderError
from app.infrastructure.config.settings import get_settings


class OllamaClient:
    def __init__(self, base_url: str | None = None, timeout: int | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self._timeout = timeout or settings.OLLAMA_TIMEOUT_SECONDS
        self._client = httpx.AsyncClient(base_url=self._base_url, timeout=self._timeout)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(path, json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            raise ProviderError(f"Ollama respondió {exc.response.status_code}: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"No se pudo contactar a Ollama: {exc}") from exc

    async def tags(self) -> dict[str, Any]:
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError as exc:
            raise ProviderError(f"No se pudo contactar a Ollama: {exc}") from exc

    async def chat(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/api/chat", {**payload, "stream": False})

    async def chat_stream(self, payload: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        """Ollama devuelve NDJSON: un objeto JSON por línea."""
        body = {**payload, "stream": True}
        try:
            async with self._client.stream("POST", "/api/chat", json=body) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    yield json.loads(line)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Error en el stream de Ollama: {exc}") from exc

    async def generate(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/api/generate", {**payload, "stream": False})

    async def embeddings(self, payload: dict[str, Any]) -> dict[str, Any]:
        return await self._post("/api/embed", payload)

    async def health(self) -> bool:
        try:
            response = await self._client.get("/api/version")
            return response.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
