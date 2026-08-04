"""Modelo ORM de la tabla RequestLogs (nueva)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, Unicode, desc, func, text
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class RequestLogModel(Base):
    __tablename__ = "RequestLogs"
    __table_args__ = (
        # DESC igual que en scripts/sql/001_create_tables.sql: las consultas
        # de logs siempre ordenan por CreatedAt descendente.
        Index("IX_RequestLogs_ApiKey_CreatedAt", "ApiKeyId", desc(text("CreatedAt"))),
        Index("IX_RequestLogs_CreatedAt", desc(text("CreatedAt"))),
    )

    RequestLogId: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ApiKeyId: Mapped[int | None] = mapped_column(Integer, ForeignKey("ApiKeys.ApiKeyId"), nullable=True)
    Model: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    Endpoint: Mapped[str] = mapped_column(Unicode(100), nullable=False)
    PromptTokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    CompletionTokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    TotalTokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    DurationMs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    StatusCode: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    ClientIp: Mapped[str | None] = mapped_column(Unicode(45), nullable=True)
    Error: Mapped[str | None] = mapped_column(Unicode(1000), nullable=True)
    CreatedAt: Mapped[datetime] = mapped_column(
        DATETIME2(0), nullable=False, server_default=func.sysutcdatetime()
    )
