"""Modelo ORM de la tabla ApiKeys (nueva).

Los tipos y los nombres de índices/constraints replican exactamente
scripts/sql/001_create_tables.sql para que Alembic no proponga cambios falsos.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Unicode, UniqueConstraint, func
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class ApiKeyModel(Base):
    __tablename__ = "ApiKeys"
    __table_args__ = (
        UniqueConstraint("KeyHash", name="UQ_ApiKeys_KeyHash"),
        Index("IX_ApiKeys_UserId", "UserId"),
    )

    ApiKeyId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    UserId: Mapped[int] = mapped_column(Integer, ForeignKey("Users.UserId"), nullable=False)
    Name: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    KeyHash: Mapped[str] = mapped_column(Unicode(64), nullable=False)
    KeyPrefix: Mapped[str] = mapped_column(Unicode(20), nullable=False)
    IsActive: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DATETIME2(0), nullable=False, server_default=func.sysutcdatetime()
    )
    ExpiresAt: Mapped[datetime | None] = mapped_column(DATETIME2(0), nullable=True)
    LastUsedAt: Mapped[datetime | None] = mapped_column(DATETIME2(0), nullable=True)
    DailyTokenLimit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    MonthlyTokenLimit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    RequestsPerMinute: Mapped[int | None] = mapped_column(Integer, nullable=True)
