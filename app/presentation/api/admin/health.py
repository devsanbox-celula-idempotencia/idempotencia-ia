"""Health checks del gateway."""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.presentation.dependencies import ContainerDep, SessionDep, SettingsDep

router = APIRouter(tags=["Health"])


@router.get("/health", summary="Liveness")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready", summary="Readiness (base de datos y Ollama)")
async def ready(
    session: SessionDep, container: ContainerDep, settings: SettingsDep
) -> dict[str, object]:
    database, db_error = True, None
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database, db_error = False, f"{type(exc).__name__}: {exc}"

    ollama = await container.provider.health()

    result: dict[str, object] = {
        "status": "ok" if (database and ollama) else "degraded",
        "database": database,
        "ollama": ollama,
    }
    # El detalle del error solo con DEBUG: puede filtrar host y usuario.
    if db_error and settings.DEBUG:
        result["database_error"] = db_error
        result["database_url"] = settings.safe_database_url
    return result
