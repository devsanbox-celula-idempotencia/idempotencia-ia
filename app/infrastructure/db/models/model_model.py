"""Modelo ORM de la tabla LlmModels (nueva): catálogo de modelos."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, Unicode, UniqueConstraint, func
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class LLMModelModel(Base):
    __tablename__ = "LlmModels"
    __table_args__ = (UniqueConstraint("ModelId", name="UQ_LlmModels_ModelId"),)

    LlmModelId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ModelId: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    ProviderModel: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    OwnedBy: Mapped[str] = mapped_column(Unicode(50), nullable=False, default="local")
    ContextLength: Mapped[int | None] = mapped_column(Integer, nullable=True)
    SupportsEmbeddings: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DATETIME2(0), nullable=False, server_default=func.sysutcdatetime()
    )
