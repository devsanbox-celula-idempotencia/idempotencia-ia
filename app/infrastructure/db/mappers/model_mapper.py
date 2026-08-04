"""Mapper LLMModel."""
from __future__ import annotations

from app.domain.entities.model import LLMModel
from app.infrastructure.db.models.model_model import LLMModelModel


def to_entity(row: LLMModelModel) -> LLMModel:
    return LLMModel(
        id=row.ModelId,
        provider_model=row.ProviderModel,
        owned_by=row.OwnedBy,
        context_length=row.ContextLength,
        supports_embeddings=bool(row.SupportsEmbeddings),
        is_active=bool(row.IsActive),
        created_at=row.CreatedAt,
    )
