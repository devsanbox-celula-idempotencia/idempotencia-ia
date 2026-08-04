"""POST /v1/completions — API legacy de OpenAI."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from app.application.dto.chat_dto import ChatCompletionInput
from app.application.use_cases.chat.create_chat_completion import CreateChatCompletion
from app.application.use_cases.chat.create_completion import CreateCompletion
from app.application.use_cases.models.resolve_model import ResolveModel
from app.infrastructure.llm.openai_mapper import normalize_stop
from app.presentation.dependencies import (
    LimitedApiKeyDep,
    ProviderDep,
    SettingsDep,
    UowDep,
    UsageRecorderDep,
    client_ip,
)
from app.presentation.schemas.openai.chat import Usage
from app.presentation.schemas.openai.completions import (
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
)

router = APIRouter(tags=["OpenAI Compatible"])


@router.post(
    "/completions",
    response_model=CompletionResponse,
    summary="Crear un completion",
    description="API legacy. Para streaming usa `/v1/chat/completions` con `stream=true`.",
)
async def create_completion(
    payload: CompletionRequest,
    request: Request,
    api_key: LimitedApiKeyDep,
    uow: UowDep,
    provider: ProviderDep,
    recorder: UsageRecorderDep,
    settings: SettingsDep,
):
    if payload.stream:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El streaming solo está soportado en /v1/chat/completions",
        )
    if payload.n is not None and payload.n > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este gateway solo genera una respuesta por petición (n=1)",
        )

    prompt = payload.prompt if isinstance(payload.prompt, str) else "\n".join(payload.prompt)
    model = await ResolveModel(uow.models, settings.ALLOWED_MODELS).execute(payload.model)

    data = ChatCompletionInput(
        api_key_id=api_key.id,
        model=payload.model,
        messages=[],
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
        stop=normalize_stop(payload.stop),
        presence_penalty=payload.presence_penalty,
        frequency_penalty=payload.frequency_penalty,
        client_ip=client_ip(request),
    )
    await uow.close()   # ver comentario en chat.py: no retener la conexión
    chat_use_case = CreateChatCompletion(provider, recorder, endpoint="/v1/completions")
    result = await CreateCompletion(chat_use_case).execute(data, prompt, model.provider_model)

    return CompletionResponse(
        id=result.id,
        created=result.created,
        model=result.model,
        choices=[CompletionChoice(index=0, text=result.content, finish_reason=result.finish_reason)],
        usage=Usage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
