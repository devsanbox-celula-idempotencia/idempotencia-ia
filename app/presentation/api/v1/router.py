"""Agrupa todos los routers públicos bajo /v1."""
from __future__ import annotations

from fastapi import APIRouter

from app.presentation.api.v1 import chat, completions, embeddings, models

api_router = APIRouter()
api_router.include_router(chat.router)
api_router.include_router(completions.router)
api_router.include_router(models.router)
api_router.include_router(embeddings.router)
