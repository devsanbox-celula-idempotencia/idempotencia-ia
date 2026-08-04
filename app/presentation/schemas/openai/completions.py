"""Schemas de /v1/completions (API legacy de OpenAI)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.presentation.schemas.openai.chat import Usage


class CompletionRequest(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    model: str = Field(default="qwen2.5:3b")
    prompt: str | list[str]
    n: int | None = Field(default=1, ge=1)
    max_tokens: int | None = Field(default=None, ge=1, le=131072)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    stream: bool = False
    # Ver el comentario de ChatCompletionRequest.stop: max_length sobre una
    # unión con `str` limitaría la longitud de la cadena, no el nº de secuencias.
    stop: list[str] | str | None = None
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)

    @field_validator("stop")
    @classmethod
    def _maximo_cuatro_secuencias(cls, value):
        if isinstance(value, list) and len(value) > 4:
            raise ValueError("stop admite como máximo 4 secuencias")
        return value


class CompletionChoice(BaseModel):
    index: int = 0
    text: str
    finish_reason: str | None = "stop"


class CompletionResponse(BaseModel):
    id: str
    object: Literal["text_completion"] = "text_completion"
    created: int
    model: str
    choices: list[CompletionChoice]
    usage: Usage
