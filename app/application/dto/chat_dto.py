"""DTOs de los casos de uso de chat, independientes de FastAPI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.value_objects.token_usage import TokenUsage


@dataclass(slots=True)
class ChatMessageDTO:
    role: str
    content: str


@dataclass(slots=True)
class ChatCompletionInput:
    api_key_id: int
    model: str
    messages: list[ChatMessageDTO]
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    stop: list[str] | None = None
    stream: bool = False
    presence_penalty: float | None = None
    frequency_penalty: float | None = None
    client_ip: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ChatCompletionOutput:
    id: str
    model: str
    content: str
    finish_reason: str
    usage: TokenUsage
    created: int
