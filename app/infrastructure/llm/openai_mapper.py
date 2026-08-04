"""Traducción entre el formato de OpenAI y el de Ollama."""
from __future__ import annotations

import secrets
import time
from typing import Any


def normalize_stop(stop: "list[str] | str | None") -> list[str] | None:
    """`stop` de OpenAI acepta str o lista; Ollama siempre quiere lista.

    Las cadenas vacías se descartan: una secuencia de parada vacía casa en la
    posición 0 y el modelo devolvería una respuesta vacía, facturada igual.
    """
    if stop is None:
        return None
    secuencias = [stop] if isinstance(stop, str) else list(stop)
    secuencias = [s for s in secuencias if s]
    return secuencias or None


def new_completion_id(prefix: str = "chatcmpl") -> str:
    return f"{prefix}-{secrets.token_hex(12)}"


def build_ollama_options(
    temperature: float | None = None,
    top_p: float | None = None,
    max_tokens: int | None = None,
    stop: list[str] | None = None,
    presence_penalty: float | None = None,
    frequency_penalty: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Parámetros de OpenAI -> bloque `options` de Ollama."""
    options: dict[str, Any] = {}
    if temperature is not None:
        options["temperature"] = temperature
    if top_p is not None:
        options["top_p"] = top_p
    if max_tokens is not None:
        options["num_predict"] = max_tokens
    if stop:
        options["stop"] = stop
    if presence_penalty is not None:
        options["presence_penalty"] = presence_penalty
    if frequency_penalty is not None:
        options["frequency_penalty"] = frequency_penalty
    if extra:
        # 'model' y 'messages' viajan como argumentos propios del provider:
        # dejarlos entrar aquí provocaría un TypeError al expandir **options.
        options.update({k: v for k, v in extra.items() if k not in {"model", "messages"}})
    return options


def finish_reason_from_ollama(payload: dict[str, Any]) -> str:
    """`done_reason` de Ollama -> `finish_reason` de OpenAI.

    Sin esto, un cliente no puede distinguir una respuesta completa de una
    cortada por max_tokens.
    """
    return "length" if payload.get("done_reason") == "length" else "stop"


def usage_from_ollama(response: dict[str, Any]) -> tuple[int, int]:
    """(prompt_tokens, completion_tokens) a partir de la respuesta de Ollama."""
    return int(response.get("prompt_eval_count") or 0), int(response.get("eval_count") or 0)


def chat_response_to_openai(
    content: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    finish_reason: str = "stop",
    completion_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": completion_id or new_completion_id(),
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


def chunk_to_openai(
    delta: str | None,
    model: str,
    completion_id: str,
    created: int,
    finish_reason: str | None = None,
    role: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if role:
        payload["role"] = role
    if delta is not None:
        payload["content"] = delta
    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": payload, "finish_reason": finish_reason}],
    }


def models_to_openai(models: list[Any]) -> dict[str, Any]:
    return {
        "object": "list",
        "data": [
            {
                "id": m.id,
                "object": "model",
                "created": int(m.created_at.timestamp()) if m.created_at else 0,
                "owned_by": m.owned_by,
            }
            for m in models
        ],
    }
