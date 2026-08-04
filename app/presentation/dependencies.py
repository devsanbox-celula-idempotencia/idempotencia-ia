"""Dependencias de FastAPI: sesión, autenticación, rate limit e inyección."""
from __future__ import annotations

import ipaddress
import secrets
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.use_cases.admin.record_usage import UsageRecorder
from app.application.use_cases.auth.authenticate_api_key import AuthenticateApiKey
from app.application.use_cases.auth.check_rate_limit import CheckRateLimit
from app.domain.entities.api_key import ApiKey
from app.domain.exceptions import InvalidApiKeyError
from app.domain.ports.services.llm_provider import LLMProvider
from app.domain.ports.services.unit_of_work import UnitOfWork
from app.infrastructure.config.container import Container
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.db.scoped_record_usage import ScopedRecordUsage
from app.infrastructure.db.session import get_session
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork

# auto_error=False para poder devolver 401 (como OpenAI) en vez del 403 que
# emite HTTPBearer por su cuenta. El SDK distingue AuthenticationError de
# PermissionDeniedError según ese código.
bearer_scheme = HTTPBearer(
    scheme_name="API Key",
    description="Tu clave del gateway: `Authorization: Bearer sk_live_...`",
    auto_error=False,
)

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
CredentialsDep = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


def get_container(request: Request) -> Container:
    return request.app.state.container


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_uow(session: SessionDep) -> AsyncGenerator[UnitOfWork, None]:
    uow = SqlAlchemyUnitOfWork(session)
    async with uow:
        yield uow


UowDep = Annotated[UnitOfWork, Depends(get_uow)]


def get_usage_recorder() -> UsageRecorder:
    """Registrador de consumo con sesión propia.

    Se inyecta (en vez de instanciarlo dentro del router) para que las pruebas
    puedan sustituirlo y no dependan de una base de datos real.
    """
    return ScopedRecordUsage()


UsageRecorderDep = Annotated[UsageRecorder, Depends(get_usage_recorder)]


def get_provider(container: ContainerDep) -> LLMProvider:
    return container.provider


ProviderDep = Annotated[LLMProvider, Depends(get_provider)]


async def get_current_api_key(
    credentials: CredentialsDep, uow: UowDep, container: ContainerDep
) -> ApiKey:
    if credentials is None or not credentials.credentials:
        raise InvalidApiKeyError("Falta la cabecera Authorization: Bearer sk_live_...")
    use_case = AuthenticateApiKey(uow, container.hasher)
    return await use_case.execute(credentials.credentials)


ApiKeyDep = Annotated[ApiKey, Depends(get_current_api_key)]


async def enforce_rate_limit(
    response: Response,
    api_key: ApiKeyDep,
    uow: UowDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> ApiKey:
    if not settings.RATE_LIMIT_ENABLED:
        return api_key

    use_case = CheckRateLimit(
        container.rate_limiter,
        uow.usage,
        settings.DEFAULT_REQUESTS_PER_MINUTE,
        settings.DEFAULT_TOKENS_PER_DAY,
    )
    resultado = await use_case.execute(api_key)

    # Cabeceras informativas: permiten al frontend mostrar cuánto le queda y
    # frenar antes de comerse un 429. Van expuestas en CORS (ver app/main.py).
    if resultado.limit is not None:
        response.headers["X-RateLimit-Limit"] = str(resultado.limit)
        response.headers["X-RateLimit-Remaining"] = str(resultado.remaining or 0)
        response.headers["X-RateLimit-Reset"] = str(resultado.reset_in_seconds or 0)

    return api_key


LimitedApiKeyDep = Annotated[ApiKey, Depends(enforce_rate_limit)]


async def require_admin(
    settings: SettingsDep, x_admin_token: Annotated[str | None, Header()] = None
) -> bool:
    # compare_digest: comparar con == permite deducir el token byte a byte
    # midiendo el tiempo de respuesta.
    # Se comparan BYTES: con dos `str`, compare_digest lanza TypeError si alguno
    # tiene caracteres no ASCII, y Starlette decodifica las cabeceras en latin-1.
    # Eso convertiría una cabecera con acentos en un 500 en vez de un 403.
    if not x_admin_token or not secrets.compare_digest(
        x_admin_token.encode("utf-8"), settings.ADMIN_TOKEN.encode("utf-8")
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token inválido")
    return True


def client_ip(request: Request) -> str | None:
    """IP del cliente, validada.

    X-Forwarded-For lo controla quien llama: sin validar, una cabecera larga
    reventaría el INSERT en RequestLogs (ClientIp es NVARCHAR(45)) y el
    consumo se perdería. Solo se acepta si es una IP de verdad.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()[:45]
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            pass   # cabecera basura o falsificada: se ignora y se usa la real
    return request.client.host[:45] if request.client else None


__all__ = [
    "ApiKeyDep",
    "ContainerDep",
    "LimitedApiKeyDep",
    "ProviderDep",
    "SessionDep",
    "SettingsDep",
    "UowDep",
    "UsageRecorderDep",
    "client_ip",
    "get_current_api_key",
    "require_admin",
]
