"""Modelo ORM de la tabla ApiKeyUsage (nueva)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class UsageModel(Base):
    __tablename__ = "ApiKeyUsage"
    __table_args__ = (UniqueConstraint("ApiKeyId", "Day", name="UQ_ApiKeyUsage_ApiKey_Day"),)

    UsageId: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ApiKeyId: Mapped[int] = mapped_column(Integer, ForeignKey("ApiKeys.ApiKeyId"), nullable=False)
    Day: Mapped[date] = mapped_column(Date, nullable=False)
    PromptTokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    CompletionTokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    TotalTokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    Requests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
