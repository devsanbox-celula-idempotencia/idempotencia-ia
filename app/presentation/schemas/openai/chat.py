"""Schemas compatibles con OpenAI para /v1/chat/completions.

Si estos schemas coinciden con los de OpenAI, el SDK oficial funciona
cambiando únicamente base_url.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"] = Field(
        description="Rol del autor. Va en inglés: es el contrato de OpenAI."
    )
    content: str = Field(description="El texto del mensaje.")
    name: str | None = Field(
        default=None,
        description="Identificador opcional del autor. NO es el contenido del mensaje.",
    )


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(
        # allow_inf_nan=False: sin esto, un cuerpo con `NaN` (JSON no estándar
        # pero que json.loads acepta) llega hasta httpx y revienta con un 500.
        allow_inf_nan=False,
        json_schema_extra={
            "examples": [
                {
                    "model": "qwen2.5:3b",
                    "messages": [
                        {"role": "system", "content": "Eres un jugador profesional de LoL."},
                        {"role": "user", "content": "¿Quién es Teemo?"},
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "stream": False,
                }
            ]
        }
    )

    model: str = Field(default="qwen2.5:3b", examples=["qwen2.5:3b"])
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = Field(
        default=None, ge=0, le=2, description="0 = determinista, 0.7 = equilibrado, 2 = caótico"
    )
    top_p: float | None = Field(default=None, ge=0, le=1)
    n: int | None = Field(default=1, ge=1, description="Este gateway solo admite 1")
    stream: bool = False
    # Sin max_length en el Field: sobre una unión `list[str] | str`, pydantic lo
    # aplicaría también a la rama str y limitaría la CADENA a 4 caracteres, de
    # modo que stop="<|im_end|>" daría 422. El tope de secuencias va aparte.
    stop: list[str] | str | None = Field(
        default=None,
        description="Hasta 4 secuencias que cortan la generación. Déjalo nulo si no las usas.",
    )
    max_tokens: int | None = Field(default=None, ge=1, le=131072)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    user: str | None = None

    @field_validator("stop")
    @classmethod
    def _maximo_cuatro_secuencias(cls, value):
        if isinstance(value, list) and len(value) > 4:
            raise ValueError("stop admite como máximo 4 secuencias")
        return value


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str | None = "stop"


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: Usage


class ChatCompletionDelta(BaseModel):
    role: str | None = None
    content: str | None = None


class ChatCompletionChunkChoice(BaseModel):
    index: int = 0
    delta: ChatCompletionDelta
    finish_reason: str | None = None


class ChatCompletionChunk(BaseModel):
    id: str
    object: Literal["chat.completion.chunk"] = "chat.completion.chunk"
    created: int
    model: str
    choices: list[ChatCompletionChunkChoice]
