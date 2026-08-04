"""Punto de entrada de la aplicación FastAPI.

Ejecutar:  uvicorn app.main:app --reload
Swagger:   http://localhost:8000/docs
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.infrastructure.config.container import Container
from app.infrastructure.config.settings import get_settings
from app.infrastructure.observability.logger import get_logger, setup_logging
from app.presentation.api.admin.health import router as health_router
from app.presentation.api.admin.router import admin_router
from app.presentation.api.v1.router import api_router
from app.presentation.middleware.error_handler import register_exception_handlers
from app.presentation.middleware.logging_middleware import LoggingMiddleware
from app.presentation.middleware.request_id import RequestIdMiddleware
from app.presentation.openapi import TAGS_METADATA, custom_openapi

settings = get_settings()
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando %s v%s (%s)", settings.APP_NAME, settings.APP_VERSION, settings.ENVIRONMENT)
    container = Container(settings)
    await container.startup()
    app.state.container = container

    if settings.ADMIN_TOKEN.startswith(("cambia", "change")):
        mensaje = "ADMIN_TOKEN sigue con el valor de ejemplo: /admin está abierto a cualquiera"
        if settings.ENVIRONMENT != "development":
            raise RuntimeError(mensaje + ". Genera uno con: python -c \"import secrets;print(secrets.token_hex(32))\"")
        logger.warning("%s. Cámbialo antes de exponer la API.", mensaje)

    if await container.provider.health():
        logger.info("Ollama disponible en %s", settings.OLLAMA_BASE_URL)
    else:
        logger.warning("Ollama NO responde en %s", settings.OLLAMA_BASE_URL)

    yield

    await container.shutdown()
    logger.info("Apagando %s", settings.APP_NAME)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        docs_url=settings.DOCS_URL or None,
        redoc_url=settings.REDOC_URL or None,
        openapi_url=settings.OPENAPI_URL or None,
        openapi_tags=TAGS_METADATA,
        lifespan=lifespan,
        swagger_ui_parameters={"persistAuthorization": True, "displayRequestDuration": True},
    )

    # Los navegadores rechazan `Access-Control-Allow-Origin: *` junto con
    # credenciales, así que solo se permiten cuando hay una lista concreta.
    permite_credenciales = "*" not in settings.CORS_ORIGINS
    if not permite_credenciales:
        logger.warning(
            "CORS_ORIGINS contiene '*': se desactivan las credenciales. "
            "Enumera los orígenes del frontend para poder usar cookies."
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=permite_credenciales,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Admin-Token", "X-Request-ID"],
        # Sin esto el navegador NO deja leer estas cabeceras desde JavaScript,
        # aunque viajen en la respuesta.
        expose_headers=[
            "X-Request-ID",
            "X-Response-Time-Ms",
            "Retry-After",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
        max_age=600,
    )
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    app.include_router(admin_router, prefix=settings.ADMIN_PREFIX)
    app.include_router(health_router)

    register_exception_handlers(app)
    app.openapi = custom_openapi(app)
    return app


app = create_app()
