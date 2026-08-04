"""Schemas de /v1/models."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ModelCard(BaseModel):
    id: str
    object: Literal["model"] = "model"
    created: int = 0
    owned_by: str = "local"


class ModelList(BaseModel):
    object: Literal["list"] = "list"
    data: list[ModelCard]
