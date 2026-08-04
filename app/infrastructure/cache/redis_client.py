"""Conexión a Redis."""
from __future__ import annotations

from app.infrastructure.config.settings import get_settings


async def create_redis(url: str | None = None):
    """Devuelve un cliente redis.asyncio ya conectado, o None si falla."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(url or get_settings().REDIS_URL, decode_responses=True)
    await client.ping()
    return client
