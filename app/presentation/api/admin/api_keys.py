"""Gestión de API keys (endpoints internos)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.application.dto.api_key_dto import CreateApiKeyInput
from app.application.use_cases.admin.create_api_key import CreateApiKey
from app.application.use_cases.admin.list_api_keys import ListApiKeys
from app.application.use_cases.admin.revoke_api_key import RevokeApiKey
from app.presentation.dependencies import ContainerDep, UowDep, require_admin
from app.presentation.schemas.admin.api_key_schemas import (
    ApiKeyCreatedResponse,
    ApiKeyCreateRequest,
    ApiKeyResponse,
)

router = APIRouter(tags=["Admin"], dependencies=[Depends(require_admin)])


@router.post(
    "/api-keys",
    response_model=ApiKeyCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una API key",
    description="La clave en claro se devuelve **una sola vez**; en la base de datos solo queda su hash.",
)
async def create_api_key(payload: ApiKeyCreateRequest, uow: UowDep, container: ContainerDep):
    use_case = CreateApiKey(uow, container.key_generator, container.hasher)
    result = await use_case.execute(
        CreateApiKeyInput(
            user_id=payload.user_id,
            name=payload.name,
            expires_at=payload.expires_at,
            daily_token_limit=payload.daily_token_limit,
            monthly_token_limit=payload.monthly_token_limit,
            requests_per_minute=payload.requests_per_minute,
        )
    )
    return ApiKeyCreatedResponse(
        id=result.id, name=result.name, api_key=result.raw_key, created_at=result.created_at
    )


@router.get("/api-keys", response_model=list[ApiKeyResponse], summary="Listar keys de un usuario")
async def list_api_keys(user_id: int, uow: UowDep):
    keys = await ListApiKeys(uow).execute(user_id)
    return [
        ApiKeyResponse(
            id=k.id,
            user_id=k.user_id,
            name=k.name,
            key_prefix=k.key_prefix,
            is_active=k.is_active,
            created_at=k.created_at,
            last_used_at=k.last_used_at,
            expires_at=k.expires_at,
            daily_token_limit=k.daily_token_limit,
            requests_per_minute=k.requests_per_minute,
        )
        for k in keys
    ]


@router.delete(
    "/api-keys/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,   # con `from __future__ import annotations`, FastAPI tomaría "-> None" como response_model
    summary="Revocar",
)
async def revoke_api_key(api_key_id: int, uow: UowDep) -> None:
    await RevokeApiKey(uow).execute(api_key_id)
