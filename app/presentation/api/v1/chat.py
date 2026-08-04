"""POST /v1/chat/completions — endpoint principal, compatible con OpenAI."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from app.application.dto.chat_dto import ChatCompletionInput, ChatMessageDTO
from app.application.use_cases.chat.create_chat_completion import CreateChatCompletion
from app.application.use_cases.chat.stream_chat_completion import StreamChatCompletion
from app.application.use_cases.models.resolve_model import ResolveModel
from app.domain.exceptions import ProviderError
from app.infrastructure.llm.openai_mapper import chunk_to_openai, normalize_stop
from app.presentation.dependencies import (
    LimitedApiKeyDep,
    ProviderDep,
    SettingsDep,
    UowDep,
    UsageRecorderDep,
    client_ip,
)
from app.presentation.schemas.openai.chat import (
    ChatCompletionChoice,
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatMessage,
    Usage,
)

router = APIRouter(tags=["OpenAI Compatible"])


def _events(item: dict) -> list[str]:
    """Un chunk del caso de uso -> una o dos líneas SSE.

    El último chunk puede traer texto además de `done`: primero se emite ese
    contenido y después el chunk con `finish_reason`, para no perder tokens.
    """
    lines: list[str] = []
    if item["delta"]:
        lines.append(
            chunk_to_openai(
                item["delta"], item["model"], item["completion_id"], item["created"], role=item["role"]
            )
        )
    if item["done"]:
        lines.append(
            chunk_to_openai(
                None,
                item["model"],
                item["completion_id"],
                item["created"],
                finish_reason=item.get("finish_reason") or "stop",
            )
        )
    return [f"data: {json.dumps(line)}\n\n" for line in lines]


async def _sse_stream(first: dict, rest: AsyncIterator[dict]) -> AsyncIterator[str]:
    """El primer chunk ya se consumió para poder devolver un error HTTP limpio
    si Ollama no responde; a partir de ahí se reenvía tal cual."""
    try:
        for line in _events(first):
            yield line
        async for item in rest:
            for line in _events(item):
                yield line
        yield "data: [DONE]\n\n"
    finally:
        # Cerrar el generador externo no cierra el interno: hay que hacerlo a
        # mano para que su `finally` (el que audita el consumo) corra siempre.
        await rest.aclose()


@router.post(
    "/chat/completions",
    response_model=ChatCompletionResponse,
    summary="Crear un chat completion",
    description=(
        "Compatible con el SDK oficial de OpenAI.\n\n"
        "```python\n"
        "client = OpenAI(api_key='sk_live_xxx', base_url='http://localhost:8000/v1')\n"
        "```\n\n"
        "Con `stream=true` la respuesta es un stream SSE de `chat.completion.chunk`."
    ),
)
async def create_chat_completion(
    payload: ChatCompletionRequest,
    request: Request,
    api_key: LimitedApiKeyDep,
    uow: UowDep,
    provider: ProviderDep,
    recorder: UsageRecorderDep,
    settings: SettingsDep,
):
    if payload.n is not None and payload.n > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Este gateway solo genera una respuesta por petición (n=1)",
        )

    # El modelo se resuelve aquí, mientras la sesión de la petición sigue viva.
    model = await ResolveModel(uow.models, settings.ALLOWED_MODELS).execute(payload.model)

    data = ChatCompletionInput(
        api_key_id=api_key.id,
        model=payload.model,
        messages=[ChatMessageDTO(role=m.role, content=m.content) for m in payload.messages],
        temperature=payload.temperature,
        top_p=payload.top_p,
        max_tokens=payload.max_tokens,
        stop=normalize_stop(payload.stop),
        stream=payload.stream,
        presence_penalty=payload.presence_penalty,
        frequency_penalty=payload.frequency_penalty,
        client_ip=client_ip(request),
    )

    # A partir de aquí no se usa más la base de datos hasta el registro final,
    # y la llamada al modelo puede tardar decenas de segundos. Soltar la
    # conexión evita que el servidor la cierre por inactividad (error 08S01).
    await uow.close()

    if payload.stream:
        chunks = StreamChatCompletion(provider, recorder).execute(
            data, model.provider_model
        )
        # Consumir el primer chunk aquí permite responder con un error HTTP
        # limpio; una vez enviado el 200 ya no se puede cambiar el estado.
        try:
            first = await anext(chunks)
        except StopAsyncIteration:
            raise ProviderError("Ollama no devolvió ningún chunk") from None
        return StreamingResponse(
            _sse_stream(first, chunks),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    result = await CreateChatCompletion(provider, recorder).execute(
        data, model.provider_model
    )

    return ChatCompletionResponse(
        id=result.id,
        created=result.created,
        model=result.model,
        choices=[
            ChatCompletionChoice(
                index=0,
                message=ChatMessage(role="assistant", content=result.content),
                finish_reason=result.finish_reason,
            )
        ],
        usage=Usage(
            prompt_tokens=result.usage.prompt_tokens,
            completion_tokens=result.usage.completion_tokens,
            total_tokens=result.usage.total_tokens,
        ),
    )
