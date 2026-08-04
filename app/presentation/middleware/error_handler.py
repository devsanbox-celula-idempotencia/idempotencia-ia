"""Traduce excepciones al formato de error de OpenAI: {"error": {...}}."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.domain.exceptions import (
    DomainError,
    InvalidApiKeyError,
    ModelNotFoundError,
    ProviderError,
    QuotaExceededError,
    RateLimitExceededError,
)
from app.infrastructure.observability.logger import get_logger

logger = get_logger(__name__)

_STATUS_MAP: dict[type[DomainError], tuple[int, str]] = {
    InvalidApiKeyError: (401, "invalid_request_error"),
    RateLimitExceededError: (429, "rate_limit_error"),
    QuotaExceededError: (429, "insufficient_quota"),
    ModelNotFoundError: (404, "model_not_found"),
    ProviderError: (502, "api_error"),
}


def _error(
    message: str,
    error_type: str,
    code: str | None = None,
    status_code: int = 400,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"message": message, "type": error_type, "param": None, "code": code}},
        headers=headers,
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        status_code, error_type = _STATUS_MAP.get(type(exc), (400, "invalid_request_error"))
        if status_code >= 500:
            logger.warning("Error de proveedor: %s", exc)

        # Retry-After en los 429: el cliente sabe cuánto esperar sin adivinar.
        cabeceras = None
        espera = getattr(exc, "retry_after", None)
        if espera:
            cabeceras = {"Retry-After": str(int(espera))}

        return _error(str(exc), error_type, status_code=status_code, headers=cabeceras)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # No serializar exc.errors() tal cual: incluye el `input` completo por
        # cada rama de los Union, así que un cuerpo de 60 KB genera una
        # respuesta de varios MB.
        detalles = [
            {"campo": ".".join(str(x) for x in e["loc"]), "error": e["msg"], "tipo": e["type"]}
            for e in exc.errors()[:10]
        ]
        return _error(str(detalles), "invalid_request_error", status_code=422)

    # Se registra sobre la excepción de STARLETTE, no sobre la de FastAPI.
    # Los 404 de ruta inexistente y los 405 los lanza el router de Starlette con
    # su propia clase; como la de FastAPI es una subclase, registrar la de
    # FastAPI dejaba esos casos fuera y respondían `{"detail": "Not Found"}`,
    # rompiendo el contrato de errores de OpenAI.
    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _error(str(exc.detail), "invalid_request_error", status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Error no controlado en %s", request.url.path)
        return _error("Error interno del servidor", "api_error", status_code=500)
