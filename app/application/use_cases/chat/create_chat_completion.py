"""POST /v1/chat/completions sin streaming.

El modelo llega ya resuelto desde la capa de presentación, para no consultar
el catálogo dos veces en la misma petición.
"""
from __future__ import annotations

import time
from dataclasses import asdict

from app.application.dto.chat_dto import ChatCompletionInput, ChatCompletionOutput
from app.application.use_cases.admin.record_usage import UsageRecorder
from app.domain.entities.request_log import RequestLog
from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.value_objects.token_usage import TokenUsage
from app.infrastructure.llm.openai_mapper import build_ollama_options, new_completion_id


class CreateChatCompletion:
    ENDPOINT = "/v1/chat/completions"

    def __init__(
        self,
        provider: LLMProvider,
        record_usage: UsageRecorder,
        endpoint: str | None = None,
    ) -> None:
        self._provider = provider
        self._record_usage = record_usage
        # /v1/completions reutiliza este caso de uso; el log debe registrar la
        # ruta por la que entró la petición, no la de chat.
        self._endpoint = endpoint or self.ENDPOINT

    async def execute(self, data: ChatCompletionInput, provider_model: str) -> ChatCompletionOutput:
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

        try:
            content, usage, finish_reason = await self._provider.chat(
                provider_model, messages, **options
            )
        except Exception as exc:  # noqa: BLE001
            await self._record_usage.execute(
                RequestLog(
                    api_key_id=data.api_key_id,
                    model=data.model,
                    endpoint=self._endpoint,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    status_code=502,
                    client_ip=data.client_ip,
                    error=str(exc)[:1000],
                ),
                TokenUsage(0, 0),
            )
            raise

        await self._record_usage.execute(
            RequestLog(
                api_key_id=data.api_key_id,
                model=data.model,
                endpoint=self._endpoint,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                total_tokens=usage.total_tokens,
                duration_ms=int((time.perf_counter() - started) * 1000),
                status_code=200,
                client_ip=data.client_ip,
            ),
            usage,
        )

        return ChatCompletionOutput(
            id=new_completion_id(),
            model=data.model,
            content=content,
            finish_reason=finish_reason,
            usage=usage,
            created=int(time.time()),
        )
