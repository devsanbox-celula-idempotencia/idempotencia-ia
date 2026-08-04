"""Composition root: el único lugar donde las implementaciones concretas
se conectan con los puertos del dominio."""
from __future__ import annotations

from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.ports.services.password_hasher import KeyGenerator, KeyHasher
from app.domain.ports.services.rate_limiter import RateLimiter
from app.infrastructure.cache.in_memory_rate_limiter import InMemoryRateLimiter
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.llm.ollama_client import OllamaClient
from app.infrastructure.llm.ollama_provider import OllamaProvider
from app.infrastructure.observability.logger import get_logger
from app.infrastructure.security.hashing import Sha256KeyHasher
from app.infrastructure.security.key_generator import SecretsKeyGenerator

logger = get_logger(__name__)


class Container:
    """Se instancia una vez en el arranque y vive en app.state.container."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._ollama_client: OllamaClient | None = None
        self._provider: LLMProvider | None = None
        self._rate_limiter: RateLimiter | None = None
        self._redis = None
        self._hasher: KeyHasher = Sha256KeyHasher()
        self._generator: KeyGenerator = SecretsKeyGenerator(prefix=self.settings.API_KEY_PREFIX)

    # --- ciclo de vida ---
    async def startup(self) -> None:
        self._ollama_client = OllamaClient(
            self.settings.OLLAMA_BASE_URL, self.settings.OLLAMA_TIMEOUT_SECONDS
        )
        self._provider = OllamaProvider(self._ollama_client)

        if self.settings.RATE_LIMIT_BACKEND == "redis":
            try:
                from app.infrastructure.cache.redis_client import create_redis
                from app.infrastructure.cache.redis_rate_limiter import RedisRateLimiter

                self._redis = await create_redis(self.settings.REDIS_URL)
                self._rate_limiter = RedisRateLimiter(self._redis)
                logger.info("Rate limiting con Redis")
            except Exception as exc:  # noqa: BLE001
                logger.warning("Redis no disponible (%s); se usa el limitador en memoria", exc)
                self._rate_limiter = InMemoryRateLimiter()
        else:
            self._rate_limiter = InMemoryRateLimiter()
            logger.info("Rate limiting en memoria")

    async def shutdown(self) -> None:
        if self._ollama_client is not None:
            await self._ollama_client.aclose()
        if self._redis is not None:
            await self._redis.aclose()

    # --- accesores ---
    @property
    def provider(self) -> LLMProvider:
        assert self._provider is not None, "Container.startup() no fue llamado"
        return self._provider

    @property
    def rate_limiter(self) -> RateLimiter:
        assert self._rate_limiter is not None, "Container.startup() no fue llamado"
        return self._rate_limiter

    @property
    def hasher(self) -> KeyHasher:
        return self._hasher

    @property
    def key_generator(self) -> KeyGenerator:
        return self._generator
