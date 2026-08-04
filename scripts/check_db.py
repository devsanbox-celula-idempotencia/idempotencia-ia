"""Diagnóstico de la conexión a SQL Server.

Uso:  python -m scripts.check_db

Comprueba, en orden: que la cadena se puede parsear, que el driver ODBC está
instalado, que el servidor responde y que existen las tablas del gateway.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.infrastructure.config.settings import get_settings

TABLES = ["Users", "ApiKeys", "ApiKeyUsage", "RequestLogs", "LlmModels"]


def check_url() -> str | None:
    settings = get_settings()
    try:
        url = settings.sqlalchemy_url
    except Exception as exc:  # noqa: BLE001
        print(f"[X] No se pudo construir la URL: {exc}")
        return None

    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        print(f"[ok] URL válida  -> host={parts.hostname} puerto={parts.port} base={parts.path.lstrip('/')}")
    except ValueError as exc:
        print(f"[X] La URL no se puede parsear: {exc}")
        print("     Suele ser un símbolo sin codificar en la contraseña.")
        print("     Codifica: ] -> %5D   } -> %7D   @ -> %40   / -> %2F   : -> %3A   # -> %23")
        print("     O usa las variables sueltas DB_HOST / DB_USER / DB_PASSWORD / DB_NAME del .env.")
        return None
    return url


def check_driver() -> bool:
    try:
        import pyodbc
    except ImportError:
        print("[X] pyodbc no está instalado")
        return False

    drivers = pyodbc.drivers()
    target = get_settings().DB_DRIVER
    if any(target.lower() == d.lower() for d in drivers):
        print(f"[ok] Driver ODBC encontrado -> {target}")
        return True

    print(f"[X] No está instalado el driver '{target}'")
    print(f"     Drivers disponibles: {drivers or 'ninguno'}")
    print("     Descárgalo: https://learn.microsoft.com/sql/connect/odbc/download-odbc-driver-for-sql-server")
    return False


async def check_connection() -> bool:
    from app.infrastructure.db.session import get_session_factory

    try:
        async with get_session_factory()() as session:
            version = (await session.execute(text("SELECT @@VERSION"))).scalar_one()
            database = (await session.execute(text("SELECT DB_NAME()"))).scalar_one()
        print(f"[ok] Conexión establecida -> base actual: {database}")
        print(f"     {str(version).splitlines()[0]}")
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"[X] No se pudo conectar: {type(exc).__name__}")
        print(f"     {exc}")
        print("     Causas frecuentes: base de datos inexistente, usuario o contraseña")
        print("     incorrectos, puerto 1433 cerrado por el firewall, o el servidor")
        print("     no acepta autenticación de SQL Server.")
        return False


async def check_tables() -> None:
    from app.infrastructure.db.session import get_session_factory

    async with get_session_factory()() as session:
        for table in TABLES:
            exists = (
                await session.execute(
                    text("SELECT OBJECT_ID(:name, 'U')"), {"name": f"dbo.{table}"}
                )
            ).scalar_one()
            mark = "ok" if exists else "X "
            note = "" if exists else "   <- falta: ejecuta scripts/sql/001_create_tables.sql"
            print(f"[{mark}] tabla {table}{note}")


async def main() -> int:
    try:
        return await _run()
    finally:
        from app.infrastructure.db.session import dispose_engine

        await dispose_engine()


async def _run() -> int:
    print(f"\nConfiguración: {get_settings().safe_database_url}\n")

    if check_url() is None:
        return 1
    if not check_driver():
        return 1
    if not await check_connection():
        return 1

    print()
    await check_tables()
    print("\nTodo listo.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
