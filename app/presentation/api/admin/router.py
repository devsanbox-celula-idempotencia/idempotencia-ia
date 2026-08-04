"""Agrupa los routers administrativos bajo /admin."""
from __future__ import annotations

from fastapi import APIRouter

from app.presentation.api.admin import api_keys, logs, usage

admin_router = APIRouter()
admin_router.include_router(api_keys.router)
admin_router.include_router(usage.router)
admin_router.include_router(logs.router)
