"""Fixtures compartidas: la app con todas sus dependencias sustituidas.

No hace falta SQL Server ni Ollama para ejecutar la suite: los casos de uso
dependen de puertos, y aquí se inyectan dobles en memoria.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain.entities.api_key import ApiKey
from app.domain.entities.model import LLMModel
from app.domain.entities.user import User
from app.infrastructure.cache.in_memory_rate_limiter import InMemoryRateLimiter
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.db.session import get_session
from app.infrastructure.security.hashing import Sha256KeyHasher
from app.infrastructure.security.key_generator import SecretsKeyGenerator
from app.main import app as fastapi_app
from app.presentation.dependencies import (
    get_container,
    get_provider,
    get_uow,
    get_usage_recorder,
)
from tests.fakes import (
    FakeApiKeyRepository,
    FakeContainer,
    FakeLLMProvider,
    FakeModelRepository,
    FakeSession,
    FakeUnitOfWork,
    FakeUsageRecorder,
    FakeUserRepository,
)

ADMIN_TOKEN = "token-de-prueba-1234567890"
CLAVE_VALIDA = "sk_live_clave_de_prueba"
CLAVE_REVOCADA = "sk_live_clave_revocada"
CLAVE_EXPIRADA = "sk_live_clave_expirada"

_hasher = Sha256KeyHasher()


def _ahora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def construir_settings(**overrides) -> Settings:
    """Settings aislados del .env del repositorio.

    Sin `_env_file=None`, los valores del .env de la máquina donde se ejecuta la
    suite se colarían en las pruebas y podrían romperlas (por ejemplo si alguien
    vacía OPENAPI_URL o cambia API_KEY_PREFIX).
    """
    base = dict(
        _env_file=None,
        ADMIN_TOKEN=ADMIN_TOKEN,
        API_KEY_PREFIX="sk_live_",
        ALLOWED_MODELS=["qwen2.5:3b"],
        DEFAULT_REQUESTS_PER_MINUTE=60,
        DEFAULT_TOKENS_PER_DAY=1_000_000,
        RATE_LIMIT_ENABLED=True,
        DEBUG=True,
        ENVIRONMENT="test",
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def settings() -> Settings:
    return construir_settings()


@pytest.fixture
def usuario() -> User:
    return User(id=1, email="santi@test.com", full_name="Santiago", role="admin", is_active=True)


@pytest.fixture
def claves() -> list[ApiKey]:
    return [
        ApiKey(
            id=1,
            user_id=1,
            name="valida",
            key_hash=_hasher.hash(CLAVE_VALIDA),
            key_prefix=CLAVE_VALIDA[:12],
            is_active=True,
            created_at=_ahora(),
        ),
        ApiKey(
            id=2,
            user_id=1,
            name="revocada",
            key_hash=_hasher.hash(CLAVE_REVOCADA),
            key_prefix=CLAVE_REVOCADA[:12],
            is_active=False,
            created_at=_ahora(),
        ),
        ApiKey(
            id=3,
            user_id=1,
            name="expirada",
            key_hash=_hasher.hash(CLAVE_EXPIRADA),
            key_prefix=CLAVE_EXPIRADA[:12],
            is_active=True,
            created_at=_ahora(),
            expires_at=_ahora() - timedelta(days=1),
        ),
    ]


@pytest.fixture
def modelos() -> list[LLMModel]:
    return [
        LLMModel(
            id="qwen2.5:3b",
            provider_model="qwen2.5:3b",
            owned_by="local",
            context_length=32768,
            created_at=datetime(2026, 1, 1),
        )
    ]


@pytest.fixture
def uow(usuario: User, claves: list[ApiKey], modelos: list[LLMModel]) -> FakeUnitOfWork:
    return FakeUnitOfWork(
        users=FakeUserRepository([usuario]),
        api_keys=FakeApiKeyRepository(claves),
        models=FakeModelRepository(modelos),
    )


@pytest.fixture
def provider() -> FakeLLMProvider:
    return FakeLLMProvider()


@pytest.fixture
def limiter() -> InMemoryRateLimiter:
    return InMemoryRateLimiter()


@pytest.fixture
def recorder(uow: FakeUnitOfWork) -> FakeUsageRecorder:
    return FakeUsageRecorder(uow)


@pytest.fixture
def session() -> FakeSession:
    return FakeSession()


@pytest.fixture
def client(
    settings: Settings,
    uow: FakeUnitOfWork,
    provider: FakeLLMProvider,
    limiter: InMemoryRateLimiter,
    recorder: FakeUsageRecorder,
    session: FakeSession,
) -> Iterator[TestClient]:
    contenedor = FakeContainer(
        provider=provider,
        rate_limiter=limiter,
        hasher=_hasher,
        key_generator=SecretsKeyGenerator(prefix=settings.API_KEY_PREFIX),
    )

    fastapi_app.dependency_overrides = {
        get_settings: lambda: settings,
        get_uow: lambda: uow,
        get_container: lambda: contenedor,
        get_provider: lambda: provider,
        get_usage_recorder: lambda: recorder,
        get_session: lambda: session,
    }

    # Sin `with`: no se ejecuta el lifespan y por tanto no se abre ninguna
    # conexión real. Todo lo que el lifespan construiría está sustituido arriba.
    # raise_server_exceptions=False para poder comprobar los 500 como respuesta.
    cliente = TestClient(fastapi_app, raise_server_exceptions=False)
    try:
        yield cliente
    finally:
        fastapi_app.dependency_overrides = {}


@pytest.fixture
def auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {CLAVE_VALIDA}"}


@pytest.fixture
def admin() -> dict[str, str]:
    return {"X-Admin-Token": ADMIN_TOKEN}


@pytest.fixture
def cuerpo_chat() -> dict:
    return {"model": "qwen2.5:3b", "messages": [{"role": "user", "content": "Hola"}]}
