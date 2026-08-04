"""DTOs de embeddings."""
from __future__ import annotations

from dataclasses import dataclass

from app.domain.value_objects.token_usage import TokenUsage


@dataclass(slots=True)
class EmbeddingsInput:
    api_key_id: int
    model: str
    inputs: list[str]
    client_ip: str | None = None


@dataclass(slots=True)
class EmbeddingsOutput:
    model: str
    vectors: list[list[float]]
    usage: TokenUsage
