"""Schemas de /v1/embeddings."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.presentation.schemas.openai.chat import Usage


class EmbeddingsRequest(BaseModel):
    model: str
    input: str | list[str] = Field(
        description="Un texto o una lista de textos (máximo 512).",
    )
    user: str | None = None

    @field_validator("input")
    @classmethod
    def _validar_input(cls, value: str | list[str]) -> str | list[str]:
        """Una lista vacía o textos vacíos son error del cliente (422), no del
        backend: sin esta validación Ollama no devolvía vectores y salía un 502."""
        textos = [value] if isinstance(value, str) else value
        if not textos:
            raise ValueError("input no puede estar vacío")
        if len(textos) > 512:
            raise ValueError("input admite como máximo 512 textos")
        if any(not t.strip() for t in textos):
            raise ValueError("input no puede contener textos vacíos")
        return value


class EmbeddingItem(BaseModel):
    object: Literal["embedding"] = "embedding"
    index: int
    embedding: list[float]


class EmbeddingsResponse(BaseModel):
    object: Literal["list"] = "list"
    data: list[EmbeddingItem]
    model: str
    usage: Usage
