"""POST /v1/chat/completions con stream=True.

Reenvía los chunks a medida que llegan y contabiliza el consumo al cerrar
(Ollama manda prompt_eval_count/eval_count en el último chunk).

El modelo se resuelve fuera de este caso de uso, mientras la sesión de la
petición sigue viva; aquí solo se recibe el nombre real del backend.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator
from dataclasses import asdict
from typing import Any

from app.application.dto.chat_dto import ChatCompletionInput
from app.application.use_cases.admin.record_usage import UsageRecorder
from app.domain.entities.request_log import RequestLog
from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.value_objects.token_usage import TokenUsage
from app.infrastructure.llm.openai_mapper import build_ollama_options, new_completion_id


class StreamChatCompletion:
    ENDPOINT = "/v1/chat/completions"

    def __init__(self, provider: LLMProvider, record_usage: UsageRecorder) -> None:
        self._provider = provider
        self._record_usage = record_usage

    async def execute(self, data: ChatCompletionInput, provider_model: str) -> AsyncIterator[dict[str, Any]]:
        started = time.perf_counter()
        messages = [asdict(m) for m in data.messages]
        options = build_ollama_options(
            temperature=data.temperature,
            top_p=data.top_p,
            max_tokens=data.max_tokens,
            stop=data.stop,
            presence_penalty=data.presence_penalty,
            frequency_penalty=data.frequency_penalty,
            extra=data.extra,
        )

        completion_id = new_completion_id()
        created = int(time.time())
        prompt_tokens = completion_tokens = 0
        status_code = 200
        error: str | None = None
        finish_reason = "stop"
        first = True

        try:
            async for chunk in self._provider.chat_stream(provider_model, messages, **options):
                done = bool(chunk.get("done"))
                delta = (chunk.get("message") or {}).get("content", "")
                if done:
                    prompt_tokens = int(chunk.get("prompt_eval_count") or 0)
                    completion_tokens = int(chunk.get("eval_count") or 0)
                    finish_reason = (
                        "length" if chunk.get("done_reason") == "length" else "stop"
                    )

                yield {
                    "completion_id": completion_id,
                    "created": created,
                    "model": data.model,
                    "delta": delta,
                    "role": "assistant" if first else None,
                    "done": done,
                    "finish_reason": finish_reason if done else None,
                }
                # El rol solo se marca en el primer evento que de verdad se
                # emite: Ollama suele mandar un primer chunk con content vacío.
                if delta or done:
                    first = False
        except Exception as exc:  # noqa: BLE001
            # El 200 ya salió: no se puede convertir en un error HTTP, pero sí auditarlo.
            status_code, error = 502, str(exc)[:1000]
            raise
        finally:
            # También se ejecuta si el cliente corta la conexión; por eso
            # ScopedRecordUsage protege el registro con un CancelScope(shield=True).
            usage = TokenUsage(prompt_tokens, completion_tokens)
            await self._record_usage.execute(
                RequestLog(
                    api_key_id=data.api_key_id,
                    model=data.model,
                    endpoint=self.ENDPOINT,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    total_tokens=usage.total_tokens,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    status_code=status_code,
                    client_ip=data.client_ip,
                    error=error,
                ),
                usage,
            )
