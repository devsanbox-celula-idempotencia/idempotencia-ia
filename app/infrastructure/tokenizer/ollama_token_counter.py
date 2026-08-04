"""Conteo de tokens usando lo que ya reporta Ollama, con respaldo aproximado."""
from __future__ import annotations

from typing import Any

from app.domain.ports.services.token_counter import TokenCounter
from app.domain.value_objects.token_usage import TokenUsage

_CHARS_PER_TOKEN = 4  # aproximación cuando el backend no reporta el conteo


class OllamaTokenCounter(TokenCounter):
    @staticmethod
    def from_response(response: dict[str, Any]) -> TokenUsage:
        return TokenUsage(
            prompt_tokens=int(response.get("prompt_eval_count") or 0),
            completion_tokens=int(response.get("eval_count") or 0),
        )

    def count_text(self, model: str, text: str) -> int:
        return max(1, len(text) // _CHARS_PER_TOKEN)

    def count_messages(self, model: str, messages: list[dict[str, Any]]) -> int:
        total = 0
        for message in messages:
            total += self.count_text(model, str(message.get("content", "")))
            total += 4  # sobrecarga por mensaje (role, separadores)
        return total
