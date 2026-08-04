"""Motor y sesiones de SQLAlchemy 2.0 (async) sobre SQL Server.

El motor se construye de forma perezosa: así importar la aplicación (para
generar el esquema OpenAPI o para ejecutar las pruebas) no depende de que la
cadena de conexión sea válida ni abre nada.
"""
from __future__ import annotations

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.infrastructure.config.settings import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(
        settings.sqlalchemy_url,
        echo=settings.DB_ECHO,
        # pre_ping: verifica la conexión al sacarla del pool y descarta la que murió
        pool_pre_ping=True,
        # recycle: no reutilizar conexiones más viejas que esto. Los servidores
        # remotos y los NAT cortan conexiones ociosas a los pocos minutos.
        pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with get_session_factory()() as session:
        yield session


async def dispose_engine() -> None:
    """Cierra el pool. Los scripts de línea de comandos deben llamarlo al salir."""
    await get_engine().dispose()
