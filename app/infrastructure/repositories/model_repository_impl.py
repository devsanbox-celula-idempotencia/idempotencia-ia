"""Repositorio del catálogo de modelos."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities.model import LLMModel
from app.domain.ports.repositories.model_repository import ModelRepository
from app.infrastructure.db.mappers import model_mapper
from app.infrastructure.db.models.model_model import LLMModelModel

# SQL Server no tiene tipo booleano: BIT es un entero.
# `IsActive.is_(True)` compilaría a `IS 1`, que es sintaxis inválida en T-SQL
# (IS solo acepta NULL). Con `== True` se genera `IsActive = 1`, que sí es válido.
_ACTIVE = LLMModelModel.IsActive == True  # noqa: E712


class SqlAlchemyModelRepository(ModelRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self) -> list[LLMModel]:
        stmt = select(LLMModelModel).where(_ACTIVE).order_by(LLMModelModel.ModelId)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [model_mapper.to_entity(r) for r in rows]

    async def get_by_id(self, model_id: str) -> LLMModel | None:
        stmt = select(LLMModelModel).where(LLMModelModel.ModelId == model_id, _ACTIVE)
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return model_mapper.to_entity(row) if row else None
