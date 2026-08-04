"""Crea una API key para un usuario existente de la tabla Users.

Uso:  python -m scripts.create_admin_key --user-id 1 --name "clave inicial"
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.application.dto.api_key_dto import CreateApiKeyInput
from app.application.use_cases.admin.create_api_key import CreateApiKey
from app.domain.exceptions import DomainError
from app.infrastructure.config.settings import get_settings
from app.infrastructure.db.session import dispose_engine, get_session_factory
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.hashing import Sha256KeyHasher
from app.infrastructure.security.key_generator import SecretsKeyGenerator


async def _print_available_users(session) -> None:
    """Si el UserId no existe, mostrar los que sí, para no adivinar."""
    rows = (
        await session.execute(
            text("SELECT TOP 10 UserId, Email FROM dbo.Users ORDER BY UserId")
        )
    ).all()
    if not rows:
        print("\n  La tabla dbo.Users está vacía. Inserta un usuario primero:\n")
        print("    INSERT INTO dbo.Users (Role, Email, PasswordHash, FullName, IsActive, CreatedAt)")
        print("    VALUES ('admin', 'tu@correo.com', 'x', 'Tu Nombre', 1, SYSUTCDATETIME());\n")
        return
    print("\n  UserId disponibles:\n")
    for user_id, email in rows:
        print(f"    --user-id {user_id}   ({email})")
    print()


async def main(user_id: int, name: str, rpm: int | None, daily_tokens: int | None) -> int:
    settings = get_settings()
    try:
        async with get_session_factory()() as session:
            uow = SqlAlchemyUnitOfWork(session)
            use_case = CreateApiKey(
                uow,
                SecretsKeyGenerator(prefix=settings.API_KEY_PREFIX),
                Sha256KeyHasher(),
            )
            try:
                result = await use_case.execute(
                    CreateApiKeyInput(
                        user_id=user_id,
                        name=name,
                        requests_per_minute=rpm,
                        daily_token_limit=daily_tokens,
                    )
                )
            except DomainError as exc:
                print(f"\n  {exc}")
                await _print_available_users(session)
                return 1

        print("\n  API key creada. Se muestra UNA sola vez:\n")
        print(f"  {result.raw_key}\n")
        print(f"  id={result.id}  nombre={result.name}\n")
        return 0
    finally:
        # Sin esto aioodbc avisa "Unclosed connection" al terminar el script
        await dispose_engine()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", type=int, required=True)
    parser.add_argument("--name", default="clave inicial")
    parser.add_argument("--rpm", type=int, default=None)
    parser.add_argument("--daily-tokens", type=int, default=None)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.user_id, args.name, args.rpm, args.daily_tokens)))
