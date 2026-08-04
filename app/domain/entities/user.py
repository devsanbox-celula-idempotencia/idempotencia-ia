"""Entidad User. Refleja la tabla Users que ya existe en la base de datos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class User:
    id: int
    email: str
    full_name: str | None = None
    role: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    last_login_at: datetime | None = None
