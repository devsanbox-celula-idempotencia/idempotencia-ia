"""Entidad Usage: consumo acumulado por API key y día."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Usage:
    api_key_id: int
    day: date
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0
    id: int | None = None

    def add(self, prompt_tokens: int, completion_tokens: int) -> None:
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.total_tokens += prompt_tokens + completion_tokens
        self.requests += 1
