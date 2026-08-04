"""POST /v1/embeddings."""
from __future__ import annotations

from fastapi import APIRouter, Request

from app.application.dto.embeddings_dto import EmbeddingsInput
from app.application.use_cases.embeddings.create_embeddings import CreateEmbeddings
from app.application.use_cases.models.resolve_model import ResolveModel
from app.presentation.dependencies import (
    LimitedApiKeyDep,
    ProviderDep,
    SettingsDep,
    UowDep,
    UsageRecorderDep,
    client_ip,
)
from app.presentation.schemas.openai.chat import Usage
from app.presentation.schemas.openai.embeddings import (
    EmbeddingItem,
    EmbeddingsRequest,
    EmbeddingsResponse,
)

router = APIRouter(tags=["OpenAI Compatible"])


@router.post("/embeddings", response_model=EmbeddingsResponse, summary="Crear embeddings")
async def create_embeddings(
    payload: EmbeddingsRequest,
    request: Request,
    api_key: LimitedApiKeyDep,
    uow: UowDep,
    provider: ProviderDep,
    recorder: UsageRecorderDep,
    settings: SettingsDep,
):
    inputs = [payload.input] if isinstance(payload.input, str) else payload.input
    model = await ResolveModel(uow.models, settings.ALLOWED_MODELS).execute(payload.model)

    await uow.close()   # ver comentario en chat.py: no retener la conexión
    result = await CreateEmbeddings(provider, recorder).execute(
        EmbeddingsInput(
            api_key_id=api_key.id,
            model=payload.model,
            inputs=inputs,
            client_ip=client_ip(request),
        ),
        model.provider_model,
    )
    return EmbeddingsResponse(
        data=[EmbeddingItem(index=i, embedding=v) for i, v in enumerate(result.vectors)],
        model=result.model,
        usage=Usage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
