"""Mapper User."""
from __future__ import annotations

from app.domain.entities.user import User
from app.infrastructure.db.models.user_model import UserModel


def to_entity(row: UserModel) -> User:
    return User(
        id=row.UserId,
        email=row.Email,
        full_name=row.FullName,
        role=row.Role,
        is_active=bool(row.IsActive),
        created_at=row.CreatedAt,
        last_login_at=row.LastLoginAt,
    )
