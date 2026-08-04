"""Conteo local con tiktoken. Respaldo si el backend no reporta tokens."""
from __future__ import annotations

from typing import Any

from app.domain.ports.services.token_counter import TokenCounter


class TiktokenCounter(TokenCounter):
    def __init__(self, encoding_name: str = "cl100k_base") -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(encoding_name)

    def count_text(self, model: str, text: str) -> int:
        return len(self._encoding.encode(text or ""))

    def count_messages(self, model: str, messages: list[dict[str, Any]]) -> int:
        return sum(self.count_text(model, str(m.get("content", ""))) + 4 for m in messages)
