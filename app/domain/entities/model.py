"""Entidad LLMModel: modelo expuesto por el gateway (p.ej. qwen2.5:3b)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class LLMModel:
    id: str                  # nombre público que ve el cliente
    provider_model: str      # nombre real en Ollama
    owned_by: str = "local"
    context_length: int | None = None
    supports_embeddings: bool = False
    is_active: bool = True
    created_at: datetime | None = None
