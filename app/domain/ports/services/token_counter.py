"""Puerto del contador de tokens.

Opción 1: usar prompt_eval_count / eval_count que devuelve Ollama.
Opción 2: calcularlos localmente (tiktoken o el tokenizer del modelo).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class TokenCounter(ABC):
    @abstractmethod
    def count_text(self, model: str, text: str) -> int: ...

    @abstractmethod
    def count_messages(self, model: str, messages: list[dict[str, Any]]) -> int: ...
