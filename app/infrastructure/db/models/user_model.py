"""Modelo ORM de la tabla Users, que ya existe en tu base de datos.

El gateway solo la lee (para validar el UserId al crear una API key); no la
modifica ni la crea.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, Integer, Unicode
from sqlalchemy.dialects.mssql import DATETIME2
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.db.base import Base


class UserModel(Base):
    __tablename__ = "Users"

    UserId: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    Role: Mapped[str | None] = mapped_column(Unicode(50), nullable=True)
    Email: Mapped[str] = mapped_column(Unicode(256), nullable=False)
    PasswordHash: Mapped[str | None] = mapped_column(Unicode(256), nullable=True)
    FullName: Mapped[str | None] = mapped_column(Unicode(200), nullable=True)
    IsActive: Mapped[bool] = mapped_column(Boolean, default=True)
    CreatedAt: Mapped[datetime | None] = mapped_column(DATETIME2(0), nullable=True)
    LastLoginAt: Mapped[datetime | None] = mapped_column(DATETIME2(0), nullable=True)
