"""POST /v1/embeddings."""
from __future__ import annotations

import time

from app.application.dto.embeddings_dto import EmbeddingsInput, EmbeddingsOutput
from app.application.use_cases.admin.record_usage import UsageRecorder
from app.domain.entities.request_log import RequestLog
from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.value_objects.token_usage import TokenUsage


class CreateEmbeddings:
    ENDPOINT = "/v1/embeddings"

    def __init__(self, provider: LLMProvider, record_usage: UsageRecorder) -> None:
        self._provider = provider
        self._record_usage = record_usage

    async def execute(self, data: EmbeddingsInput, provider_model: str) -> EmbeddingsOutput:
        started = time.perf_counter()
        try:
            vectors, usage = await self._provider.embeddings(provider_model, data.inputs)
        except Exception as exc:  # noqa: BLE001
            await self._record_usage.execute(
                RequestLog(
                    api_key_id=data.api_key_id,
                    model=data.model,
                    endpoint=self.ENDPOINT,
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
                endpoint=self.ENDPOINT,
                prompt_tokens=usage.prompt_tokens,
                total_tokens=usage.total_tokens,
                duration_ms=int((time.perf_counter() - started) * 1000),
                status_code=200,
                client_ip=data.client_ip,
            ),
            usage,
        )
        return EmbeddingsOutput(model=data.model, vectors=vectors, usage=usage)
