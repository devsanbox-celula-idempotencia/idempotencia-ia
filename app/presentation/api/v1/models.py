"""GET /v1/models — catálogo de modelos expuestos por el gateway."""
from __future__ import annotations

from fastapi import APIRouter

from app.application.use_cases.models.list_models import ListModels, RetrieveModel
from datetime import timezone

from app.presentation.dependencies import LimitedApiKeyDep, SettingsDep, UowDep
from app.presentation.schemas.openai.models import ModelCard, ModelList

router = APIRouter(tags=["OpenAI Compatible"])


def _to_card(model) -> ModelCard:
    return ModelCard(
        id=model.id,
        # created_at llega naive desde SQL Server pero es UTC: sin marcarlo,
        # .timestamp() lo interpretaría como hora local del proceso.
        created=(
            int(model.created_at.replace(tzinfo=timezone.utc).timestamp())
            if model.created_at
            else 0
        ),
        owned_by=model.owned_by,
    )


@router.get("/models", response_model=ModelList, summary="Listar modelos")
async def list_models(api_key: LimitedApiKeyDep, uow: UowDep, settings: SettingsDep):
    models = await ListModels(uow.models, settings.ALLOWED_MODELS).execute()
    return ModelList(data=[_to_card(m) for m in models])


@router.get("/models/{model_id:path}", response_model=ModelCard, summary="Obtener un modelo")
async def retrieve_model(model_id: str, api_key: LimitedApiKeyDep, uow: UowDep, settings: SettingsDep):
    model = await RetrieveModel(uow.models, settings.ALLOWED_MODELS).execute(model_id)
    return _to_card(model)
